import base64
import hashlib
import hmac
import json
import re
import time

import pytest

from conftest import ADMIN, MEMBER, first_id, query
from db import get_db

SECRET = "whsec_" + base64.b64encode(b"inbound webhook secret").decode()
DOMAIN = "inbound.example.co.uk"


class FakeResend:
    """Stands in for Resend's Receiving API: emails by id, their attachments, and the files behind them."""

    def __init__(self):
        self.emails, self.files, self.calls = {}, {}, []

    def add(self, email_id, sender, subject, text, to=None, headers=None, attachments=None, authentication=None,
            message_id=None):
        self.emails[email_id] = {"id": email_id, "from": sender, "to": to or [], "subject": subject, "text": text,
                                 "html": None, "headers": headers or {}, "message_id": message_id or f"<{email_id}@mail>",
                                 "attachments": [{"id": a["id"]} for a in attachments or []],
                                 "authentication": authentication or {"spf": {"result": "pass"}, "dkim": {"result": "pass"}},
                                 "_attachments": attachments or []}

    def request(self, path):
        self.calls.append(path)
        m = re.match(r"/emails/receiving/([^/]+)(/attachments)?$", path)
        email = self.emails[m.group(1)]
        if m.group(2):
            return {"object": "list", "data": email["_attachments"]}
        return email

    def download(self, url):
        return self.files[url]


@pytest.fixture
def resend(app):
    fake = FakeResend()
    app.config.update(MAIL_BACKEND="memory", RESEND_WEBHOOK_SECRET=SECRET, INBOUND_DOMAIN=DOMAIN, INBOUND_BACKEND=fake,
                      MAIL_FROM="CAE CRM <hello@mail.example.co.uk>")
    app.extensions["outbox"] = []
    return fake


@pytest.fixture
def switched_on(app, resend, client):
    client.post("/settings/support-email", data={"csrf": client.csrf, "enabled": "on", "owner": MEMBER[0]})
    token = query(app, "SELECT inbound_token FROM workspaces WHERE id=?", app.ws)[0][0]
    return f"support-{token}@{DOMAIN}"


def deliver(app, email_id, to, sender="Morag Campbell <morag@bramble.co.uk>"):
    payload = {"type": "email.received", "created_at": "2026-10-16T10:00:00Z",
               "data": {"email_id": email_id, "from": sender, "to": [to], "subject": "x", "attachments": []}}
    body = json.dumps(payload).encode()
    msg_id, stamp = f"msg_{email_id}", str(int(time.time()))
    key = base64.b64decode(SECRET.split("_", 1)[1])
    sig = base64.b64encode(hmac.new(key, f"{msg_id}.{stamp}.".encode() + body, hashlib.sha256).digest()).decode()
    return app.test_client().post("/webhooks/resend", data=body, headers={
        "svix-id": msg_id, "svix-timestamp": stamp, "svix-signature": f"v1,{sig}", "Content-Type": "application/json"})


def latest_ticket(app):
    return query(app, "SELECT * FROM tickets WHERE workspace_id=? ORDER BY id DESC LIMIT 1", app.ws)[0]


# --- Settings ---------------------------------------------------------------------------------------------------------

def test_hidden_until_set_up(app, client):
    assert client.get("/settings/support-email").status_code == 404
    app.config.update(MAIL_BACKEND="memory", INBOUND_DOMAIN=DOMAIN)
    assert client.get("/settings/support-email").status_code == 200


def test_admins_switch_it_on_and_get_an_address(app, resend, client, member_client):
    assert member_client.get("/settings/support-email").status_code == 403
    client.post("/settings/support-email", data={"csrf": client.csrf, "enabled": "on", "owner": MEMBER[0]})
    on, owner, token = query(app, "SELECT inbound_on, inbound_owner, inbound_token FROM workspaces WHERE id=?", app.ws)[0]
    assert on == 1 and owner == MEMBER[0] and token
    page = client.get("/settings/support-email").get_data(as_text=True)
    assert f"support-{token}@{DOMAIN}" in page and "Microsoft 365" in page


# --- New tickets ------------------------------------------------------------------------------------------------------

