"""Email-to-ticket: customers' emails to a business's support address become tickets, and their replies thread back
into the ticket they belong to.

Resend receives the email (at CAE_INBOUND_DOMAIN) and sends an email.received event to the signed Resend webhook; the
message itself is then fetched from Resend's Receiving API. Each workspace that switches this on gets a private
address, support-<token>@<domain>, to forward its own support mailbox to. Replies sent from a ticket carry a reply-to
address for that ticket, support-<token>+<ticket id>@<domain>, so the customer's answer lands back on it; a "[#214]"
in the subject from the ticket's contact also matches.

Auto-replies, bounces and our own email are ignored, each received email is handled once, and there are limits per
sender and per workspace. Tests set INBOUND_BACKEND to a fake with request(path) returning Resend's JSON, and
download(url) returning bytes."""

import hashlib
import hmac
import json
import os
import re
import secrets
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from email.utils import parseaddr

from flask import abort, current_app, flash, g, redirect, render_template, request, url_for

import auth
from core import log_event, now, one, rows, workspace, ws
from db import get_db
from events import emit

API = "https://api.resend.com"
ADDRESS = re.compile(r"^support-([a-z0-9]{8,16})(?:\+(\d{1,10})-([a-f0-9]{8}))?@(.+)$", re.I)
SUBJECT_TICKET = re.compile(r"\[#(\d{1,10})\]")
REOPEN_WITHIN = timedelta(days=14)
PER_SENDER_HOUR = 20
PER_WORKSPACE_DAY = 500
MAX_BODY = 10_000
FREE_DOMAINS = {"gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "hotmail.co.uk", "live.com", "live.co.uk",
                "yahoo.com", "yahoo.co.uk", "icloud.com", "me.com", "aol.com", "btinternet.com", "sky.com",
                "virginmedia.com", "talktalk.net", "protonmail.com", "proton.me", "msn.com", "mail.com"}
QUOTE_STARTS = (re.compile(r"^On .{0,200} wrote:\s*$", re.I), re.compile(r"^-{2,}\s*Original Message\s*-{2,}", re.I),
                re.compile(r"^From:\s.+", re.I), re.compile(r"^Sent from my ", re.I), re.compile(r"^-- ?$"),
                re.compile(r"^_{5,}$"))


class InboundError(Exception):
    pass


# --- Setup --------------------------------------------------------------------------------------------------------------

def domain():
    return (current_app.config.get("INBOUND_DOMAIN") or "").strip().lower()


def configured():
    import mail
    return bool(domain()) and mail.configured()


def ticket_sig(token, ticket_id):
    """A short signature, so a ticket's reply address can't be guessed from another ticket's."""
    key = current_app.config["SECRET_KEY"].encode()
    return hmac.new(key, f"inbound:{token}:{ticket_id}".encode(), hashlib.sha256).hexdigest()[:8]


def address_for(w, ticket_id=None):
    if not (w["inbound_token"] and domain()):
        return None
    plus = f"+{ticket_id}-{ticket_sig(w['inbound_token'], ticket_id)}" if ticket_id else ""
    return f"support-{w['inbound_token']}{plus}@{domain()}"


def reply_to_for(ticket):
    """Where a customer's reply to a ticket email should go: back to the ticket, when email-to-ticket is on."""
    w = workspace()
    if configured() and w["inbound_on"]:
        return address_for(w, ticket["id"])
    return w["reply_to"]


# --- Talking to Resend --------------------------------------------------------------------------------------------------

