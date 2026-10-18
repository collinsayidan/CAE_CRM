import base64
import hashlib
import hmac
import json
import re
from datetime import timedelta

import pytest

import webhooks
from conftest import ADMIN, MEMBER, TODAY, first_id, query


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    """Webhook addresses resolve to a public address, without using the network."""
    monkeypatch.setattr(webhooks, "resolve", lambda host: {"93.184.216.34"})


def make_key(client, access="write", name="Test key"):
    page = client.post("/settings/api/keys", data={"csrf": client.csrf, "name": name, "access": access})
    assert page.status_code == 200
    return re.search(r'id="new-key" value="(cae_[^"]+)"', page.get_data(as_text=True)).group(1)


def bearer(key):
    return {"Authorization": f"Bearer {key}"}


class Receiver:
    """Stands in for a customer's webhook endpoint."""

    def __init__(self, status=200):
        self.status, self.calls = status, []

    def __call__(self, url, headers, body):
        self.calls.append((url, headers, json.loads(body), body))
        return self.status

    def events(self):
        return [c[2]["event"] for c in self.calls]


def add_webhook(client, events, url="https://hooks.example.com/cae"):
    client.post("/settings/api/webhooks", data={"csrf": client.csrf, "url": url, "events": events})


# --- API keys and access -------------------------------------------------------------------------------------------

def test_keys_are_shown_once_stored_hashed_and_admin_only(app, client, member_client):
    assert member_client.get("/settings/api").status_code == 403
    assert member_client.post("/settings/api/keys", data={"csrf": member_client.csrf, "name": "x",
                                                         "access": "read"}).status_code == 403
    key = make_key(client)
    (stored_hash, prefix, by), = query(app, "SELECT key_hash, prefix, created_by FROM api_keys WHERE workspace_id=?", app.ws)
    assert stored_hash == hashlib.sha256(key.encode()).hexdigest() and key.startswith(prefix) and by == ADMIN[0]
    assert key not in client.get("/settings/api").get_data(as_text=True)
    assert client.get("/api/v1/", headers=bearer(key)).json["workspace"] == "Thistle Ltd"
    key_id = query(app, "SELECT id FROM api_keys WHERE workspace_id=?", app.ws)[0][0]
    client.post(f"/settings/api/keys/{key_id}/revoke", data={"csrf": client.csrf})
    assert client.get("/api/v1/", headers=bearer(key)).status_code == 401
    actions = [r[0] for r in query(app, "SELECT action FROM audit_events WHERE workspace_id=?", app.ws)]
    assert "Made an API key" in actions and "Revoked an API key" in actions


def test_api_needs_a_key_and_sees_only_its_own_business(app, client, rival, anon):
    assert anon.get("/api/v1/contacts").status_code == 401
    assert anon.get("/api/v1/contacts", headers=bearer("cae_wrong")).status_code == 401
    assert anon.get("/api/v1/nothing-here", headers=bearer("cae_wrong")).status_code == 401
    ours, theirs = make_key(client), make_key(rival)
    contact = first_id(app, "contacts", app.ws)
    assert anon.get(f"/api/v1/contacts/{contact}", headers=bearer(theirs)).status_code == 404
    assert anon.patch(f"/api/v1/contacts/{contact}", json={"first_name": "Hacked"}, headers=bearer(theirs)).status_code == 404
    listed = anon.get("/api/v1/contacts?per_page=100", headers=bearer(theirs)).json
    assert listed["total"] == query(app, "SELECT COUNT(*) FROM contacts WHERE workspace_id=?", app.rival_ws)[0][0]
    assert contact not in [c["id"] for c in listed["data"]]
    # Session cookies and CSRF tokens play no part: a signed-in browser without a key gets nothing.
    assert client.get("/api/v1/contacts").status_code == 401
    assert anon.get(f"/api/v1/contacts/{contact}", headers=bearer(ours)).json["id"] == contact


