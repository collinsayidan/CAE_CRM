"""Log emails from a connected Gmail or Outlook mailbox to contacts' timelines.

Only emails to or from someone already in your contacts are logged, and only the subject and a short preview are
stored, never the full message or attachments. Each message is logged once, however often the sync runs."""

from datetime import datetime, timedelta, timezone
from email.utils import getaddresses

from core import UK_TZ, log_event, now, one
from db import get_db
from integrations import access_token, http, record_sync

LOOKBACK = timedelta(days=3)  # how far back the first sync reaches
BATCH = 50  # messages per run, so one mailbox can't use up the whole run
PREVIEW = 300


def gmail_messages(token, since):
    auth = {"Authorization": f"Bearer {token}"}
    listing = http("GET", "https://gmail.googleapis.com/gmail/v1/users/me/messages", headers=auth,
                   params={"q": f"after:{int(since.timestamp())}", "maxResults": BATCH})
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
                        "$orderby": "receivedDateTime asc", "$top": BATCH})

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
    since = (datetime.fromisoformat(conn["sync_cursor"]) if conn["sync_cursor"]
             else datetime.now(timezone.utc) - LOOKBACK)
    token = access_token(conn)
    messages = (gmail_messages if conn["provider"] == "google" else outlook_messages)(token, since)
    logged, latest = 0, since
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
        when = m["when"].astimezone(UK_TZ).replace(tzinfo=None).isoformat(timespec="minutes")
        preview = " ".join(m["preview"].split())[:PREVIEW]
        direction = f"Sent to {', '.join(others)}" if outgoing else f"Received from {sender[0] if sender else 'unknown'}"
        for c in found[:5]:
            log_event((m["subject"] or "(no subject)")[:140], f"{direction}\n\n{preview}".strip(), kind="email",
                      author=user["name"], occurred_at=when, contact_id=c["id"], company_id=c["company_id"])
        logged += 1
    db.commit()
    record_sync(conn["id"], cursor=latest.isoformat(timespec="seconds"))
    return f"{conn['account'] or 'Mailbox'}: {logged} {'email' if logged == 1 else 'emails'} logged to contacts."
