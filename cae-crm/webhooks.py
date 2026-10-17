"""Webhooks: when something happens in CAE CRM, POST it as JSON to a business's own URL (Zapier, Make, n8n, their own
system). Each request is signed so the receiver can check it came from us:

    CAE-Signature: t=<unix time>,v1=<hex HMAC-SHA256 of "<t>.<raw body>" using the webhook's signing secret>

The first attempt is made as soon as the change is saved. A failed delivery is retried by the cron job, up to
MAX_ATTEMPTS times, further apart each time. After DISABLE_AFTER failures in a row the webhook is paused and admins
are told. Only public https addresses are allowed, so a webhook can't be pointed at anything on our own network."""

import hashlib
import hmac
import ipaddress
import json
import secrets
import socket
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from flask import current_app, flash, g, redirect, request, url_for

import auth
from core import now, one, rows, scalar, ws
from db import get_db
from events import EVENTS

EVENT_CHOICES = [(name, label) for name, (label, _) in EVENTS.items()]
TABLES = {"contact": "contacts", "company": "companies", "deal": "deals", "ticket": "tickets", "quote": "quotes",
          "invoice": "invoices"}
MAX_HOOKS = 10
MAX_ATTEMPTS = 6
BACKOFF_MINUTES = [5, 30, 120, 720, 1440]  # after attempts 1 to 5
DISABLE_AFTER = 20
INLINE_BUDGET = 4  # seconds a page may spend sending webhooks before leaving the rest to the cron job
TIMEOUT = 3


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def resolve(host):
    """Every address a host name points to. Tests replace this."""
    return {info[4][0] for info in socket.getaddrinfo(host, None)}


def check_url(url):
    """Why a URL can't be used for a webhook, or None if it can."""
    parts = urlsplit(url or "")
    if parts.scheme != "https" or not parts.hostname:
        return "Use a full https:// address."
    if len(url) > 500:
        return "That address is too long."
    try:
        addresses = resolve(parts.hostname)
    except (socket.gaierror, UnicodeError, ValueError):
        return f"{parts.hostname} couldn't be found."
    if not addresses or not all(ipaddress.ip_address(a.split("%")[0]).is_global for a in addresses):
        return "Webhooks can only go to public internet addresses."
    return None


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # a redirect could lead somewhere check_url never saw


def post(url, headers, body):
    """(status code or None, error message or None)."""
    fake = current_app.config.get("WEBHOOK_HTTP")
    if fake:
        return fake(url, headers, body), None
    problem = check_url(url)  # again, in case the address now points somewhere else
    if problem:
        return None, problem
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.build_opener(NoRedirects).open(req, timeout=TIMEOUT) as resp:
            return resp.status, None
    except urllib.error.HTTPError as e:
        return e.code, f"Your server answered {e.code}."
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return None, f"Couldn't reach your server ({getattr(e, 'reason', e)})."[:300]