def test_lists_filter_page_and_fetch(app, client, anon):
    key = make_key(client, "read")
    total = query(app, "SELECT COUNT(*) FROM deals WHERE workspace_id=?", app.ws)[0][0]
    page = anon.get("/api/v1/deals?per_page=2&page=2", headers=bearer(key)).json
    assert len(page["data"]) == 2 and page["total"] == total and page["has_more"] and page["page"] == 2
    won = anon.get("/api/v1/deals?stage=Won&per_page=100", headers=bearer(key)).json
    assert won["data"] and all(d["stage"] == "Won" for d in won["data"])
    deal = won["data"][0]
    value = query(app, "SELECT value FROM deals WHERE id=?", deal["id"])[0][0]
    assert deal["value_pence"] == value and deal["url"].endswith(f"/deals/{deal['id']}")
    invoice = anon.get("/api/v1/invoices?per_page=1", headers=bearer(key)).json["data"][0]
    assert invoice["gross_pence"] == invoice["net_pence"] + invoice["vat_pence"] and invoice["status"] in ("Paid", "Due", "Overdue")
    assert anon.get("/api/v1/deals?page=x", headers=bearer(key)).status_code == 400
    company = deal["company_id"]
    mine = anon.get(f"/api/v1/deals?company_id={company}&per_page=100", headers=bearer(key)).json["data"]
    assert mine and all(d["company_id"] == company for d in mine)
    assert anon.get("/api/v1/deals?company_id=abc", headers=bearer(key)).status_code == 400
    assert anon.get("/api/v1/projects", headers=bearer(key)).status_code == 404
    assert anon.post("/api/v1/invoices", json={}, headers=bearer(make_key(client))).status_code == 405


def test_read_keys_cannot_write_and_read_only_workspaces_refuse_changes(app, client, anon):
    reader, writer = make_key(client, "read"), make_key(client, "write")
    new = {"first_name": "Ada", "last_name": "Byron", "lawful_basis": "Contract"}
    assert anon.post("/api/v1/contacts", json=new, headers=bearer(reader)).status_code == 403
    app.config.update(STRIPE_BACKEND=object(), STRIPE_PRICE_ID="price_seat", BILLING_EXEMPT="")
    with app.app_context():
        from db import get_db
        get_db().execute("UPDATE workspaces SET trial_ends=? WHERE id=?", ((TODAY - timedelta(days=1)).isoformat(), app.ws))
        get_db().commit()
    assert anon.post("/api/v1/contacts", json=new, headers=bearer(writer)).status_code == 402
    assert anon.get("/api/v1/contacts", headers=bearer(writer)).status_code == 200  # reading still works


def test_add_and_change_contacts_with_the_same_checks_as_the_app(app, client, anon):
    key = make_key(client)
    client.post("/custom-fields", data={"csrf": client.csrf, "object": "contacts", "label": "Tier", "field_type": "choice",
                                        "options": "Bronze, Silver, Gold"})
    bad = anon.post("/api/v1/contacts", json={"first_name": "Ada"}, headers=bearer(key))
    assert bad.status_code == 422 and "fields" in bad.json
    assert anon.post("/api/v1/contacts", json={"first_name": "Ada", "last_name": "Byron", "lawful_basis": "Because"},
                     headers=bearer(key)).status_code == 422
    assert anon.post("/api/v1/contacts", data="not json", headers=bearer(key)).status_code == 400
    company = first_id(app, "companies", app.ws)
    made = anon.post("/api/v1/contacts", headers=bearer(key), json={
        "first_name": "Ada", "last_name": "Byron", "email": "ADA@example.co.uk", "lawful_basis": "Contract",
        "company_id": company, "marketing_consent": True, "custom": {"tier": "Gold"}})
    assert made.status_code == 201
    c = made.json
    assert c["email"] == "ada@example.co.uk" and c["marketing_consent"] is True and c["custom"] == {"Tier": "Gold"}
    assert c["owner"] == ADMIN[0] and made.headers["Location"].endswith(f"/api/v1/contacts/{c['id']}")
    assert anon.post("/api/v1/contacts", headers=bearer(key), json={
        "first_name": "Dup", "last_name": "Licate", "email": "ada@example.co.uk", "lawful_basis": "Contract"}).status_code == 422
    changed = anon.patch(f"/api/v1/contacts/{c['id']}", headers=bearer(key),
                         json={"lifecycle_stage": "Customer", "owner": MEMBER[0], "custom": {"Tier": "Silver"}}).json
    assert (changed["lifecycle_stage"], changed["owner"], changed["custom"]["Tier"]) == ("Customer", MEMBER[0], "Silver")
    assert changed["first_name"] == "Ada" and changed["company_id"] == company  # untouched fields stay as they were
    assert anon.patch(f"/api/v1/contacts/{c['id']}", headers=bearer(key), json={"owner": "Nobody"}).status_code == 422
    assert anon.patch(f"/api/v1/contacts/{c['id']}", headers=bearer(key), json={"custom": {"Tier": "Platinum"}}).status_code == 422
    authors = [r[0] for r in query(app, "SELECT body FROM engagements WHERE contact_id=?", c["id"])]
    assert "Added by API key Test key" in authors
    assert query(app, "SELECT user_name FROM audit_events WHERE action='Added a contact through the API'")[0][0] == "API key Test key"


