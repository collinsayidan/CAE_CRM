"""Read full conversations on demand from the user's own mailbox; keep no body copies."""

import base64
import re
import secrets
import mail
from email.message import EmailMessage
from urllib.parse import quote
from flask import abort, current_app, flash, g, redirect, render_template, request, url_for
from core import get_or_404, log_event, one, rows, ws
from db import get_db
from integrations import IntegrationError, access_token, http
from mailsync import addresses


def mine(conn_id):
    c = one(
        "SELECT * FROM connections WHERE id=? AND workspace_id=? AND user_id=? AND provider IN ('google','microsoft')",
        conn_id,
        ws(),
        g.user["id"],
    )
    if not c:
        abort(404)
    return c


def allowed(conn, feature):
    scopes = (conn["granted_scopes"] or "").split()
    required = {
        "google": {
            "send": "https://www.googleapis.com/auth/gmail.send",
            "calendar": "https://www.googleapis.com/auth/calendar.events",
        },
        "microsoft": {"send": "Mail.Send", "calendar": "Calendars.ReadWrite"},
    }
    return required[conn["provider"]][feature] in scopes


def plain_body(payload):
    if payload.get("mimeType") == "text/plain" or (
        not payload.get("mimeType") and (payload.get("body") or {}).get("data")
    ):
        data = (payload.get("body") or {}).get("data", "")
        try:
            return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")[
                :100000
            ]
        except ValueError:
            return "Message body could not be decoded."
    bodies = [plain_body(p) for p in payload.get("parts", []) if p.get("mimeType") != "text/html"]
    return (
        "\n".join(bodies).strip()
        or "This message has no plain-text body. Open it in your mailbox to view its formatting or attachments."
    )


def conversation(conn, contact):
    email = (contact["email"] or "").lower()
    if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+", email):
        raise IntegrationError("This contact needs a valid email address.")
    token = access_token(conn)
    headers = {"Authorization": f"Bearer {token}"}
    out = []
    if conn["provider"] == "google":
        data = http(
            "GET",
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers=headers,
            params={"q": f"from:({email}) OR to:({email})", "maxResults": 30},
        )
        for ref in data.get("messages", []):
            m = http(
                "GET",
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/" + quote(ref["id"], safe=""),
                headers=headers,
                params={"format": "full"},
            )
            p = m.get("payload") or {}
            h = {v["name"].lower(): v["value"] for v in p.get("headers", [])}
            if email not in addresses(h.get("from", "")) + addresses(h.get("to", "")) + addresses(
                h.get("cc", "")
            ):
                continue
            out.append(
                dict(
                    subject=h.get("subject", "(No subject)"),
                    sender=h.get("from", ""),
                    when=h.get("date", ""),
                    body=plain_body(p),
                    thread=m.get("threadId", m["id"]),
                )
            )
    else:
        headers["Prefer"] = 'outlook.body-content-type="text"'
        data = http(
            "GET",
            "https://graph.microsoft.com/v1.0/me/messages",
            headers=headers,
            params={
                "$search": '"participants:' + email + '"',
                "$top": 30,
                "$select": "id,subject,from,toRecipients,ccRecipients,receivedDateTime,body,conversationId",
            },
        )
        for m in data.get("value", []):
            sender = ((m.get("from") or {}).get("emailAddress") or {}).get("address", "")
            recipients = [
                (r.get("emailAddress") or {}).get("address", "").lower()
                for r in m.get("toRecipients", []) + m.get("ccRecipients", [])
            ]
            if email not in [sender.lower(), *recipients]:
                continue
            body = m.get("body") or {}
            out.append(
                dict(
                    subject=m.get("subject", ""),
                    sender=sender,
                    when=m.get("receivedDateTime", ""),
                    body=(
                        body.get("content", "")[:100000]
                        if body.get("contentType", "").lower() == "text"
                        else "Open this message in Outlook to view its formatted body."
                    ),
                    thread=m.get("conversationId", m["id"]),
                )
            )
    return out


