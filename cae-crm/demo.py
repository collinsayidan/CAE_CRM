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

# The wording people agree to is kept on their contact's timeline, as a record of their consent.
CONSENT_EMAIL = "Email me CAE CRM news and offers."
CONSENT_ADS = "Show me CAE CRM ads on Facebook, Instagram and LinkedIn. We'd share a scrambled copy of your email with them to do it."
TAG_DEMO = "Demo"
TAG_ADS = "Social ads OK"

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


def record_lead(email, email_updates, social_ads):
    """Add the visitor to the leads workspace (CAE_LEADS_WORKSPACE, Collinalitics' own) as a contact, with what they
    agreed to. Their consent wording goes on the timeline; "Social ads OK" marks who may be added to ad audiences."""
    leads_ws = current_app.config.get("LEADS_WORKSPACE")
    if not leads_ws:
        return None
    from core import log_event, now, today
    import tags
    db = get_db()
    owner = db.execute("SELECT name FROM users WHERE workspace_id=? AND role='admin' ORDER BY id LIMIT 1",
                       (leads_ws,)).fetchone()
    if not owner:
        return None
    g.public_workspace = leads_ws
    try:
        t = today().isoformat()
        contact = db.execute("SELECT * FROM contacts WHERE workspace_id=? AND email=?", (leads_ws, email)).fetchone()
        if contact:
            contact_id = contact["id"]
            if email_updates and not contact["marketing_consent"]:
                db.execute("UPDATE contacts SET marketing_consent=1, consent_date=?, unsubscribed_at=NULL WHERE id=?",
                           (t, contact_id))
        else:
            local = email.split("@")[0].replace("_", ".").replace("-", ".")
            parts = [p.capitalize() for p in local.split(".") if p.isalpha()] or [local[:60]]
            # Following up someone who asked to try the product is a legitimate interest; marketing needs their opt-in.
            contact_id = db.insert("contacts", workspace_id=leads_ws, first_name=parts[0][:60],
                                   last_name=" ".join(parts[1:])[:60], email=email, phone="",
                                   lawful_basis="Legitimate interests", marketing_consent=int(email_updates),
                                   consent_date=t if email_updates else None, lifecycle_stage="Lead", lead_status="New",
                                   owner=owner["name"], created_at=t)
        tags.add("contact", contact_id, TAG_DEMO)
        if social_ads:
            tags.add("contact", contact_id, TAG_ADS)
        agreed = [f'"{text}"' for on, text in ((email_updates, CONSENT_EMAIL), (social_ads, CONSENT_ADS)) if on]
        body = ("Agreed at " + now().isoformat(timespec="minutes") + ": " + "; ".join(agreed)) if agreed             else "Didn't tick either marketing box."
        log_event("Tried the demo", body, contact_id=contact_id)
        db.commit()
        return contact_id
    finally:
        g.pop("public_workspace", None)
        g.pop("workspace", None)


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
    import os
    leads = os.environ.get("CAE_LEADS_WORKSPACE", "")
    app.config.setdefault("LEADS_WORKSPACE", int(leads) if leads.isdigit() else None)

    @app.route("/demo", methods=["GET", "POST"])
    def start_demo():
        """Ask for an email, then start a demo: a private sample workspace, signed in as its admin."""
        if g.get("user"):
            return redirect(url_for("overview"))
        from flask import render_template
        import auth
        form, errors = request.form, {}
        page = lambda: (render_template("auth/demo.html", form=form, errors=errors, consent_email=CONSENT_EMAIL,
                                        consent_ads=CONSENT_ADS), 422 if errors else 200)
        if request.method == "GET":
            return page()
        email = form.get("email", "").strip().lower()[:200]
        if not auth.valid_email(email):
            errors["email"] = "Enter your email address to open the demo."
            return page()
        purge()
        db, now = get_db(), now_utc()
        net = network()
        started_lately = db.execute("SELECT COUNT(*) FROM workspaces WHERE demo_ip=? AND demo_until > ?",
                                    (net, (now + timedelta(hours=HOURS - 1)).isoformat(timespec="seconds"))).fetchone()[0]
        active = db.execute("SELECT COUNT(*) FROM workspaces WHERE demo_until IS NOT NULL").fetchone()[0]
        if started_lately >= PER_NETWORK_PER_HOUR or active >= MAX_ACTIVE:
            flash("Lots of demos have been started recently. Please try again in an hour, or create a workspace.", "error")
            return redirect(url_for("auth.login"))  # the homepage shows no messages; sign-in has both choices
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
        record_lead(email, form.get("email_updates") == "on", form.get("social_ads") == "on")
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
