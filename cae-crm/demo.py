"""Try CAE CRM without signing up: each visitor gets their own sample workspace, deleted after a day.

A demo is an ordinary workspace with `demo_until` set, filled with the same made-up UK data as sign-up's sample data.
Anything that reaches outside the app is switched off in it: email, integrations, payments, API keys and webhooks,
public pages a visitor could edit (web forms, help articles, business details) and the AI features, which cost money.
Each network can start a few demos an hour, and the daily job deletes demos that have run out."""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app, flash, g, jsonify, redirect, request, session, url_for

from db import get_db

HOURS = 24
PER_NETWORK_PER_HOUR = 5
MAX_ACTIVE = 200
VISITOR = "Alex Morgan"
MESSAGE = "That's switched off in the demo. Create your own workspace to use it."

# Changes a demo can't make, by endpoint.
BLOCKED = {
    # Sends email
    "campaign_deliver", "campaign_start", "campaign_test", "email_invoice", "email_quote", "send_quote", "remind_invoice",
    "ticket_reply", "auth.team", "auth.resend_invite", "auth.resend_verification",
    # The visitor's own account
    "auth.account", "auth.account_profile", "auth.edit_member", "auth.change_role", "auth.remove_user",
    "auth.reset_password", "auth.two_factor_setup", "auth.two_factor_off", "auth.two_factor_reset",
    # Money and connected services
    "billing_checkout", "billing_portal", "payment_settings", "stripe_disconnect", "oauth_connect", "oauth_disconnect",
    "oauth_sync", "invoice_to_xero", "xero_push_all", "vat_return", "companies_house_refresh", "recurring_invoices",
    # Reaches other systems, or publishes pages on our domain
    "create_api_key", "create_webhook", "test_webhook", "toggle_webhook", "create_form", "web_form", "help_articles",
    "chat_settings", "support_email_settings", "settings", "upload_file",
    # AI, which costs money per question
    "assistant_ask", "assistant_confirm", "assistant_settings", "ai_draft", "ai_helper", "ai_triage", "ai_triage_decide",
    "account_summary", "ai_campaign",
}


def now_utc():
    return datetime.now(timezone.utc)


def network():
    """The visitor's IP address, scrambled with the app's secret: enough to count demos, useless for anything else."""
    key = (current_app.config.get("SECRET_KEY") or "").encode()
    return hmac.new(key, (request.remote_addr or "").encode(), hashlib.sha256).hexdigest()[:24]


def is_demo(workspace_id):
    row = get_db().execute("SELECT demo_until FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
    return bool(row and row["demo_until"])


def guard():
    """Run on every signed-in request: marks demos (g.demo) and stops the changes they can't make."""
    g.demo = bool(g.get("user")) and is_demo(g.user["workspace_id"])
    if not g.demo or request.method != "POST" or request.endpoint not in BLOCKED:
        return None
    if request.headers.get("X-Requested-With") == "fetch" or request.path.startswith("/api/"):
        return jsonify(error=MESSAGE), 403
    flash(MESSAGE, "error")
    target = request.referrer or ""
    return redirect(target if target.startswith(request.host_url) else url_for("overview"))


def purge(workspace_ids=None):
    """Delete demos that have run out (or the ones given), with everything in them. Returns how many."""
    db = get_db()
    if workspace_ids is None:
        workspace_ids = [r["id"] for r in db.execute(
            "SELECT id FROM workspaces WHERE demo_until IS NOT NULL AND demo_until < ?",
            (now_utc().isoformat(timespec="seconds"),)).fetchall()]
    ids = [int(i) for i in workspace_ids]
    if not ids:
        return 0
    from move_database import tables
    marks = ", ".join("?" * len(ids))
    user_ids = [r["id"] for r in db.execute(f"SELECT id FROM users WHERE workspace_id IN ({marks})", ids).fetchall()]
    # Children before parents: tables are defined parents first, so go in reverse.
    for table in reversed(tables()):
        cols = db.columns(table)
        if table in ("workspaces", "users"):
            continue
        if "workspace_id" in cols:
            db.execute(f"DELETE FROM {table} WHERE workspace_id IN ({marks})", ids)
        elif "user_id" in cols and user_ids:
            db.execute(f"DELETE FROM {table} WHERE user_id IN ({', '.join('?' * len(user_ids))})", user_ids)
    db.execute(f"DELETE FROM users WHERE workspace_id IN ({marks})", ids)
    db.execute(f"DELETE FROM workspaces WHERE id IN ({marks}) AND demo_until IS NOT NULL", ids)
    db.commit()
    return len(ids)


def register(app):
    @app.post("/demo")
    def start_demo():
        """Start a demo: a private sample workspace, signed in as its admin."""
        if g.get("user"):
            return redirect(url_for("overview"))
        purge()
        db, now = get_db(), now_utc()
        net = network()
        started_lately = db.execute("SELECT COUNT(*) FROM workspaces WHERE demo_ip=? AND demo_until > ?",
                                    (net, (now + timedelta(hours=HOURS - 1)).isoformat(timespec="seconds"))).fetchone()[0]
        active = db.execute("SELECT COUNT(*) FROM workspaces WHERE demo_until IS NOT NULL").fetchone()[0]
        if started_lately >= PER_NETWORK_PER_HOUR or active >= MAX_ACTIVE:
            flash("Lots of demos have been started recently. Please try again in an hour, or create a workspace.", "error")
            return redirect(url_for("auth.login"))  # the homepage shows no messages; sign-in has both choices
        import auth
        from core import today
        from seed import seed_workspace
        t = today()
        ws_id = auth.create_workspace(db, "Thistle & Co Ltd", t)
        db.execute("UPDATE workspaces SET demo_until=?, demo_ip=?, onboarding_done=1 WHERE id=?",
                   ((now + timedelta(hours=HOURS)).isoformat(timespec="seconds"), net, ws_id))
        user_id = auth.create_user(db, ws_id, VISITOR, f"demo-{secrets.token_hex(8)}@demo.invalid",
                                   secrets.token_urlsafe(24), "admin", verified=True)
        seed_workspace(db, ws_id, t, VISITOR, auth.DEFAULT_MONTHLY_TARGET)
        db.commit()
        auth.start_session(user_id)
        flash("You're in a demo with made-up data. Click around and change anything you like.", "ok")
        return redirect(url_for("overview"))

    @app.post("/demo/leave")
    def leave_demo():
        """End the demo now: delete it and go to sign-up."""
        user = g.get("user")
        if user and g.get("demo"):
            ws_id = user["workspace_id"]
            session.clear()
            purge([ws_id])
        return redirect(url_for("auth.signup"))