def test_deals_and_tickets_through_the_api(app, client, anon):
    key = make_key(client)
    company = first_id(app, "companies", app.ws)
    deal = anon.post("/api/v1/deals", headers=bearer(key), json={
        "title": "API pilot", "company_id": company, "value": "£1,250.50", "close_date": "2026-12-31"}).json
    assert deal["value_pence"] == 125050 and deal["stage"] == "Lead"
    assert anon.post("/api/v1/deals", headers=bearer(key), json={"title": "No company", "close_date": "2026-12-31"}
                     ).status_code == 422
    assert anon.post("/api/v1/deals", headers=bearer(key), json={
        "title": "Bad date", "company_id": company, "close_date": "31/12/2026"}).status_code == 422
    won = anon.patch(f"/api/v1/deals/{deal['id']}", headers=bearer(key), json={"stage": "Won"}).json
    assert won["stage"] == "Won" and won["closed_at"]
    assert query(app, "SELECT COUNT(*) FROM projects WHERE deal_id=?", deal["id"])[0][0] == 1  # as if won in the app
    ticket = anon.post("/api/v1/tickets", headers=bearer(key), json={"subject": "Printer on fire", "priority": "Urgent",
                                                                     "owner": MEMBER[0]}).json
    assert ticket["status"] == "New" and ticket["resolution_due"]
    closed = anon.patch(f"/api/v1/tickets/{ticket['id']}", headers=bearer(key), json={"status": "Closed"}).json
    assert closed["status"] == "Closed" and closed["closed_at"]
    notes = [r[0] for r in query(app, "SELECT n.title FROM notifications n JOIN users u ON u.id=n.user_id WHERE u.email=?",
                                 MEMBER[1])]
    assert any("Printer on fire" in n for n in notes)


