import base64
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest

from conftest import ADMIN, TODAY, first_id, query


def id_token(claims):
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJub25lIn0.{body}.sig"


class FakeServices:
    """Plays Google, Microsoft, Xero and HMRC: answers by URL and remembers every call."""

    def __init__(self):
        self.calls = []
        self.gmail = []
        self.outlook = []
        self.xero_status = "AUTHORISED"

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        path = urlsplit(url).path
        if url.startswith("https://oauth2.googleapis.com/token") or url.endswith("/oauth2/v2.0/token") \
                or url.startswith("https://identity.xero.com/connect/token") or path == "/oauth/token":
            grant = parse_qs(body.decode())["grant_type"][0]
            return 200, {"access_token": f"access-{grant}", "refresh_token": "refresh-1", "expires_in": 3600,
                         "id_token": id_token({"email": "admin@gmail.example"})}
        if path == "/gmail/v1/users/me/messages":
            return 200, {"messages": [{"id": m["id"]} for m in self.gmail]}
        if path.startswith("/gmail/v1/users/me/messages/"):
            m = next(m for m in self.gmail if m["id"] == path.rsplit("/", 1)[1])
            return 200, {"id": m["id"], "snippet": m["snippet"], "internalDate": str(m["ms"]),
                         "payload": {"headers": [{"name": "From", "value": m["from"]}, {"name": "To", "value": m["to"]},
                                                 {"name": "Subject", "value": m["subject"]}]}}
        if url == "https://graph.microsoft.com/v1.0/me":
            return 200, {"mail": "admin@outlook.example"}
        if path == "/v1.0/me/messages":
            return 200, {"value": self.outlook}
        if url == "https://api.xero.com/connections":
            return 200, [{"tenantId": "tenant-1", "tenantName": "Thistle Ltd (Xero)", "tenantType": "ORGANISATION"}]
        if path == "/api.xro/2.0/Invoices" and method == "PUT":
            return 200, {"Invoices": [{"InvoiceID": "xero-inv-1"}]}
        if path == "/api.xro/2.0/Invoices" and method == "GET":
            return 200, {"Invoices": [{"InvoiceID": "xero-inv-1", "Status": self.xero_status,
                                       "FullyPaidOnDate": "/Date(1792022400000+0000)/"}]}
        if path.endswith("/obligations"):
            return 200, {"obligations": [{"periodKey": "26A3", "start": "2026-07-01", "end": "2026-09-30",
                                          "due": "2026-11-07", "status": "O"}]}
        if path.endswith("/returns"):
            return 201, {"processingDate": "2026-10-16T11:00:00Z", "formBundleNumber": "256660290587"}
        raise AssertionError(f"unexpected call {method} {url}")


@pytest.fixture
def services(app):
    fake = FakeServices()
    app.config.update(INTEGRATION_HTTP=fake, GOOGLE_CLIENT_ID="g-id", GOOGLE_CLIENT_SECRET="g-secret",
                      CRON_SECRET="cron-secret")
    return fake


def connect(client, provider):
    start = client.post(f"/integrations/{provider}/connect", data={"csrf": client.csrf})
    assert start.status_code == 302
    state = parse_qs(urlsplit(start.headers["Location"]).query)["state"][0]
    return client.get(f"/integrations/{provider}/callback?code=abc&state={state}")


def a_contact(app):
    return query(app, "SELECT id, email, first_name FROM contacts WHERE workspace_id=? AND email <> '' ORDER BY id LIMIT 1", app.ws)[0]


def test_connecting_checks_state_and_encrypts_tokens(app, client, services):
    page = client.get("/integrations").get_data(as_text=True)
    assert "Connect Gmail" in page
    start = client.post("/integrations/google/connect", data={"csrf": client.csrf})
    params = parse_qs(urlsplit(start.headers["Location"]).query)
    assert params["client_id"] == ["g-id"] and "gmail.readonly" in params["scope"][0] and params["access_type"] == ["offline"]
    client.get("/integrations/google/callback?code=abc&state=forged")
    assert query(app, "SELECT COUNT(*) FROM connections")[0][0] == 0
    connect(client, "google")
    account, access, refresh = query(app, "SELECT account, access_token, refresh_token FROM connections")[0]
    assert account == "admin@gmail.example"
    assert "access-authorization_code" not in access and refresh != "refresh-1"  # stored encrypted


