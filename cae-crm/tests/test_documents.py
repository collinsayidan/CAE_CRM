import base64
import io
from datetime import timedelta

import pytest
from PIL import Image

from conftest import TODAY, first_id, query

SETTINGS = {"name": "Thistle Ltd", "legal_name": "Thistle Ltd", "address": "1 High Street", "city": "Edinburgh",
            "postcode": "EH1 1AA", "company_no": "SC512345", "vat_registered": "on", "vat_no": "GB123456789",
            "monthly_target": "150000", "invoice_prefix": "INV", "payment_terms": "30",
            "bank_account_name": "Thistle Ltd", "bank_sort_code": "12 34 56", "bank_account_number": "12345678",
            "payment_link": "https://pay.example.co.uk/thistle"}


@pytest.fixture
def outbox(app):
    app.config.update(MAIL_BACKEND="memory", CRON_SECRET="cron-secret")
    app.extensions["outbox"] = []
    return app.extensions["outbox"]


def png(size=(900, 300)):
    buf = io.BytesIO()
    Image.new("RGBA", size, (15, 31, 61, 255)).save(buf, "PNG")
    buf.seek(0)
    return buf


def save_settings(client, **changes):
    data = {"csrf": client.csrf, **SETTINGS, **changes}
    return client.post("/settings", data=data, content_type="multipart/form-data")


def unpaid_invoice(app):
    return query(app, "SELECT id, number FROM invoices WHERE workspace_id=? AND paid_date IS NULL ORDER BY id LIMIT 1", app.ws)[0]


def test_logo_and_payment_details_are_saved_and_shown(app, client):
    assert save_settings(client, logo=(png(), "logo.png")).status_code == 302
    sort_code, account, link, logo = query(app, "SELECT bank_sort_code, bank_account_number, payment_link, logo FROM workspaces "
                                                "WHERE id=?", app.ws)[0]
    assert (sort_code, account, link) == ("12-34-56", "12345678", "https://pay.example.co.uk/thistle")
    img = Image.open(io.BytesIO(base64.b64decode(logo)))
    assert img.size == (600, 200)  # scaled to fit, shape kept
    logo_resp = app.test_client().get(f"/logo/{app.ws}")  # public, for emails and customers' pages
    assert logo_resp.status_code == 200 and logo_resp.mimetype == "image/png"
    invoice_id, number = unpaid_invoice(app)
    page = client.get(f"/invoices/{invoice_id}").get_data(as_text=True)
    assert f"/logo/{app.ws}?v=" in page and "sort code 12-34-56" in page and "pay.example.co.uk" in page


def test_bad_payment_details_are_refused(app, client):
    resp = save_settings(client, bank_sort_code="1234", payment_link="http://insecure.example")
    page = resp.get_data(as_text=True)
    assert resp.status_code == 422 and "6-digit sort code" in page and "starting with https://" in page


def test_invoice_and_quote_pdfs(app, client):
    save_settings(client, logo=(png(), "logo.png"))
    invoice_id, number = unpaid_invoice(app)
    pdf = client.get(f"/invoices/{invoice_id}/pdf?download=1")
    assert pdf.mimetype == "application/pdf" and pdf.data.startswith(b"%PDF") and len(pdf.data) > 2000
    assert f'filename="{number}.pdf"' in pdf.headers["Content-Disposition"]
    deal = query(app, "SELECT d.id FROM deals d WHERE d.workspace_id=? AND EXISTS (SELECT 1 FROM line_items l WHERE "
                      "l.deal_id=d.id) ORDER BY d.id LIMIT 1", app.ws)[0][0]
    client.post(f"/deals/{deal}/quote", data={"csrf": client.csrf})
    quote_id, token = query(app, "SELECT id, token FROM quotes WHERE deal_id=? ORDER BY id DESC", deal)[0]
    assert client.get(f"/quotes/{quote_id}/pdf").data.startswith(b"%PDF")
    assert app.test_client().get(f"/q/{token}/pdf").status_code == 404  # a draft isn't public yet
    client.post(f"/quotes/{quote_id}/send", data={"csrf": client.csrf})
    assert app.test_client().get(f"/q/{token}/pdf").data.startswith(b"%PDF")
    assert app.test_client().get(f"/invoices/{invoice_id}/pdf").status_code == 302  # invoices need signing in


def test_emailing_an_invoice_attaches_the_pdf(app, client, outbox):
    invoice_id, number = unpaid_invoice(app)
    assert client.post(f"/invoices/{invoice_id}/email", data={"csrf": client.csrf, "contact_id": "", "email": "nope"}).status_code == 302
    assert not outbox
    client.post(f"/invoices/{invoice_id}/email", data={"csrf": client.csrf, "contact_id": "", "email": "Accounts@Customer.co.uk"})
    msg = outbox[-1]
    assert msg["to"] == ["accounts@customer.co.uk"] and msg["subject"].startswith(f"Invoice {number}")
    assert msg["attachments"][0]["filename"] == f"{number}.pdf"
    assert base64.b64decode(msg["attachments"][0]["content"]).startswith(b"%PDF")
    assert query(app, "SELECT sent_to FROM invoices WHERE id=?", invoice_id)[0][0] == "accounts@customer.co.uk"


def test_overdue_reminders_go_once_per_stage_and_stop_when_paid(app, client, outbox):
    invoice_id, number = unpaid_invoice(app)
    with app.app_context():
        from db import get_db
        db = get_db()
        db.execute("UPDATE invoices SET due_date=?, sent_to='accounts@customer.co.uk' WHERE id=?",
                   ((TODAY - timedelta(days=15)).isoformat(), invoice_id))
        db.execute("UPDATE invoices SET sent_to=NULL WHERE workspace_id=? AND id<>?", (app.ws, invoice_id))
        db.commit()
    cron = {"Authorization": "Bearer cron-secret"}
    assert app.test_client().get("/cron/sync", headers=cron).get_json()["reminders"] == 0  # reminders are off
    save_settings(client, reminders_on="on")
    assert app.test_client().get("/cron/sync", headers=cron).get_json()["reminders"] == 1
    assert outbox[-1]["subject"].startswith(f"Reminder: invoice {number}")
    assert app.test_client().get("/cron/sync", headers=cron).get_json()["reminders"] == 0  # the 14-day one is done
    assert query(app, "SELECT stage FROM invoice_reminders WHERE invoice_id=?", invoice_id)[0][0] == 14
    client.post(f"/invoices/{invoice_id}/remind", data={"csrf": client.csrf})
    assert len(outbox) == 2
    client.post(f"/invoices/{invoice_id}/paid", data={"csrf": client.csrf})
    with app.app_context():
        from db import get_db
        get_db().execute("UPDATE invoices SET due_date=? WHERE id=?", ((TODAY - timedelta(days=40)).isoformat(), invoice_id))
        get_db().commit()
    assert app.test_client().get("/cron/sync", headers=cron).get_json()["reminders"] == 0  # paid: no more chasing


def test_documents_stay_private_to_the_workspace(app, client, rival):
    invoice_id, _ = unpaid_invoice(app)
    assert rival.get(f"/invoices/{invoice_id}/pdf").status_code == 404
    assert rival.post(f"/invoices/{invoice_id}/email", data={"csrf": rival.csrf, "email": "x@y.co.uk"}).status_code == 404