def test_an_email_from_someone_new_opens_a_ticket_and_a_contact(app, resend, switched_on):
    company = first_id(app, "companies", app.ws)
    run_sql = "UPDATE companies SET website='https://www.bramble.co.uk' WHERE id=?"
    with app.app_context():
        get_db().execute(run_sql, (company,))
        get_db().commit()
    resend.add("e1", "Morag Campbell <Morag@Bramble.co.uk>", "Can't log in",
               "Hi,\n\nNone of us can sign in since this morning.\n\nMorag\n\nOn Mon, someone wrote:\n> old stuff",
               to=[switched_on])
    assert deliver(app, "e1", switched_on).status_code == 204
    t = latest_ticket(app)
    assert (t["subject"], t["source"], t["status"], t["owner"]) == ("Can't log in", "Email", "New", MEMBER[0])
    assert "None of us can sign in" in t["description"] and "old stuff" not in t["description"]
    contact = query(app, "SELECT first_name, last_name, email, lawful_basis, marketing_consent, company_id FROM contacts "
                         "WHERE id=?", t["contact_id"])[0]
    assert tuple(contact) == ("Morag", "Campbell", "morag@bramble.co.uk", "Legitimate interests", 0, company)
    assert query(app, "SELECT 1 FROM notifications n JOIN users u ON u.id=n.user_id WHERE u.email=? AND n.title LIKE "
                      "'New ticket%'", MEMBER[1])
    # Resend sometimes delivers the same event twice: it's handled once.
    deliver(app, "e1", switched_on)
    assert len(query(app, "SELECT 1 FROM tickets WHERE workspace_id=? AND subject=?", app.ws, "Can't log in")) == 1


def test_existing_contacts_are_reused_and_free_email_domains_are_not_companies(app, resend, switched_on):
    contact = first_id(app, "contacts", app.ws)
    with app.app_context():
        get_db().execute("UPDATE contacts SET email='known@example.co.uk' WHERE id=?", (contact,))
        get_db().commit()
    resend.add("e2", "known@example.co.uk", "Question", "Hello", to=[switched_on])
    deliver(app, "e2", switched_on, "known@example.co.uk")
    assert latest_ticket(app)["contact_id"] == contact
    resend.add("e3", "Jo Bloggs <jo.bloggs@gmail.com>", "Hello", "Hi", to=[switched_on])
    deliver(app, "e3", switched_on, "jo.bloggs@gmail.com")
    assert query(app, "SELECT company_id FROM contacts WHERE email='jo.bloggs@gmail.com'")[0][0] is None


def test_automatic_and_our_own_emails_are_ignored(app, resend, switched_on):
    before = len(query(app, "SELECT 1 FROM tickets WHERE workspace_id=?", app.ws))
    resend.add("a1", "mailer-daemon@googlemail.com", "Delivery failed", "x", to=[switched_on])
    resend.add("a2", "Help <help@bramble.co.uk>", "Out of office", "Away", to=[switched_on],
               headers={"Auto-Submitted": "auto-replied"})
    resend.add("a3", "hello@mail.example.co.uk", "Loop", "x", to=[switched_on])
    for i in ("a1", "a2", "a3"):
        deliver(app, i, switched_on)
    assert len(query(app, "SELECT 1 FROM tickets WHERE workspace_id=?", app.ws)) == before
    assert [r[0] for r in query(app, "SELECT outcome FROM inbound_emails ORDER BY id")] == ["ignored"] * 3


def test_unknown_addresses_and_rival_workspaces_get_nothing(app, resend, switched_on, rival):
    before = len(query(app, "SELECT 1 FROM tickets"))
    resend.add("x1", "a@b.co.uk", "Hi", "x")
    deliver(app, "x1", f"support-notarealtoken@{DOMAIN}")
    deliver(app, "x1", "support@somewhere-else.co.uk")
    assert len(query(app, "SELECT 1 FROM tickets")) == before
    assert not resend.calls  # nothing was even fetched


def test_limits_stop_floods(app, resend, switched_on, monkeypatch):
    import inbound
    monkeypatch.setattr(inbound, "PER_SENDER_HOUR", 2)
    for i in range(3):
        resend.add(f"f{i}", "flood@spam.example", f"Spam {i}", "x", to=[switched_on])
        deliver(app, f"f{i}", switched_on, "flood@spam.example")
    assert [r[0] for r in query(app, "SELECT outcome FROM inbound_emails ORDER BY id")] == ["opened", "opened", "limited"]


def test_unverified_senders_are_flagged(app, resend, switched_on):
    resend.add("u1", "boss@bramble.co.uk", "Urgent payment", "Pay this now", to=[switched_on],
               authentication={"spf": {"result": "fail"}, "dkim": {"result": "fail"}, "dmarc": {"result": "fail"}})
    deliver(app, "u1", switched_on, "boss@bramble.co.uk")
    t = latest_ticket(app)
    assert query(app, "SELECT 1 FROM engagements WHERE ticket_id=? AND body LIKE '%couldn''t be verified%'", t["id"])


# --- Replies thread back ----------------------------------------------------------------------------------------------