def send_connected(conn, contact, subject, body):
    if not current_app.config.get("MAIL_SEND_ENABLED") or not allowed(conn, "send"):
        raise IntegrationError(
            "Sending needs the additional mail permission. Reconnect your mailbox from Integrations after the administrator enables sending."
        )
    if not contact["email"]:
        raise IntegrationError("This contact has no email address.")
    import mail

    mail.check_allowance(1)
    headers = {"Authorization": f"Bearer {access_token(conn)}"}
    if conn["provider"] == "google":
        msg = EmailMessage()
        msg["To"] = contact["email"]
        msg["From"] = conn["account"] or g.user["email"]
        msg["Subject"] = subject
        msg.set_content(body)
        return http(
            "POST",
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers=headers,
            json_body={"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()},
        )
    return http(
        "POST",
        "https://graph.microsoft.com/v1.0/me/sendMail",
        headers=headers,
        json_body={
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": contact["email"]}}],
            },
            "saveToSentItems": True,
        },
    )


def register(app):
    @app.route("/mailbox", methods=["GET", "POST"])
    def mailbox():
        connections = rows(
            "SELECT * FROM connections WHERE workspace_id=? AND user_id=? AND provider IN ('google','microsoft')",
            ws(),
            g.user["id"],
        )
        conn = (
            mine(request.values.get("connection_id"))
            if request.values.get("connection_id")
            else (connections[0] if connections else None)
        )
        contact = (
            get_or_404("contacts", request.values.get("contact_id"))
            if request.values.get("contact_id")
            else None
        )
        messages = []
        error = None
        if request.method == "POST":
            if not conn or not contact:
                abort(422)
            subject = request.form.get("subject", "").strip()
            body = request.form.get("body", "").strip()
            if (
                not subject
                or len(subject) > 200
                or not body
                or len(body) > 20000
                or any(c in subject for c in "\r\n")
            ):
                abort(422)
            if g.get("demo"):
                abort(403)
            key = request.form.get("send_key", "")
            if len(key) < 24 or len(key) > 100:
                abort(422)
            db = get_db()
            if one("SELECT id FROM mailbox_outbox WHERE request_key=?", key):
                abort(
                    409,
                    "This send request was already submitted. Check your Sent folder before sending again.",
                )
            try:
                outbox = db.insert(
                    "mailbox_outbox",
                    workspace_id=ws(),
                    user_id=g.user["id"],
                    contact_id=contact["id"],
                    request_key=key,
                    status="sending",
                    created_at=__import__("core").now().isoformat(),
                )
                db.commit()
            except Exception:
                db.rollback()
                if one("SELECT id FROM mailbox_outbox WHERE request_key=?", key):
                    abort(409)
                raise
            try:
                send_connected(conn, contact, subject, body)
                db.execute("UPDATE mailbox_outbox SET status='sent' WHERE id=?", (outbox,))
                log_event(
                    subject,
                    "Sent from connected mailbox",
                    kind="email",
                    contact_id=contact["id"],
                    company_id=contact["company_id"],
                )
                get_db().commit()
                flash("Email sent.", "ok")
                return redirect(url_for("mailbox", connection_id=conn["id"], contact_id=contact["id"]))
            except (IntegrationError, mail.MailError) as exc:
                db.execute("UPDATE mailbox_outbox SET status='needs_review' WHERE id=?", (outbox,))
                db.commit()
                error = str(exc) + " Check your Sent folder before trying again if delivery was uncertain."
        if conn and contact:
            try:
                messages = conversation(conn, contact)
            except IntegrationError as exc:
                error = str(exc)
        return render_template(
            "mailbox.html",
            send_key=secrets.token_urlsafe(24),
            connections=connections,
            connection=conn,
            contact=contact,
            messages=messages,
            error=error,
            contacts=rows(
                "SELECT id,first_name,last_name FROM contacts WHERE workspace_id=? AND email IS NOT NULL ORDER BY first_name LIMIT 500",
                ws(),
            ),
            can_send=conn and allowed(conn, "send") and current_app.config.get("MAIL_SEND_ENABLED"),
        )
