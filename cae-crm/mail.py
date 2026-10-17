"""Sending email through Resend (resend.com). Every business sends from the one address in CAE_MAIL_FROM, showing
the business's own name, with replies going to the business. Without RESEND_API_KEY, nothing is sent and pages say so.

Tests set MAIL_BACKEND = "memory" to collect messages in app.extensions["outbox"] instead of sending them."""

import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from email.utils import formataddr, parseaddr

from flask import current_app

API = "https://api.resend.com"
BATCH_SIZE = 100  # Resend's limit for one batch request


class MailError(Exception):
    pass


def configured():
    return current_app.config.get("MAIL_BACKEND") == "memory" or bool(current_app.config.get("RESEND_API_KEY"))


def sender(display_name):
    """The From header: the business's name on the platform's sending address."""
    address = parseaddr(current_app.config.get("MAIL_FROM") or "")[1] or "onboarding@resend.dev"
    # Keep the display name to plain characters so it can't break the header.
    name = "".join(ch for ch in (display_name or "CAE CRM") if ch.isprintable() and ch not in '<>"@,;')[:70]
    return formataddr((name.strip() or "CAE CRM", address))


def message(to, subject, html, text, from_name, reply_to=None, headers=None, tags=None):
    msg = {"from": sender(from_name), "to": [to], "subject": subject[:200], "html": html, "text": text}
    if reply_to:
        msg["reply_to"] = reply_to
    if headers:
        msg["headers"] = headers
    if tags:
        msg["tags"] = [{"name": k, "value": str(v)} for k, v in tags.items()]
    return msg


def _post(path, payload):
    req = urllib.request.Request(API + path, data=json.dumps(payload).encode(), method="POST", headers={
        "Authorization": f"Bearer {current_app.config['RESEND_API_KEY']}", "Content-Type": "application/json",
        "User-Agent": "CAE-CRM/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        try:
            detail = json.loads(detail).get("message", detail)
        except ValueError:
            pass
        raise MailError(f"Resend refused the email ({e.code}): {detail}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise MailError(f"Couldn't reach Resend: {e}") from None


def send(msg):
    """Send one message. Returns the provider's id. Raises MailError."""
    if current_app.config.get("MAIL_BACKEND") == "memory":
        outbox = current_app.extensions.setdefault("outbox", [])
        outbox.append(msg)
        return f"test-{len(outbox)}"
    if not configured():
        raise MailError("Email isn't set up. Add RESEND_API_KEY to the hosting settings.")
    return _post("/emails", msg).get("id", "")


def send_batch(msgs):
    """Send up to BATCH_SIZE messages in one request. Returns their ids in order. Raises MailError."""
    assert len(msgs) <= BATCH_SIZE
    if current_app.config.get("MAIL_BACKEND") == "memory":
        return [send(m) for m in msgs]
    if not configured():
        raise MailError("Email isn't set up. Add RESEND_API_KEY to the hosting settings.")
    data = _post("/emails/batch", msgs).get("data", [])
    return [d.get("id", "") for d in data] + [""] * (len(msgs) - len(data))


def verify_webhook(body, headers, secret, tolerance=300):
    """Check a Resend (Svix) webhook signature. Returns True when it's genuine and recent."""
    msg_id, stamp, sigs = headers.get("svix-id"), headers.get("svix-timestamp"), headers.get("svix-signature", "")
    if not (secret and msg_id and stamp and sigs):
        return False
    try:
        if abs(time.time() - int(stamp)) > tolerance:
            return False
        key = base64.b64decode(secret.split("_", 1)[1] if secret.startswith("whsec_") else secret)
    except (ValueError, TypeError):
        return False
    expected = base64.b64encode(hmac.new(key, f"{msg_id}.{stamp}.".encode() + body, hashlib.sha256).digest()).decode()
    return any(hmac.compare_digest(expected, part.split(",", 1)[1]) for part in sigs.split() if "," in part)