def test_replies_from_a_ticket_come_back_to_it(app, resend, switched_on, client):
    resend.add("r0", "Morag <morag@bramble.co.uk>", "Login", "Help", to=[switched_on])
    deliver(app, "r0", switched_on)
    t = latest_ticket(app)
    client.post(f"/tickets/{t['id']}/reply", data={"csrf": client.csrf, "body": "Try now, please."})
    sent = app.extensions["outbox"][-1]
    assert f"[#{t['id']}]" in sent["subject"]
    reply_to = sent["reply_to"] if isinstance(sent.get("reply_to"), str) else sent["reply_to"][0]
    assert reply_to.startswith(switched_on.split("@")[0] + f"+{t['id']}-")
    assert query(app, "SELECT status FROM tickets WHERE id=?", t["id"])[0][0] == "Waiting on contact"
    resend.add("r1", "Morag <morag@bramble.co.uk>", f"Re: {sent['subject']}", "That worked, thanks!\n\n> Try now",
               to=[reply_to])
    deliver(app, "r1", reply_to)
    assert latest_ticket(app)["id"] == t["id"]  # no new ticket
    status = query(app, "SELECT status FROM tickets WHERE id=?", t["id"])[0][0]
    bodies = [r[0] for r in query(app, "SELECT body FROM engagements WHERE ticket_id=? AND kind='email'", t["id"])]
    assert status == "Waiting on us" and "That worked, thanks!" in bodies and not any("> Try now" in b for b in bodies)


def test_forged_ticket_addresses_and_strangers_do_not_thread(app, resend, switched_on):
    resend.add("s0", "morag@bramble.co.uk", "Login", "Help", to=[switched_on])
    deliver(app, "s0", switched_on, "morag@bramble.co.uk")
    t = latest_ticket(app)
    local, dom = switched_on.split("@")
    forged = f"{local}+{t['id']}-deadbeef@{dom}"
    resend.add("s1", "attacker@evil.example", "Re: Login", "Ignore", to=[forged])
    deliver(app, "s1", forged, "attacker@evil.example")
    resend.add("s2", "attacker@evil.example", f"Re: [#{t['id']}] Login", "Also ignore", to=[switched_on])
    deliver(app, "s2", switched_on, "attacker@evil.example")
    assert not query(app, "SELECT 1 FROM engagements WHERE ticket_id=? AND body LIKE '%ignore%'", t["id"])
    assert len(query(app, "SELECT 1 FROM tickets WHERE contact_id=(SELECT id FROM contacts WHERE email='attacker@evil.example')")) == 2


def test_replies_reopen_recent_tickets_and_follow_on_from_old_ones(app, resend, switched_on, client):
    resend.add("o0", "morag@bramble.co.uk", "Login", "Help", to=[switched_on])
    deliver(app, "o0", switched_on, "morag@bramble.co.uk")
    t = latest_ticket(app)
    client.post(f"/tickets/{t['id']}/status", data={"csrf": client.csrf, "status": "Closed"})
    resend.add("o1", "morag@bramble.co.uk", f"Re: [#{t['id']}] Login", "It's broken again", to=[switched_on])
    deliver(app, "o1", switched_on, "morag@bramble.co.uk")
    assert query(app, "SELECT status FROM tickets WHERE id=?", t["id"])[0][0] == "Waiting on us"
    with app.app_context():
        get_db().execute("UPDATE tickets SET status='Closed', closed_at='2026-08-01T10:00' WHERE id=?", (t["id"],))
        get_db().commit()
    resend.add("o2", "morag@bramble.co.uk", f"Re: [#{t['id']}] Login", "Back again months later", to=[switched_on])
    deliver(app, "o2", switched_on, "morag@bramble.co.uk")
    new = latest_ticket(app)
    assert new["id"] != t["id"] and f"Follows on from ticket #{t['id']}" in new["description"]


# --- Attachments ------------------------------------------------------------------------------------------------------

def test_attachments_are_saved_to_the_ticket(app, resend, switched_on):
    resend.files["https://cdn.example/1"] = b"%PDF-1.7 order"
    resend.files["https://cdn.example/2"] = b"MZ evil"
    resend.add("p1", "morag@bramble.co.uk", "Purchase order", "Attached", to=[switched_on], attachments=[
        {"id": "a1", "filename": "PO-1234.pdf", "size": 14, "content_type": "application/pdf",
         "content_disposition": "attachment", "download_url": "https://cdn.example/1"},
        {"id": "a2", "filename": "invoice.exe", "size": 7, "content_type": "application/octet-stream",
         "content_disposition": "attachment", "download_url": "https://cdn.example/2"},
        {"id": "a3", "filename": "logo.png", "size": 10, "content_type": "image/png", "content_disposition": "inline",
         "content_id": "logo", "download_url": "https://cdn.example/3"}])
    deliver(app, "p1", switched_on, "morag@bramble.co.uk")
    t = latest_ticket(app)
    files = query(app, "SELECT filename, size FROM attachments WHERE record_type='ticket' AND record_id=?", t["id"])
    assert [tuple(f) for f in files] == [("PO-1234.pdf", 14)]
    note = query(app, "SELECT body FROM engagements WHERE ticket_id=? AND subject='Attachments from the email'", t["id"])[0][0]
    assert "PO-1234.pdf" in note and "invoice.exe" in note and "logo.png" not in note


def test_legal_pages_mention_receiving_email(anon):
    assert "receiving" in anon.get("/legal/dpa").get_data(as_text=True).lower()
