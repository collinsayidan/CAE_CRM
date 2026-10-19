"""The audit trail: who changed what, when and from where. Every successful change by a signed-in person is recorded
automatically, plus sign-ins and password resets. Admins see it under Settings and can download it.

Contacts are recorded by number, not name, so erasing someone under UK GDPR leaves no copy of their name here."""

import csv
import io

from flask import Response, current_app, g, render_template, request, session

import auth
from core import change_failed, now, rows, ws
from db import get_db

# What each change is called in the trail. Anything missing falls back to its endpoint name.
LABELS = {
    "create_contact": "Added a contact", "create_contact_for_company": "Added a contact", "edit_contact": "Edited a contact",
    "erase_contact": "Erased a contact's personal data", "create_company": "Added a company",
    "edit_company": "Edited a company", "delete_company": "Deleted a company", "create_deal": "Added a deal",
    "edit_deal": "Edited a deal", "delete_deal": "Deleted a deal", "move_deal": "Moved a deal to another stage",
    "add_line": "Added a line item", "edit_line": "Changed a line item", "create_ticket": "Opened a ticket",
    "edit_ticket": "Edited a ticket", "ticket_status": "Changed a ticket's status", "create_activity": "Added a task",
    "toggle_activity": "Ticked off or reopened a task", "log_engagement": "Logged a note, call, email or meeting",
    "delete_engagement": "Removed a timeline entry", "create_product": "Added a product", "update_product": "Changed a product",
    "update_project": "Updated a project", "create_invoice": "Raised an invoice", "invoice_deal": "Invoiced a deal",
    "mark_paid": "Marked an invoice paid", "email_invoice": "Emailed an invoice", "remind_invoice": "Sent a payment reminder", "invoice_to_xero": "Sent an invoice to Xero", "xero_push_all": "Sent invoices to Xero",
    "quote_deal": "Drafted a quote", "edit_quote": "Edited a quote", "send_quote": "Marked a quote as sent",
    "email_quote": "Emailed a quote", "invoice_quote": "Invoiced a quote", "delete_quote": "Deleted a quote",
    "create_form": "Created a web form", "web_form": "Changed a web form", "delete_form": "Deleted a web form",
    "create_campaign": "Started an email campaign draft", "campaign": "Edited an email campaign",
    "campaign_test": "Sent a test email", "campaign_start": "Sent an email campaign", "campaign_duplicate": "Copied an email campaign",
    "campaign_delete": "Deleted an email campaign draft", "bulk": "Changed several records at once",
    "imports": "Uploaded an import", "import_map": "Imported records", "save_view": "Saved a view", "delete_view": "Deleted a view",
    "settings": "Changed business settings", "auth.team": "Added a team member", "auth.edit_member": "Edited a team member's profile",
    "auth.change_role": "Changed a team member's role", "auth.reset_password": "Reset a team member's password",
    "auth.remove_user": "Removed a team member", "auth.account": "Changed their password",
    "auth.account_profile": "Edited their profile", "auth.login": "Signed in", "auth.reset": "Reset their password by email",
    "oauth_connect": "Started connecting an integration", "oauth_disconnect": "Disconnected an integration",
    "billing_checkout": "Opened checkout", "billing_portal": "Opened the billing portal", "vat_return": "Submitted a VAT return",
    "auth.two_factor_setup": "Turned on two-factor sign-in", "auth.two_factor_off": "Turned off two-factor sign-in",
    "auth.two_factor_reset": "Reset a team member's two-factor sign-in",
    "auth.two_factor_check": "Signed in with two-factor",
    "upload_file": "Attached a file", "delete_file": "Removed a file", "custom_fields_page": "Added a custom field",
    "delete_custom_field": "Removed a custom field", "workflows": "Added a workflow rule",
    "toggle_workflow": "Paused or resumed a workflow rule", "delete_workflow": "Removed a workflow rule",
    "create_api_key": "Made an API key", "revoke_api_key": "Revoked an API key", "create_webhook": "Added a webhook",
    "delete_webhook": "Removed a webhook", "toggle_webhook": "Paused or resumed a webhook",
    "test_webhook": "Sent a test webhook",
    "assistant_settings": "Turned the AI assistant on or off", "assistant_delete": "Deleted an assistant conversation",
    "assistant_delete_all": "Deleted all their assistant conversations",
    "auth.accept_invite": "Accepted their invite and signed in", "auth.resend_invite": "Sent an invite again",
    "auth.resend_verification": "Asked for a new email confirmation link", "auth.end_session": "Signed out a device",
    "auth.end_other_sessions": "Signed out everywhere else",
    "companies_house_refresh": "Updated a company from Companies House",
    "ticket_reply": "Replied to a ticket by email", "help_articles": "Changed a help article",
    "chat_settings": "Changed the website chat settings", "support_email_settings": "Changed the support email settings", "ai_triage_decide": "Applied or dismissed a triage suggestion", "account_summary": "Changed their daily summary email", "saved_replies_page": "Changed a saved reply",
    "restore_from_bin": "Restored a record from the recycle bin", "delete_from_bin": "Deleted a record permanently",
    "merge_duplicates": "Merged duplicate records", "dismiss_duplicates": "Marked two records as not duplicates",
    "add_tag": "Tagged a record", "remove_tag": "Removed a tag from a record", "tags_settings": "Changed a tag",
    "lose_deal": "Marked a deal as lost", "deal_reason": "Recorded why a deal was won or lost",
}
# Routine or high-volume actions that would bury the changes that matter.
# Asking the assistant (or its helpers) changes no records, and a confirmed suggestion is recorded by the page it's
# passed on to.
SKIP = {"auth.logout", "oauth_sync", "campaign_deliver", "auth.forgot", "assistant_ask", "assistant_confirm",
        "ai_helper", "ai_draft", "ai_triage"}