def test_rate_limit(app, client, anon):
    app.config["API_RATE_LIMIT"] = 3
    key = make_key(client, "read")
    codes = [anon.get("/api/v1/", headers=bearer(key)).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


# --- Webhooks ------------------------------------------------------------------------------------------------------

def test_webhook_addresses_must_be_public_https(app, client, monkeypatch):
    add_webhook(client, ["contact.created"], url="http://hooks.example.com/cae")
    monkeypatch.setattr(webhooks, "resolve", lambda host: {"127.0.0.1"})
    add_webhook(client, ["contact.created"], url="https://localhost/cae")
    monkeypatch.setattr(webhooks, "resolve", lambda host: {"93.184.216.34", "10.0.0.5"})
    add_webhook(client, ["contact.created"], url="https://sneaky.example.com/cae")
    monkeypatch.setattr(webhooks, "resolve", lambda host: {"169.254.169.254"})
    add_webhook(client, ["contact.created"], url="https://metadata.example.com/")
    assert query(app, "SELECT COUNT(*) FROM webhooks")[0][0] == 0


def test_events_are_signed_and_sent(app, client, anon):
    receiver = Receiver()
    app.config["WEBHOOK_HTTP"] = receiver
    add_webhook(client, ["contact.created", "deal.stage_changed", "deal.won", "form.submitted"])
    secret = query(app, "SELECT secret FROM webhooks WHERE workspace_id=?", app.ws)[0][0]
    client.post("/contacts", data={"csrf": client.csrf, "first_name": "Ada", "last_name": "Byron", "lawful_basis": "Contract"})
    client.post("/contacts", data={"csrf": client.csrf, "first_name": "", "last_name": "", "lawful_basis": "Contract"})
    assert receiver.events() == ["contact.created"]  # a failed add sends nothing
    url, headers, payload, raw = receiver.calls[0]
    assert payload["data"]["first_name"] == "Ada" and headers["CAE-Event"] == "contact.created"
    stamp, sig = re.match(r"t=(\d+),v1=([0-9a-f]+)", headers["CAE-Signature"]).groups()
    assert hmac.compare_digest(sig, hmac.new(secret.encode(), f"{stamp}.".encode() + raw, hashlib.sha256).hexdigest())
    deal = first_id(app, "deals", app.ws, "stage='Proposal'")
    client.post(f"/deals/{deal}/stage", data={"csrf": client.csrf, "stage": "Won"})
    assert receiver.events()[1:] == ["deal.stage_changed", "deal.won"]
    assert receiver.calls[1][2]["previous_stage"] == "Proposal" and receiver.calls[2][2]["data"]["stage"] == "Won"
    assert query(app, "SELECT COUNT(*) FROM webhook_deliveries WHERE status='delivered'")[0][0] == 3


def test_failed_deliveries_retry_on_cron_then_pause(app, client):
    receiver = Receiver(status=500)
    app.config.update(WEBHOOK_HTTP=receiver, CRON_SECRET="cron-test")
    add_webhook(client, ["company.created"])
    client.post("/companies", data={"csrf": client.csrf, "name": "Retry Ltd", "postcode": "EH1 1AA"})
    (status, attempts, error), = query(app, "SELECT status, attempts, last_error FROM webhook_deliveries")
    assert (status, attempts) == ("pending", 1) and "500" in error
    with app.app_context():
        from db import get_db
        get_db().execute("UPDATE webhook_deliveries SET next_attempt_at='2000-01-01T00:00:00+00:00'")
        get_db().execute(f"UPDATE webhooks SET failures={webhooks.DISABLE_AFTER - 2}")
        get_db().commit()
    receiver.status = 200
    assert client.get("/cron/sync", headers={"Authorization": "Bearer cron-test"}).json["webhooks"]["delivered"] == 1
    assert tuple(query(app, "SELECT status, attempts FROM webhook_deliveries")[0]) == ("delivered", 2)
    assert query(app, "SELECT failures FROM webhooks")[0][0] == 0
    # Enough failures in a row pause the webhook and tell the admins.
    receiver.status = 500
    with app.app_context():
        from db import get_db
        get_db().execute(f"UPDATE webhooks SET failures={webhooks.DISABLE_AFTER - 1}")
        get_db().commit()
    client.post("/companies", data={"csrf": client.csrf, "name": "Pause Ltd", "postcode": "EH1 1AA"})
    assert len(receiver.calls) == 2  # a webhook that keeps failing isn't tried while someone waits for the page
    client.get("/cron/sync", headers={"Authorization": "Bearer cron-test"})
    assert query(app, "SELECT active FROM webhooks")[0][0] == 0
    assert query(app, "SELECT COUNT(*) FROM notifications WHERE title='A webhook was paused'")[0][0] == 1


def test_test_button_and_member_access(app, client, member_client):
    receiver = Receiver()
    app.config["WEBHOOK_HTTP"] = receiver
    add_webhook(client, ["invoice.paid"])
    hook = query(app, "SELECT id FROM webhooks")[0][0]
    assert member_client.post(f"/settings/api/webhooks/{hook}/test", data={"csrf": member_client.csrf}).status_code == 403
    client.post(f"/settings/api/webhooks/{hook}/test", data={"csrf": client.csrf})
    assert receiver.events() == ["ping"]


# --- Workflow rules ------------------------------------------------------------------------------------------------

def add_rule(client, **form):
    return client.post("/workflows", data={"csrf": client.csrf, **form})


def test_rule_creates_a_task_for_new_contacts(app, client, member_client):
    assert member_client.get("/workflows").status_code == 403
    add_rule(client, name="Call new leads", on_event="contact.created", action="task", task_subject="Intro call",
             task_kind="Call", task_days="1", task_person=MEMBER[0])
    page = client.get("/workflows").get_data(as_text=True)
    assert "When a contact is added, create a call “Intro call” for Test Member, due 1 day later." in page
    client.post("/contacts", data={"csrf": client.csrf, "first_name": "Ada", "last_name": "Byron", "lawful_basis": "Contract"})
    contact = query(app, "SELECT id FROM contacts WHERE first_name='Ada'")[0][0]
    (kind, subject, owner, due), = query(app, "SELECT kind, subject, owner, due_at FROM activities WHERE contact_id=?", contact)
    assert (kind, subject, owner, due) == ("Call", "Intro call: Ada Byron", MEMBER[0], "2026-10-17T09:00")
    assert query(app, "SELECT subject FROM engagements WHERE contact_id=? AND subject LIKE 'Workflow:%'", contact)
    assert query(app, "SELECT runs FROM workflow_rules")[0][0] == 1


def test_rules_filter_and_take_turns(app, client):
    add_rule(client, name="Share out wins", on_event="deal.stage_changed", on_stage="Won", action="owner",
             owner_person="rotate")
    deals = [r[0] for r in query(app, "SELECT id FROM deals WHERE workspace_id=? AND stage='Proposal' ORDER BY id", app.ws)][:2]
    client.post(f"/deals/{deals[0]}/stage", data={"csrf": client.csrf, "stage": "Negotiation"})
    assert query(app, "SELECT runs FROM workflow_rules")[0][0] == 0  # not the stage it's waiting for
    for d in deals:
        client.post(f"/deals/{d}/stage", data={"csrf": client.csrf, "stage": "Won"})
    owners = [query(app, "SELECT owner FROM deals WHERE id=?", d)[0][0] for d in deals]
    assert owners == sorted([ADMIN[0], MEMBER[0]])  # first one, then the other


def test_rules_run_for_web_forms_and_can_be_paused(app, client):
    app.config["FORM_MIN_SECONDS"] = 0
    client.post("/forms", data={"csrf": client.csrf, "name": "Website enquiries"})
    form_id, token = query(app, "SELECT id, token FROM web_forms WHERE workspace_id=? ORDER BY id DESC", app.ws)[0]
    add_rule(client, name="Hot lead", on_event="form.submitted", on_form=str(form_id), action="lifecycle",
             lifecycle_stage="Sales qualified lead")
    visitor = app.test_client()
    stamp = re.search(r'name="stamp" value="([^"]+)"', visitor.get(f"/f/{token}").get_data(as_text=True)).group(1)
    visitor.post(f"/f/{token}", data={"stamp": stamp, "first_name": "Morag", "last_name": "Campbell",
                                      "email": "morag@example.co.uk", "message": "Hello"})
    assert query(app, "SELECT lifecycle_stage FROM contacts WHERE email='morag@example.co.uk'")[0][0] == "Sales qualified lead"
    rule = query(app, "SELECT id FROM workflow_rules")[0][0]
    client.post(f"/workflows/{rule}/toggle", data={"csrf": client.csrf})
    assert query(app, "SELECT active FROM workflow_rules")[0][0] == 0
    add_rule(client, name="", on_event="contact.created", action="task")
    add_rule(client, name="Bad stage", on_event="deal.stage_changed", on_stage="Pending", action="notify",
             notify_person="owner")
    assert query(app, "SELECT COUNT(*) FROM workflow_rules")[0][0] == 1


# --- Power BI feed -------------------------------------------------------------------------------------------------

def test_power_bi_feed(app, client, anon):
    key = make_key(client, "read", "Power BI")
    client.post("/custom-fields", data={"csrf": client.csrf, "object": "deals", "label": "Region", "field_type": "text"})
    basic = {"Authorization": "Basic " + base64.b64encode(f"api:{key}".encode()).decode()}
    resp = anon.get("/api/v1/feed/deals", headers=basic)
    assert resp.status_code == 200 and resp.mimetype == "text/csv"
    header = resp.get_data(as_text=True).lstrip("﻿").splitlines()[0].split(",")
    assert {"value_gbp", "weighted_value_gbp", "company", "Region"} <= set(header) and "custom" not in header
    with app.app_context():
        from db import get_db
        get_db().execute("UPDATE companies SET name='=HYPERLINK(\"x\")', phone='+44 131 496 0000' WHERE id=?",
                         (first_id(app, "companies", app.ws),))
        get_db().commit()
    text = anon.get("/api/v1/feed/companies", headers=basic).get_data(as_text=True)
    assert "'=HYPERLINK" in text and "'+44" not in text
    rows = anon.get("/api/v1/feed/invoices?format=json", headers=basic).json
    assert rows and {"gross_gbp", "status"} <= rows[0].keys()
    assert anon.get("/api/v1/feed/users", headers=basic).status_code == 404
    assert anon.get("/api/v1/feed/deals").status_code == 401
    assert anon.get("/api/v1/feed/deals").headers["WWW-Authenticate"].startswith("Basic")