def call(path):
    fake = current_app.config.get("INBOUND_BACKEND")
    if fake:
        return fake.request(path)
    req = urllib.request.Request(API + path, headers={"Authorization": f"Bearer {current_app.config['RESEND_API_KEY']}",
                                                      "User-Agent": "CAE-CRM"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as e:
        raise InboundError(f"Couldn't fetch the email from Resend: {e}") from None


def download(url, limit):
    fake = current_app.config.get("INBOUND_BACKEND")
    if fake:
        return fake.download(url)[:limit + 1]
    req = urllib.request.Request(url, headers={"User-Agent": "CAE-CRM"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read(limit + 1)


# --- Reading an email ---------------------------------------------------------------------------------------------------

def plain_text(email):
    text = email.get("text") or ""
    if not text.strip() and email.get("html"):
        html = re.sub(r"(?is)<(script|style).*?</\1>", "", email["html"])
        html = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", html)
        text = re.sub(r"<[^>]+>", "", html)
        for entity, char in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
            text = text.replace(entity, char)
    return text.replace("\r\n", "\n")


def new_part(text):
    """The message without the quoted earlier messages and signature below it."""
    keep = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith(">") or any(p.match(stripped) for p in QUOTE_STARTS):
            break
        keep.append(line.rstrip())
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(keep)).strip()
    return (out or text.strip())[:MAX_BODY]


def header(email, name):
    headers = email.get("headers") or {}
    if isinstance(headers, list):  # [{name, value}] in some payloads
        headers = {h.get("name", ""): h.get("value", "") for h in headers if isinstance(h, dict)}
    for k, v in headers.items():
        if k.lower() == name.lower():
            return str(v)
    return ""


def is_automatic(email, sender):
    local = sender.split("@")[0].lower()
    if local in ("mailer-daemon", "postmaster") or local.startswith(("noreply", "no-reply", "donotreply", "do-not-reply")):
        return True
    auto = header(email, "Auto-Submitted").lower()
    if auto and auto != "no":
        return True
    if header(email, "X-Autoreply") or header(email, "X-Autorespond"):
        return True
    return header(email, "Precedence").lower() in ("bulk", "junk", "list", "auto_reply")


def authentication_failed(email):
    auth_ = email.get("authentication") or {}
    results = {k: str((v or {}).get("result") if isinstance(v, dict) else v).lower() for k, v in auth_.items()}
    return results.get("dmarc") == "fail" or (results.get("spf") == "fail" and results.get("dkim") == "fail")


# --- Turning it into a ticket -------------------------------------------------------------------------------------------

def target(addresses):
    """(workspace, ticket id or None) from the addresses an email was sent to."""
    for raw in addresses:
        m = ADDRESS.match(parseaddr(str(raw))[1].strip().lower())
        if m and m.group(4) == domain():
            w = one("SELECT * FROM workspaces WHERE inbound_token=? AND inbound_on=1", m.group(1))
            if w:
                ticket_id = int(m.group(2)) if m.group(2) else None
                if ticket_id and not hmac.compare_digest(m.group(3), ticket_sig(w["inbound_token"], ticket_id)):
                    ticket_id = None  # a made-up ticket address: treat it as a new email to the workspace
                return w, ticket_id
    return None, None


def contact_for(sender, display_name, owner):
    """The sender's contact in this workspace, made if they're new. Returns (contact row, created?)."""
    found = one("SELECT * FROM contacts WHERE workspace_id=? AND LOWER(email)=?", ws(), sender)
    if found:
        return found, False
    name = (display_name or "").strip().strip('"') or sender.split("@")[0].replace(".", " ").replace("_", " ")
    parts = name.split()
    first, last = (parts[0].title(), " ".join(parts[1:]).title() or "(unknown)") if parts else ("Unknown", "(unknown)")
    domain_ = sender.split("@")[-1]
    company_id = None
    if domain_ not in FREE_DOMAINS:
        for c in rows("SELECT id, website FROM companies WHERE workspace_id=? AND website IS NOT NULL AND website <> ''", ws()):
            host = re.sub(r"^https?://", "", c["website"].lower()).split("/")[0].removeprefix("www.")
            if host == domain_ or domain_.endswith("." + host):
                company_id = c["id"]
                break
    db = get_db()
    contact_id = db.insert("contacts", workspace_id=ws(), company_id=company_id, first_name=first[:60], last_name=last[:60],
                           email=sender, lawful_basis="Legitimate interests", marketing_consent=0, lifecycle_stage="Lead",
                           lead_status="New", owner=owner, created_at=now().date().isoformat())
    log_event("Contact created", "From an email to the support address", contact_id=contact_id, company_id=company_id)
    emit("contact.created", contact_id)
    return one("SELECT * FROM contacts WHERE id=?", contact_id), True


def default_owner(w):
    team = [r[0] for r in rows("SELECT name FROM users WHERE workspace_id=? ORDER BY role='admin' DESC, id", w["id"])]
    return w["inbound_owner"] if w["inbound_owner"] in team else (team[0] if team else "CAE CRM")


def matching_ticket(w, plus_id, email, sender):
    """The open (or recently closed) ticket this email replies to, if any."""
    candidates = []
    if plus_id:
        candidates.append(plus_id)
    m = SUBJECT_TICKET.search(email.get("subject") or "")
    if m:
        candidates.append(int(m.group(1)))
    for ref in re.findall(r"<[^>]+>", header(email, "In-Reply-To") + " " + header(email, "References")):
        found = one("SELECT ticket_id FROM inbound_emails WHERE workspace_id=? AND message_id=?", w["id"], ref)
        if found:
            candidates.append(found[0])
    for ticket_id in candidates:
        t = one("SELECT t.*, ct.email AS contact_email FROM tickets t LEFT JOIN contacts ct ON ct.id=t.contact_id "
                "WHERE t.id=? AND t.workspace_id=?", ticket_id, w["id"])
        if t is None:
            continue
        if ticket_id != plus_id and (t["contact_email"] or "").lower() != sender:
            continue  # a subject or header match only counts from the ticket's own contact
        return t
    return None


def save_attachments(email_id, items, ticket_id, uploader):
    """Save allowed attachments to the ticket. Returns (saved names, skipped names)."""
    import files
    saved, skipped = [], []
    for a in items:
        name = os.path.basename(str(a.get("filename") or "attachment").replace("\\", "/")).lstrip(". ")[:150] or "attachment"
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if (a.get("content_disposition") or "attachment") == "inline" and (a.get("content_id")):
            continue  # pictures inside the email, such as logos in a signature
        if ext not in files.ALLOWED or int(a.get("size") or 0) > files.MAX_BYTES or not a.get("download_url"):
            skipped.append(name)
            continue
        try:
            data = download(a["download_url"], files.MAX_BYTES)
            if len(data) > files.MAX_BYTES:
                skipped.append(name)
                continue
            key = f"{ws()}/ticket/{ticket_id}/{secrets.token_hex(8)}-{name}"
            content = files.put(key, data, a.get("content_type") or "application/octet-stream")
        except (urllib.error.URLError, TimeoutError, OSError, files.StorageError):
            skipped.append(name)
            continue
        get_db().insert("attachments", workspace_id=ws(), record_type="ticket", record_id=ticket_id, filename=name,
                        content_type=a.get("content_type") or "application/octet-stream", size=len(data), storage_key=key,
                        content=content, uploaded_by=uploader, created_at=now().isoformat(timespec="minutes"))
        saved.append(name)
    return saved, skipped


def receive(event_data):
    """Handle one email.received event. Returns what happened, in a word, for the webhook's log."""
    email_id = event_data.get("email_id") or event_data.get("id")
    if not email_id:
        return "no id"
    w, plus_id = target((event_data.get("to") or []) + (event_data.get("cc") or []) +
                        ([event_data["received_for"]] if isinstance(event_data.get("received_for"), str)
                         else event_data.get("received_for") or []))
    if w is None:
        return "not ours"
    g.public_workspace = w["id"]
    g.pop("workspace", None)
    db = get_db()
    if one("SELECT 1 FROM inbound_emails WHERE provider_id=?", email_id):
        return "duplicate"
    email = call(f"/emails/receiving/{email_id}")
    display, sender = parseaddr(str(email.get("from") or event_data.get("from") or ""))
    sender = sender.strip().lower()
    our_sender = parseaddr(current_app.config.get("MAIL_FROM") or "")[1].lower()
    stamp = now().isoformat(timespec="minutes")

    def note(outcome, ticket_id=None):
        db.insert("inbound_emails", workspace_id=w["id"], provider_id=email_id, message_id=email.get("message_id"),
                  sender=sender[:200], ticket_id=ticket_id, outcome=outcome, created_at=stamp)
        db.commit()
        return outcome

    if not sender or "@" not in sender or sender == our_sender or sender.endswith("@" + domain()) or is_automatic(email, sender):
        return note("ignored")
    subject = (email.get("subject") or "").strip()[:200] or "(no subject)"
    body = new_part(plain_text(email))
    warning = " The sender's email address couldn't be verified, so check it's genuine before acting." \
        if authentication_failed(email) else ""
    existing = matching_ticket(w, plus_id, email, sender)
    reopen = existing and (existing["status"] != "Closed" or
                           datetime.fromisoformat(existing["closed_at"]) >= now() - REOPEN_WITHIN)
    from crm import notify_owner
    if reopen:
        t = existing
        log_event(subject, body + (f"\n\n{warning.strip()}" if warning else ""), kind="email", author=display or sender,
                  ticket_id=t["id"], contact_id=t["contact_id"], company_id=t["company_id"])
        if t["status"] != "Waiting on us":
            from service import set_ticket_status
            set_ticket_status(t["id"], "Waiting on us")
        notify_owner(t["owner"], f"{display or sender} replied on ticket #{t['id']}", body[:200],
                     url_for("ticket", ticket_id=t["id"]))
        saved, skipped = save_attachments(email_id, call(f"/emails/receiving/{email_id}/attachments").get("data") or []
                                          if email.get("attachments") else [], t["id"], display or sender)
        _note_files(t, saved, skipped)
        return note("replied", t["id"])
    # A new ticket, within the limits.
    hour_ago = (now() - timedelta(hours=1)).isoformat(timespec="minutes")
    day_ago = (now() - timedelta(days=1)).isoformat(timespec="minutes")
    if one("SELECT COUNT(*) FROM inbound_emails WHERE workspace_id=? AND sender=? AND outcome='opened' AND created_at >= ?",
           w["id"], sender, hour_ago)[0] >= PER_SENDER_HOUR or \
            one("SELECT COUNT(*) FROM inbound_emails WHERE workspace_id=? AND outcome='opened' AND created_at >= ?",
                w["id"], day_ago)[0] >= PER_WORKSPACE_DAY:
        return note("limited")
    owner = default_owner(w)
    contact, _ = contact_for(sender, display, owner)
    from service import sla_due
    opened = now()
    first_due, resolve_due = sla_due(opened, "Medium")
    earlier = f"Follows on from ticket #{existing['id']}, closed on {existing['closed_at'][:10]}.\n\n" if existing else ""
    ticket_id = db.insert("tickets", workspace_id=w["id"], company_id=contact["company_id"], contact_id=contact["id"],
                          subject=re.sub(r"^\s*((re|fw|fwd)\s*:\s*)+", "", subject, flags=re.I) or subject,
                          description=(earlier + body)[:MAX_BODY], status="New", priority="Medium", category="Other",
                          source="Email", owner=owner, created_at=opened.isoformat(timespec="minutes"),
                          first_response_due=first_due, resolution_due=resolve_due)
    t = one("SELECT * FROM tickets WHERE id=?", ticket_id)
    log_event("Ticket opened", f"From an email by {display or sender} <{sender}>.{warning}", ticket_id=ticket_id,
              company_id=t["company_id"], contact_id=t["contact_id"])
    log_event(subject, body, kind="email", author=display or sender, ticket_id=ticket_id, contact_id=t["contact_id"],
              company_id=t["company_id"])
    notify_owner(owner, f"New ticket #{ticket_id} by email: {t['subject']}", f"From {display or sender}",
                 url_for("ticket", ticket_id=ticket_id))
    emit("ticket.created", ticket_id, value="Medium")
    saved, skipped = save_attachments(email_id, call(f"/emails/receiving/{email_id}/attachments").get("data") or []
                                      if email.get("attachments") else [], ticket_id, display or sender)
    _note_files(t, saved, skipped)
    return note("opened", ticket_id)


def _note_files(t, saved, skipped):
    if saved or skipped:
        log_event("Attachments from the email",
                  ". ".join(filter(None, [f"Saved to Files: {', '.join(saved)}" if saved else None,
                                          f"Not saved (too big or a type that isn't allowed): {', '.join(skipped)}"
                                          if skipped else None])) + ".",
                  ticket_id=t["id"], company_id=t["company_id"], contact_id=t["contact_id"])


# --- Settings -----------------------------------------------------------------------------------------------------------

def register(app):
    app.config.setdefault("INBOUND_DOMAIN", os.environ.get("CAE_INBOUND_DOMAIN", ""))
    app.config.setdefault("INBOUND_BACKEND", None)
    app.add_template_global(configured, "inbound_configured")
    app.add_template_global(address_for, "inbound_address")

    @app.route("/settings/support-email", methods=["GET", "POST"])
    def support_email_settings():
        auth.admin_required()
        if not configured():
            abort(404)
        w = workspace()
        team = [r[0] for r in rows("SELECT name FROM users WHERE workspace_id=? ORDER BY name", ws())]
        if request.method == "POST":
            on = request.form.get("enabled") == "on"
            owner = request.form.get("owner") if request.form.get("owner") in team else default_owner(w)
            token = w["inbound_token"] or secrets.token_hex(5)
            get_db().execute("UPDATE workspaces SET inbound_on=?, inbound_owner=?, inbound_token=? WHERE id=?",
                             (int(on), owner, token, ws()))
            get_db().commit()
            flash("Saved. Forward your support mailbox to the address below." if on else "Email-to-ticket is off.", "ok")
            return redirect(url_for("support_email_settings"))
        recent = rows("SELECT * FROM inbound_emails WHERE workspace_id=? ORDER BY id DESC LIMIT 10", ws())
        return render_template("support_email.html", w=w, team=team, owner=default_owner(w), recent=recent,
                               address=address_for(w))
