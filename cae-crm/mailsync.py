"""Log emails from a connected Gmail or Outlook mailbox to contacts' timelines.

Only emails to or from someone already in your contacts are logged, and only the subject and a short preview are
stored, never the full message or attachments. Each message is logged once, however often the sync runs."""

from datetime import datetime, timedelta, timezone
from email.utils import getaddresses
from urllib.parse import urlsplit,parse_qs
from flask import g

from core import UK_TZ, log_event, now, one
from db import get_db
from integrations import access_token, http, record_sync

LOOKBACK = timedelta(days=3)  # how far back the first sync reaches
BATCH = 10  # messages per run, so one mailbox can't use up the whole run
PREVIEW = 300


def gmail_messages(token, since):
    auth = {"Authorization": f"Bearer {token}"}
    listing = http("GET", "https://gmail.googleapis.com/gmail/v1/users/me/messages", headers=auth,
                   params={"q": f"after:{int(since.timestamp())}", "maxResults": BATCH, **({"pageToken":g.mail_page} if g.get("mail_page") else {})})
    g.mail_next_page=listing.get("nextPageToken")
    out = []
    for ref in listing.get("messages") or []:
        m = http("GET", f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{ref['id']}", headers=auth,
                 params={"format": "metadata", "metadataHeaders": ["From", "To", "Cc", "Subject"]})
        head = {h["name"].lower(): h["value"] for h in (m.get("payload") or {}).get("headers", [])}
        out.append(dict(id=m["id"], subject=head.get("subject", ""), sender=head.get("from", ""),
                        recipients=", ".join(filter(None, [head.get("to"), head.get("cc")])),
                        when=datetime.fromtimestamp(int(m.get("internalDate", 0)) / 1000, timezone.utc),
                        preview=m.get("snippet", "")))
    return out


def outlook_messages(token, since):
    data = http("GET", "https://graph.microsoft.com/v1.0/me/messages", headers={"Authorization": f"Bearer {token}"},
                params={"$filter": f"receivedDateTime ge {since.strftime('%Y-%m-%dT%H:%M:%SZ')}",
                        "$select": "id,subject,from,toRecipients,ccRecipients,receivedDateTime,bodyPreview",
                        "$orderby": "receivedDateTime asc", "$top": BATCH, **({"$skiptoken":g.mail_page} if g.get("mail_page") else {})})
    next_url=data.get("@odata.nextLink")
    g.mail_next_page=None
    if next_url:
        parts=urlsplit(next_url)
        if parts.scheme!="https" or parts.hostname!="graph.microsoft.com":
            from integrations import IntegrationError
            raise IntegrationError("The mailbox returned an invalid continuation address.")
        g.mail_next_page=(parse_qs(parts.query).get("$skiptoken") or [None])[0]
        if not g.mail_next_page:
            from integrations import IntegrationError
            raise IntegrationError("This mailbox pagination response needs review before the sync can advance.")

    def addr(r):
        e = (r or {}).get("emailAddress") or {}
        return f'{e.get("name", "")} <{e.get("address", "")}>'
    return [dict(id=m["id"], subject=m.get("subject") or "", sender=addr(m.get("from")),
                 recipients=", ".join(addr(r) for r in (m.get("toRecipients") or []) + (m.get("ccRecipients") or [])),
                 when=datetime.fromisoformat(m["receivedDateTime"].replace("Z", "+00:00")), preview=m.get("bodyPreview") or "")
            for m in data.get("value") or []]


def addresses(text):
    return [a.lower() for _, a in getaddresses([text or ""]) if "@" in a]


def sync(conn):
    db = get_db()
    user = one("SELECT name, email FROM users WHERE id=?", conn["user_id"])
    if user is None:
        return "Nothing to sync."
    mine = {(conn["account"] or "").lower(), user["email"].lower()}
    since = (datetime.fromisoformat(conn["sync_window_start"] or conn["sync_cursor"]) if (conn["sync_window_start"] or conn["sync_cursor"])
             else datetime.now(timezone.utc) - LOOKBACK)
    token = access_token(conn)
    g.mail_page=conn["sync_page"];g.mail_next_page=None
    messages = (gmail_messages if conn["provider"] == "google" else outlook_messages)(token, since)
    logged, latest = 0, datetime.fromisoformat(conn["sync_window_latest"]) if conn["sync_window_latest"] else since
    for m in messages:
        latest = max(latest, m["when"])
        if one("SELECT 1 FROM synced_emails WHERE connection_id=? AND message_id=?", conn["id"], m["id"]):
            continue
        sender = addresses(m["sender"])
        outgoing = bool(sender) and sender[0] in mine
        others = [a for a in (addresses(m["recipients"]) if outgoing else sender) if a not in mine]
        found = []
        for a in dict.fromkeys(others):
            c = one("SELECT id, company_id FROM contacts WHERE workspace_id=? AND lower(email)=?", conn["workspace_id"], a)
            if c:
                found.append(c)
        db.insert("synced_emails", workspace_id=conn["workspace_id"], connection_id=conn["id"], message_id=m["id"],
                  created_at=now().isoformat(timespec="minutes"))
        if not found:
            continue  # not about anyone in the CRM, so nothing about it is kept
        if not outgoing:
            from sequences import stop_for_contact
            for c in found:
                stop_for_contact(c["id"], "Reply received")
        when = m["when"].astimezone(UK_TZ).replace(tzinfo=None).isoformat(timespec="minutes")
        preview = " ".join(m["preview"].split())[:PREVIEW]
        direction = f"Sent to {', '.join(others)}" if outgoing else f"Received from {sender[0] if sender else 'unknown'}"
        for c in found[:5]:
            log_event((m["subject"] or "(no subject)")[:140], f"{direction}\n\n{preview}".strip(), kind="email",
                      author=user["name"], occurred_at=when, contact_id=c["id"], company_id=c["company_id"])
        logged += 1
    db.commit()
    if g.get("mail_next_page"):
        db.execute("UPDATE connections SET sync_page=?,sync_window_start=?,sync_window_latest=? WHERE id=?",
            (g.mail_next_page,since.isoformat(timespec="seconds"),latest.isoformat(timespec="seconds"),conn["id"]))
        db.commit();record_sync(conn["id"])
    else:
        db.execute("UPDATE connections SET sync_page=NULL,sync_window_start=NULL,sync_window_latest=NULL WHERE id=?",(conn["id"],))
        db.commit();record_sync(conn["id"], cursor=latest.isoformat(timespec="seconds"))
    return f"{conn['account'] or 'Mailbox'}: {logged} {'email' if logged == 1 else 'emails'} logged to contacts."