def test_expired_tokens_are_refreshed(app, client, services):
    connect(client, "google")
    with app.app_context():
        from db import get_db
        from integrations import access_token, connection
        from flask import g
        g.user = {"workspace_id": app.ws}
        get_db().execute("UPDATE connections SET expires_at=?", ((datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),))
        get_db().commit()
        assert access_token(connection("google")) == "access-refresh_token"


def test_gmail_logs_only_emails_with_contacts_and_only_once(app, client, services):
    contact_id, email, _ = a_contact(app)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    services.gmail = [
        {"id": "m1", "from": f"Someone <{email}>", "to": "admin@gmail.example", "subject": "Re: pricing",
         "snippet": "Thanks, that works for us", "ms": now_ms},
        {"id": "m2", "from": "newsletter@shop.example", "to": "admin@gmail.example", "subject": "Sale!", "snippet": "50% off",
         "ms": now_ms},
    ]
    connect(client, "google")
    conn_id = query(app, "SELECT id FROM connections")[0][0]
    client.post(f"/integrations/{conn_id}/sync", data={"csrf": client.csrf})
    logged = query(app, "SELECT subject, body, author, kind FROM engagements WHERE contact_id=? AND subject='Re: pricing'", contact_id)
    assert len(logged) == 1 and logged[0][3] == "email" and logged[0][2] == ADMIN[0] and "Thanks, that works" in logged[0][1]
    assert query(app, "SELECT COUNT(*) FROM engagements WHERE subject='Sale!'")[0][0] == 0
    client.post(f"/integrations/{conn_id}/sync", data={"csrf": client.csrf})
    assert query(app, "SELECT COUNT(*) FROM engagements WHERE subject='Re: pricing'")[0][0] == 1