# Pages that sign someone in: the person comes from the new session, not from before the request.
SIGN_IN_ENDPOINTS = {"auth.login", "auth.reset", "auth.signup", "auth.two_factor_check", "auth.accept_invite"}
# How to name the record a change was about: URL argument -> (type, SQL for a name, or None to record a number only).
TARGETS = {
    "company_id": ("Company", "SELECT name FROM companies WHERE id=? AND workspace_id=?"),
    "deal_id": ("Deal", "SELECT title FROM deals WHERE id=? AND workspace_id=?"),
    "ticket_id": ("Ticket", "SELECT subject FROM tickets WHERE id=? AND workspace_id=?"),
    "quote_id": ("Quote", "SELECT number FROM quotes WHERE id=? AND workspace_id=?"),
    "invoice_id": ("Invoice", "SELECT number FROM invoices WHERE id=? AND workspace_id=?"),
    "user_id": ("Team member", "SELECT name FROM users WHERE id=? AND workspace_id=?"),
    "form_id": ("Web form", "SELECT name FROM web_forms WHERE id=? AND workspace_id=?"),
    "campaign_id": ("Campaign", "SELECT name FROM email_campaigns WHERE id=? AND workspace_id=?"),
    "product_id": ("Product", "SELECT name FROM products WHERE id=? AND workspace_id=?"),
    "contact_id": ("Contact", None),
}


def record(workspace_id, user, action, target_type=None, target_id=None, summary=None):
    from quotes import client_ip
    db = get_db()
    db.insert("audit_events", workspace_id=workspace_id, user_id=user["id"] if user else None,
              user_name=user["name"] if user else None, action=action, target_type=target_type, target_id=target_id,
              summary=(summary or "")[:200] or None, ip=client_ip(), created_at=now().isoformat(timespec="seconds"))
    db.commit()


def register(app):

    @app.before_request
    def note_target():
        """Name the record before the change, so a deleted record can still be described afterwards."""
        g.audit_target = None
        if request.method != "POST" or not g.get("user") or not request.view_args:
            return
        for arg, value in request.view_args.items():
            if arg in TARGETS:
                kind, sql = TARGETS[arg]
                name = None
                if sql:
                    found = get_db().execute(sql, (value, g.user["workspace_id"])).fetchone()
                    name = found[0] if found else None
                g.audit_target = (kind, value, name)
                return

    @app.after_request
    def write_trail(response):
        endpoint = request.endpoint
        if request.method != "POST" or response.status_code >= 400 or endpoint in SKIP or endpoint is None:
            return response
        if change_failed():
            return response  # the page said it didn't work, so nothing changed
        try:
            user = g.get("user")
            if endpoint in SIGN_IN_ENDPOINTS and not user and session.get("user_id"):
                user = get_db().execute("SELECT id, name, workspace_id FROM users WHERE id=?",
                                        (session["user_id"],)).fetchone()
            if not user or (endpoint == "auth.login" and response.status_code != 302):
                return response
            target = g.get("audit_target")
            if endpoint == "bulk":
                ids = request.form.getlist("ids")
                summary = f"{request.form.get('action', 'change')} on {len(ids)} {request.view_args.get('obj', 'records')}"
                target = ("Records", None, summary)
            record(user["workspace_id"], user, LABELS.get(endpoint, endpoint.replace("_", " ").capitalize()),
                   target[0] if target else None, target[1] if target else None, target[2] if target else None)
        except Exception:  # the trail must never break the change it records
            current_app.logger.exception("Audit trail entry not written")
        return response

    @app.route("/audit")
    def audit_trail():
        auth.admin_required()
        person, action = request.args.get("person", ""), request.args.get("action", "")
        sql = "SELECT * FROM audit_events WHERE workspace_id=?"
        args = [ws()]
        if person.isdigit():
            sql += " AND user_id=?"
            args.append(int(person))
        if action:
            sql += " AND action=?"
            args.append(action)
        events = rows(sql + " ORDER BY id DESC LIMIT 500", *args)
        if request.args.get("format") == "csv":
            out = io.StringIO()
            w = csv.writer(out)
            w.writerow(["When (UK time)", "Who", "Did", "Record type", "Record number", "Record", "IP address"])
            for e in events:
                w.writerow([e["created_at"], e["user_name"], e["action"], e["target_type"] or "", e["target_id"] or "",
                            e["summary"] or "", e["ip"] or ""])
            return Response("﻿" + out.getvalue(), mimetype="text/csv",
                            headers={"Content-Disposition": "attachment; filename=audit-trail.csv"})
        people = rows("SELECT DISTINCT user_id, user_name FROM audit_events WHERE workspace_id=? AND user_id IS NOT NULL "
                      "ORDER BY user_name", ws())
        actions = [r[0] for r in rows("SELECT DISTINCT action FROM audit_events WHERE workspace_id=? ORDER BY action", ws())]
        return render_template("audit.html", events=events, people=people, actions=actions, person=person, action=action)