def sign(secret, body, stamp=None):
    stamp = stamp or int(time.time())
    digest = hmac.new(secret.encode(), f"{stamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={stamp},v1={digest}"


def payload(evt):
    from api import serialise
    kind = EVENTS[evt["event"]][1]
    table = TABLES[kind]
    row = one(f"SELECT * FROM {table} WHERE id=? AND workspace_id=?", evt["record_id"], ws())
    return {"id": f"evt_{uuid.uuid4().hex}", "event": evt["event"], "created_at": utc_now().isoformat(),
            "data": serialise(table, row) if row else {"id": evt["record_id"]}, **evt["extra"]}


def deliver(d, hook):
    """Try one delivery and record what happened. Returns True if it arrived."""
    db = get_db()
    body = d["payload"].encode()
    headers = {"Content-Type": "application/json", "User-Agent": "CAE-CRM-Webhooks/1", "CAE-Event": d["event"],
               "CAE-Delivery": str(d["id"]), "CAE-Signature": sign(hook["secret"], body)}
    status, problem = post(hook["url"], headers, body)
    attempts = d["attempts"] + 1
    stamp = utc_now()
    if status and 200 <= status < 300:
        db.execute("UPDATE webhook_deliveries SET status='delivered', attempts=?, response_code=?, last_error=NULL, "
                   "delivered_at=?, next_attempt_at=NULL WHERE id=?", (attempts, status, stamp.isoformat(), d["id"]))
        db.execute("UPDATE webhooks SET failures=0 WHERE id=?", (hook["id"],))
        db.commit()
        return True
    problem = problem or f"Your server answered {status}."
    if attempts >= MAX_ATTEMPTS:
        db.execute("UPDATE webhook_deliveries SET status='failed', attempts=?, response_code=?, last_error=?, "
                   "next_attempt_at=NULL WHERE id=?", (attempts, status, problem, d["id"]))
    else:
        retry = stamp + timedelta(minutes=BACKOFF_MINUTES[attempts - 1])
        db.execute("UPDATE webhook_deliveries SET attempts=?, response_code=?, last_error=?, next_attempt_at=? WHERE id=?",
                   (attempts, status, problem, retry.isoformat(), d["id"]))
    failures = hook["failures"] + 1
    db.execute("UPDATE webhooks SET failures=? WHERE id=?", (failures, hook["id"]))
    if failures >= DISABLE_AFTER and hook["active"]:
        db.execute("UPDATE webhooks SET active=0 WHERE id=?", (hook["id"],))
        for admin in rows("SELECT id FROM users WHERE workspace_id=? AND role='admin'", hook["workspace_id"]):
            # Every admin is told, including one whose own change set off the last failure.
            db.insert("notifications", workspace_id=hook["workspace_id"], user_id=admin["id"],
                      title="A webhook was paused", body=f"{hook['url']} failed {failures} times in a row."[:300],
                      url="/settings/api", created_at=now().isoformat(timespec="minutes"))
    db.commit()
    return False


def queue(pending):
    """Store a delivery for each webhook that wants each event, then try to send them now."""
    hooks = rows("SELECT * FROM webhooks WHERE workspace_id=? AND active=1", ws())
    if not hooks:
        return
    db = get_db()
    created = []
    for evt in pending:
        wanted = [h for h in hooks if evt["event"] in json.loads(h["events"])]
        if not wanted:
            continue
        body = json.dumps(payload(evt), default=str)
        for h in wanted:
            delivery_id = db.insert("webhook_deliveries", workspace_id=ws(), webhook_id=h["id"], event=evt["event"],
                                    payload=body, status="pending", attempts=0, next_attempt_at=utc_now().isoformat(),
                                    created_at=utc_now().isoformat())
            created.append((delivery_id, h))
    db.commit()
    started = time.monotonic()
    for delivery_id, h in created:
        if time.monotonic() - started > INLINE_BUDGET:
            break  # the cron job sends the rest
        if h["failures"] >= 3:
            continue  # a server that keeps failing shouldn't slow the page down; the cron job retries it
        deliver(one("SELECT * FROM webhook_deliveries WHERE id=?", delivery_id),
                one("SELECT * FROM webhooks WHERE id=?", h["id"]))


def retry_due(budget=40):
    """For the cron job: send deliveries that are due a retry. Also clears out deliveries over 30 days old."""
    started, sent = time.monotonic(), 0
    due = rows("SELECT * FROM webhook_deliveries WHERE status='pending' AND next_attempt_at <= ? ORDER BY id LIMIT 200",
               utc_now().isoformat())
    for d in due:
        if time.monotonic() - started > budget:
            break
        hook = one("SELECT * FROM webhooks WHERE id=?", d["webhook_id"])
        if hook is None or not hook["active"]:
            continue
        sent += deliver(d, hook)
    db = get_db()
    db.execute("DELETE FROM webhook_deliveries WHERE created_at < ?", ((utc_now() - timedelta(days=30)).isoformat(),))
    db.commit()
    return {"tried": len(due), "delivered": sent}


def register(app):
    app.add_template_filter(json.loads, "fromjson")

    @app.post("/settings/api/webhooks")
    def create_webhook():
        auth.admin_required()
        url = request.form.get("url", "").strip()
        chosen = [e for e in request.form.getlist("events") if e in EVENTS]
        problem = check_url(url)
        if problem:
            flash(f"Webhook not added. {problem}", "error")
        elif not chosen:
            flash("Webhook not added. Choose at least one event to send.", "error")
        elif scalar("SELECT COUNT(*) FROM webhooks WHERE workspace_id=?", ws()) >= MAX_HOOKS:
            flash(f"Webhook not added. A workspace can have up to {MAX_HOOKS}.", "error")
        else:
            db = get_db()
            db.insert("webhooks", workspace_id=ws(), url=url, events=json.dumps(chosen),
                      secret="whsec_" + secrets.token_hex(24), active=1, failures=0, created_by=g.user["name"],
                      created_at=now().isoformat(timespec="minutes"))
            db.commit()
            flash("Webhook added. Use its signing secret to check that requests come from CAE CRM.", "ok")
        return redirect(url_for("developers") + "#webhooks")

    def hook_or_404(hook_id):
        from flask import abort
        hook = one("SELECT * FROM webhooks WHERE id=? AND workspace_id=?", hook_id, ws())
        if hook is None:
            abort(404)
        return hook

    @app.post("/settings/api/webhooks/<int:hook_id>/delete")
    def delete_webhook(hook_id):
        auth.admin_required()
        hook_or_404(hook_id)
        db = get_db()
        db.execute("DELETE FROM webhook_deliveries WHERE webhook_id=?", (hook_id,))
        db.execute("DELETE FROM webhooks WHERE id=? AND workspace_id=?", (hook_id, ws()))
        db.commit()
        flash("Webhook removed.", "ok")
        return redirect(url_for("developers") + "#webhooks")

    @app.post("/settings/api/webhooks/<int:hook_id>/toggle")
    def toggle_webhook(hook_id):
        auth.admin_required()
        hook = hook_or_404(hook_id)
        db = get_db()
        db.execute("UPDATE webhooks SET active=?, failures=0 WHERE id=?", (0 if hook["active"] else 1, hook_id))
        db.commit()
        flash("Webhook paused." if hook["active"] else "Webhook turned back on.", "ok")
        return redirect(url_for("developers") + "#webhooks")

    @app.post("/settings/api/webhooks/<int:hook_id>/test")
    def test_webhook(hook_id):
        auth.admin_required()
        hook = hook_or_404(hook_id)
        body = json.dumps({"id": f"evt_{uuid.uuid4().hex}", "event": "ping", "created_at": utc_now().isoformat(),
                           "data": {"message": "A test from CAE CRM. Your webhook is set up."}}).encode()
        headers = {"Content-Type": "application/json", "User-Agent": "CAE-CRM-Webhooks/1", "CAE-Event": "ping",
                   "CAE-Delivery": "test", "CAE-Signature": sign(hook["secret"], body)}
        status, problem = post(hook["url"], headers, body)
        if status and 200 <= status < 300:
            flash(f"Test sent. Your server answered {status}.", "ok")
        else:
            flash(f"Test not delivered. {problem or f'Your server answered {status}.'}", "error")
        return redirect(url_for("developers") + "#webhooks")