def test_outlook_logs_sent_email(app, member_client, services):
    app.config.update(MICROSOFT_CLIENT_ID="m-id", MICROSOFT_CLIENT_SECRET="m-secret")
    contact_id, email, _ = a_contact(app)
    services.outlook = [{"id": "o1", "subject": "Proposal attached", "bodyPreview": "Please find attached",
                         "from": {"emailAddress": {"address": "admin@outlook.example"}},
                         "toRecipients": [{"emailAddress": {"name": "C", "address": email}}],
                         "receivedDateTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}]
    connect(member_client, "microsoft")
    conn_id = query(app, "SELECT id FROM connections WHERE provider='microsoft'")[0][0]
    member_client.post(f"/integrations/{conn_id}/sync", data={"csrf": member_client.csrf})
    body = query(app, "SELECT body FROM engagements WHERE contact_id=? AND subject='Proposal attached'", contact_id)[0][0]
    assert body.startswith(f"Sent to {email}")


def test_members_connect_their_own_mailbox_but_not_the_business(app, client, member_client, services):
    app.config.update(XERO_CLIENT_ID="x-id", XERO_CLIENT_SECRET="x-secret")
    assert member_client.post("/integrations/xero/connect", data={"csrf": member_client.csrf}).status_code == 403
    connect(client, "google")
    conn_id = query(app, "SELECT id FROM connections")[0][0]
    assert member_client.post(f"/integrations/{conn_id}/disconnect", data={"csrf": member_client.csrf}).status_code == 403


def test_xero_receives_invoices_and_reports_payments(app, client, services):
    app.config.update(XERO_CLIENT_ID="x-id", XERO_CLIENT_SECRET="x-secret")
    connect(client, "xero")
    assert query(app, "SELECT tenant_id, account FROM connections WHERE provider='xero'")[0][0] == "tenant-1"
    invoice = query(app, "SELECT id FROM invoices WHERE workspace_id=? AND paid_date IS NULL ORDER BY id LIMIT 1", app.ws)[0][0]
    client.post(f"/invoices/{invoice}/xero", data={"csrf": client.csrf})
    put = next(c for c in services.calls if c[0] == "PUT")
    assert put[2]["xero-tenant-id"] == "tenant-1"
    sent = json.loads(put[3])["Invoices"][0]
    number = query(app, "SELECT number FROM invoices WHERE id=?", invoice)[0][0]
    assert sent["InvoiceNumber"] == number and sent["Type"] == "ACCREC" and sent["LineAmountTypes"] == "Exclusive"
    assert all(li["TaxType"] in ("OUTPUT2", "RROUTPUT", "ZERORATEDOUTPUT") for li in sent["LineItems"])
    assert query(app, "SELECT xero_invoice_id FROM invoices WHERE id=?", invoice)[0][0] == "xero-inv-1"
    services.xero_status = "PAID"
    conn_id = query(app, "SELECT id FROM connections WHERE provider='xero'")[0][0]
    client.post(f"/integrations/{conn_id}/sync", data={"csrf": client.csrf})
    assert query(app, "SELECT paid_date FROM invoices WHERE id=?", invoice)[0][0] == "2026-10-15"


def test_vat_return_is_worked_out_and_submitted_with_fraud_headers(app, client, services):
    app.config.update(HMRC_CLIENT_ID="h-id", HMRC_CLIENT_SECRET="h-secret")
    with app.app_context():
        from db import get_db
        get_db().execute("UPDATE workspaces SET vat_no='GB123456789' WHERE id=?", (app.ws,))
        get_db().commit()
    connect(client, "hmrc")
    page = client.get("/vat?screens=width%3D1920&timezone=UTC%2B01:00").get_data(as_text=True)
    assert "Prepare return" in page
    vat, net = (int(v or 0) for v in query(app, "SELECT SUM(vat), SUM(net) FROM invoices WHERE workspace_id=? "
                                                "AND issue_date >= '2026-07-01' AND issue_date <= '2026-09-30'", app.ws)[0])
    form = client.get("/vat/26A3?start=2026-07-01&end=2026-09-30").get_data(as_text=True)
    assert f'value="{(vat or 0) / 100:.2f}"' in form
    base = {"csrf": client.csrf, "start": "2026-07-01", "end": "2026-09-30", "box1": f"{(vat or 0) / 100:.2f}", "box2": "0",
            "box4": "120.50", "box6": str((net or 0) // 100), "box7": "900", "box8": "0", "box9": "0",
            "screens": "width=1920&height=1080&scaling-factor=1&colour-depth=24", "window_size": "width=1200&height=800",
            "timezone": "UTC+01:00", "js_user_agent": "Test", "dnt": "0", "device_id": "dev-1"}
    assert client.post("/vat/26A3", data=base).status_code == 422  # no declaration
    assert client.post("/vat/26A3", data={**base, "declaration": "on"}).status_code == 302
    method, url, headers, body = next(c for c in services.calls if c[1].endswith("/returns"))
    sent = json.loads(body)
    assert sent["periodKey"] == "26A3" and sent["vatReclaimedCurrPeriod"] == 120.5 and sent["finalised"] is True
    assert sent["netVatDue"] == round(abs((vat or 0) / 100 - 120.5), 2)
    assert "/organisations/vat/123456789/returns" in url
    for h in ("Gov-Client-Connection-Method", "Gov-Client-Device-ID", "Gov-Client-Screens", "Gov-Client-Timezone",
              "Gov-Vendor-Version", "Gov-Client-User-IDs"):
        assert headers.get(h), h
    assert headers["Accept"] == "application/vnd.hmrc.1.0+json"
    assert query(app, "SELECT period_key FROM vat_returns WHERE workspace_id=?", app.ws)[0][0] == "26A3"
    assert client.post("/vat/26A3", data={**base, "declaration": "on"}).status_code == 302
    assert sum(1 for c in services.calls if c[1].endswith("/returns")) == 1


def test_cron_needs_the_secret_and_syncs_everyone(app, client, services):
    connect(client, "google")
    assert app.test_client().get("/cron/sync").status_code == 401
    assert app.test_client().get("/cron/sync", headers={"Authorization": "Bearer wrong"}).status_code == 401
    r = app.test_client().get("/cron/sync", headers={"Authorization": "Bearer cron-secret"})
    assert r.status_code == 200 and r.get_json()["synced"] == 1


def test_connections_are_private_to_the_workspace(app, client, rival, services):
    connect(client, "google")
    conn_id = query(app, "SELECT id FROM connections")[0][0]
    assert rival.post(f"/integrations/{conn_id}/sync", data={"csrf": rival.csrf}).status_code == 404
    assert rival.post(f"/integrations/{conn_id}/disconnect", data={"csrf": rival.csrf}).status_code == 404
    assert "admin@gmail.example" not in rival.get("/integrations").get_data(as_text=True)
