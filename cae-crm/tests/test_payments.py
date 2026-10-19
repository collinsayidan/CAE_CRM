import hashlib
import hmac
import json
import time
from datetime import date, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from conftest import MEMBER, TODAY, first_id, query
from db import get_db

CONNECT_SECRET = "whsec_test_connect"
CRON = {"Authorization": "Bearer cron-secret"}


def run(app, statement, *args):
    with app.app_context():
        get_db().execute(statement, args)
        get_db().commit()


class FakeStripe:
    """Stands in for Stripe Connect: the OAuth endpoints and Checkout on connected accounts."""

    def __init__(self):
        self.calls = []
        self.sessions = {}

    def request(self, method, path, params, account=None, oauth=False):
        self.calls.append((method, path, params, account, oauth))
        if oauth and path == "/oauth/token":
            if params["code"] != "good-code":
                from stripe_api import StripeError
                raise StripeError("Stripe refused the request (400). Authorization code expired")
            return {"stripe_user_id": "acct_thistle", "scope": "read_write"}
        if oauth and path == "/oauth/deauthorize":
            return {"stripe_user_id": params["stripe_user_id"]}
        if path == "/accounts/acct_thistle":
            return {"id": "acct_thistle", "settings": {"dashboard": {"display_name": "Thistle Ltd"}}}
        if path == "/checkout/sessions" and method == "POST":
            sid = f"cs_test_{len(self.sessions) + 1}"
            self.sessions[sid] = {"id": sid, "payment_status": "unpaid", "amount_total": params["line_items"][0]["price_data"]["unit_amount"],
                                  "metadata": {k: str(v) for k, v in params["metadata"].items()}, "payment_intent": f"pi_{sid}"}
            return {"id": sid, "url": f"https://checkout.stripe.test/{sid}"}
        if path.startswith("/checkout/sessions/"):
            return self.sessions[path.rsplit("/", 1)[1]]
        raise AssertionError(f"unexpected Stripe call {method} {path}")


@pytest.fixture
def stripe(app):
    fake = FakeStripe()
    app.config.update(STRIPE_BACKEND=fake, STRIPE_CONNECT_CLIENT_ID="ca_test", STRIPE_CONNECT_WEBHOOK_SECRET=CONNECT_SECRET)
    return fake


@pytest.fixture
def outbox(app):
    app.config.update(MAIL_BACKEND="memory", CRON_SECRET="cron-secret")
    app.extensions["outbox"] = []
    return app.extensions["outbox"]


@pytest.fixture
def invoice(app, client):
    """A fresh £1,000 + VAT invoice (£1,200), due in 30 days."""
    company = first_id(app, "companies", app.ws)
    client.post("/invoices", data={"csrf": client.csrf, "company_id": company, "description": "Consultancy",
                                   "net": "1000", "vat_rate": "20"})
    return query(app, "SELECT id FROM invoices WHERE workspace_id=? ORDER BY id DESC LIMIT 1", app.ws)[0][0]


def inv(app, invoice_id):
    return query(app, "SELECT * FROM invoices WHERE id=?", invoice_id)[0]


def pay(client, invoice_id, amount, method="Bank transfer", paid_on=None, **extra):
    return client.post(f"/invoices/{invoice_id}/payments", data={"csrf": client.csrf, "amount": amount, "method": method,
                                                                 "paid_on": paid_on or TODAY.isoformat(), **extra})


def connect(app, client, stripe):
    start = client.get("/settings/payments/stripe")
    state = parse_qs(urlsplit(start.headers["Location"]).query)["state"][0]
    return client.get(f"/settings/payments/stripe/return?code=good-code&state={state}")


def connect_webhook(app, event, secret=CONNECT_SECRET):
    body = json.dumps(event).encode()
    stamp = int(time.time())
    sig = hmac.new(secret.encode(), f"{stamp}.".encode() + body, hashlib.sha256).hexdigest()
    return app.test_client().post("/webhooks/stripe-connect", data=body, headers={"Stripe-Signature": f"t={stamp},v1={sig}"})


# --- Part payments ----------------------------------------------------------------------------------------------------

def test_part_payments_add_up_and_mark_the_invoice_paid(app, client, invoice):
    assert pay(client, invoice, "500").status_code == 302
    i = inv(app, invoice)
    assert i["amount_paid"] == 50_000 and i["paid_date"] is None
    page = client.get(f"/invoices/{invoice}").get_data(as_text=True)
    assert "Part paid: £700.00 left to pay" in page
    assert "£700.00 left" in client.get("/invoices").get_data(as_text=True)
    pay(client, invoice, "800")  # more than is left: refused
    assert inv(app, invoice)["amount_paid"] == 50_000
    pay(client, invoice, "100", paid_on=(TODAY + timedelta(days=1)).isoformat())  # in the future: refused
    assert inv(app, invoice)["amount_paid"] == 50_000
    pay(client, invoice, "700", method="Cheque", reference="CHQ 0042")
    i = inv(app, invoice)
    assert i["amount_paid"] == 120_000 and i["paid_date"] == TODAY.isoformat()
    timeline = [r[0] for r in query(app, "SELECT subject FROM engagements WHERE company_id=? ORDER BY id", i["company_id"])]
    assert f"Payment of £700.00 received for invoice {i['number']}" in timeline and f"Invoice {i['number']} paid" in timeline


def test_removing_a_payment_reopens_the_invoice(app, client, member_client, invoice):
    pay(client, invoice, "1200")
    assert inv(app, invoice)["paid_date"]
    payment = query(app, "SELECT id FROM invoice_payments WHERE invoice_id=?", invoice)[0][0]
    assert member_client.post(f"/invoices/{invoice}/payments/{payment}/delete", data={"csrf": member_client.csrf}).status_code == 403
    client.post(f"/invoices/{invoice}/payments/{payment}/delete", data={"csrf": client.csrf})
    i = inv(app, invoice)
    assert i["amount_paid"] == 0 and i["paid_date"] is None


def test_mark_paid_records_what_was_left(app, client, invoice):
    pay(client, invoice, "200")
    client.post(f"/invoices/{invoice}/paid", data={"csrf": client.csrf})
    amounts = sorted(r[0] for r in query(app, "SELECT amount FROM invoice_payments WHERE invoice_id=?", invoice))
    assert amounts == [20_000, 100_000] and inv(app, invoice)["paid_date"] == TODAY.isoformat()


# --- Credit notes -----------------------------------------------------------------------------------------------------

def test_credit_notes_reduce_what_is_owed(app, client, invoice):
    client.post(f"/invoices/{invoice}/credit-notes", data={"csrf": client.csrf, "amount": "240", "reason": "Two days not needed"})
    note = query(app, "SELECT id, number, net, vat FROM credit_notes WHERE invoice_id=?", invoice)[0]
    assert tuple(note[1:]) == ("CN-0001", 20_000, 4_000)
    assert inv(app, invoice)["credited"] == 24_000
    pdf = client.get(f"/credit-notes/{note[0]}/pdf")
    assert pdf.data.startswith(b"%PDF") and 'CN-0001.pdf' in pdf.headers["Content-Disposition"]
    client.post(f"/invoices/{invoice}/credit-notes", data={"csrf": client.csrf, "amount": "1000", "reason": "Too much"})
    assert len(query(app, "SELECT 1 FROM credit_notes WHERE invoice_id=?", invoice)) == 1  # over what's left to credit
    client.post(f"/invoices/{invoice}/credit-notes", data={"csrf": client.csrf, "amount": "960", "reason": "Cancelled"})
    i = inv(app, invoice)
    assert i["credited"] == 120_000 and i["paid_date"] == TODAY.isoformat()  # settled by credit
    assert query(app, "SELECT number FROM credit_notes WHERE invoice_id=? ORDER BY id", invoice)[1][0] == "CN-0002"
    assert client.get("/invoices").status_code == 200


def test_credit_notes_come_off_the_vat_quarter(app, client, invoice):
    import re
    def quarter_vat():
        page = client.get("/invoices").get_data(as_text=True)
        return re.search(r"Output VAT this quarter</p><p class=\"stat-value\">([^<]+)<", page).group(1)
    before = quarter_vat()
    client.post(f"/invoices/{invoice}/credit-notes", data={"csrf": client.csrf, "amount": "120", "reason": "Discount"})
    after = quarter_vat()
    to_p = lambda s: int(s.replace("£", "").replace(",", "").replace(".", ""))
    assert to_p(before) - to_p(after) == 2_000


# --- Late payment charges ---------------------------------------------------------------------------------------------

def test_late_payment_charges_follow_the_act(app, client, invoice):
    page = client.get(f"/invoices/{invoice}").get_data(as_text=True)
    assert "Late payment charges" not in page  # not due yet
    assert client.post(f"/invoices/{invoice}/late-charges", data={"csrf": client.csrf}).status_code == 302
    assert inv(app, invoice)["late_interest"] == 0
    run(app, "UPDATE invoices SET due_date=? WHERE id=?", (TODAY - timedelta(days=30)).isoformat(), invoice)
    page = client.get(f"/invoices/{invoice}").get_data(as_text=True)
    # 8% + 3.75% on £1,200 for 30 days is £11.58; £70 compensation for a debt of £1,000 to £9,999.99.
    assert "£11.58" in page and "£70.00" in page and "11.75% a year" in page
    client.post(f"/invoices/{invoice}/late-charges", data={"csrf": client.csrf})
    i = inv(app, invoice)
    assert (i["late_interest"], i["late_compensation"], i["late_charged_on"]) == (1_158, 7_000, TODAY.isoformat())
    assert client.get(f"/invoices/{invoice}/pdf").data.startswith(b"%PDF")
    pay(client, invoice, "1200")
    assert inv(app, invoice)["paid_date"] is None  # the charges are still owed
    client.post(f"/invoices/{invoice}/late-charges", data={"csrf": client.csrf, "action": "remove"})
    assert inv(app, invoice)["late_interest"] == 0


def test_the_reference_rate_is_a_setting(app, client, invoice):
    client.post("/settings/payments", data={"csrf": client.csrf, "late_rate": "4.25"})
    assert query(app, "SELECT late_rate_bp FROM workspaces WHERE id=?", app.ws)[0][0] == 425
    client.post("/settings/payments", data={"csrf": client.csrf, "late_rate": "lots"})
    assert query(app, "SELECT late_rate_bp FROM workspaces WHERE id=?", app.ws)[0][0] == 425
    import payments
    with app.app_context():
        w = query(app, "SELECT * FROM workspaces WHERE id=?", app.ws)[0]
        i = dict(inv(app, invoice)) | {"due_date": (TODAY - timedelta(days=10)).isoformat(), "net": 1_000_000, "vat": 200_000}
        assert payments.late_claim(i, w)["compensation"] == 10_000  # £10,000 or more
        assert payments.late_claim(i | {"net": 50_000, "vat": 0}, w)["compensation"] == 4_000  # under £1,000


# --- The payment page and Stripe ----------------------------------------------------------------------------------------

def test_payment_page_is_private_and_shows_what_is_left(app, client, invoice):
    token = inv(app, invoice)["pay_token"]
    assert token and len(token) >= 20
    visitor = app.test_client()
    pay(client, invoice, "200")
    page = visitor.get(f"/pay/{token}").get_data(as_text=True)
    assert "Left to pay" in page and "£1,000.00" in page and "by card" not in page
    assert visitor.get(f"/pay/{token}/pdf").data.startswith(b"%PDF")
    assert visitor.get("/pay/not-a-real-token").status_code == 404
    assert visitor.post(f"/pay/{token}/card").status_code == 409  # Stripe isn't connected


def test_connecting_stripe(app, client, member_client, stripe):
    assert member_client.get("/settings/payments/stripe").status_code == 403
    start = client.get("/settings/payments/stripe")
    target = urlsplit(start.headers["Location"])
    params = parse_qs(target.query)
    assert target.netloc == "connect.stripe.com" and params["client_id"] == ["ca_test"] and params["scope"] == ["read_write"]
    bad = client.get("/settings/payments/stripe/return?code=good-code&state=forged")
    assert bad.status_code == 302 and query(app, "SELECT stripe_account_id FROM workspaces WHERE id=?", app.ws)[0][0] is None
    assert connect(app, client, stripe).status_code == 302
    assert tuple(query(app, "SELECT stripe_account_id, stripe_account_name FROM workspaces WHERE id=?", app.ws)[0]) == \
        ("acct_thistle", "Thistle Ltd")
    assert "Thistle Ltd" in client.get("/settings/payments").get_data(as_text=True)
    client.post("/settings/payments/stripe/disconnect", data={"csrf": client.csrf})
    assert stripe.calls[-1][1] == "/oauth/deauthorize" and stripe.calls[-1][2]["stripe_user_id"] == "acct_thistle"
    assert query(app, "SELECT stripe_account_id FROM workspaces WHERE id=?", app.ws)[0][0] is None


def test_card_payment_is_recorded_once(app, client, stripe, invoice):
    connect(app, client, stripe)
    pay(client, invoice, "200")
    token = inv(app, invoice)["pay_token"]
    visitor = app.test_client()
    assert "Pay £1,000.00 by card" in visitor.get(f"/pay/{token}").get_data(as_text=True)
    resp = visitor.post(f"/pay/{token}/card")
    assert resp.status_code == 303 and resp.headers["Location"] == "https://checkout.stripe.test/cs_test_1"
    method, path, params, account, _ = stripe.calls[-1]
    assert account == "acct_thistle" and params["line_items"][0]["price_data"]["unit_amount"] == 100_000
    assert params["success_url"].endswith(f"/pay/{token}?session_id={{CHECKOUT_SESSION_ID}}")
    # Back from Stripe before it has cleared: nothing recorded yet.
    assert "being processed" in visitor.get(f"/pay/{token}?session_id=cs_test_1").get_data(as_text=True)
    stripe.sessions["cs_test_1"]["payment_status"] = "paid"
    assert "has gone through" in visitor.get(f"/pay/{token}?session_id=cs_test_1").get_data(as_text=True)
    event = {"type": "checkout.session.completed", "account": "acct_thistle", "data": {"object": stripe.sessions["cs_test_1"]}}
    assert connect_webhook(app, event).status_code == 200  # Stripe's own message arrives too
    payments = query(app, "SELECT amount, method, stripe_session FROM invoice_payments WHERE invoice_id=? ORDER BY id", invoice)
    assert [tuple(p) for p in payments] == [(20_000, "Bank transfer", None), (100_000, "Card", "cs_test_1")]
    assert inv(app, invoice)["paid_date"] == TODAY.isoformat()
    assert "Paid in full" in visitor.get(f"/pay/{token}").get_data(as_text=True)


def test_connect_webhook_checks_signature_and_account(app, client, stripe, rival, invoice):
    connect(app, client, stripe)
    session = {"id": "cs_forged", "payment_status": "paid", "amount_total": 120_000,
               "metadata": {"invoice_id": str(invoice), "workspace_id": str(app.ws)}}
    event = {"type": "checkout.session.completed", "account": "acct_thistle", "data": {"object": session}}
    assert connect_webhook(app, event, secret="whsec_wrong").status_code == 400
    run(app, "UPDATE workspaces SET stripe_account_id='acct_rival' WHERE id=?", app.rival_ws)
    rival_event = dict(event, account="acct_rival")  # another business's Stripe account can't pay our invoices
    assert connect_webhook(app, rival_event).status_code == 200
    assert connect_webhook(app, dict(event, account="acct_unknown")).status_code == 200
    assert not query(app, "SELECT 1 FROM invoice_payments WHERE invoice_id=?", invoice)
    connect_webhook(app, {"type": "account.application.deauthorized", "account": "acct_thistle", "data": {"object": {}}})
    assert query(app, "SELECT stripe_account_id FROM workspaces WHERE id=?", app.ws)[0][0] is None


def test_emails_link_to_the_payment_page_once_stripe_is_connected(app, client, stripe, outbox, invoice):
    connect(app, client, stripe)
    client.post(f"/invoices/{invoice}/email", data={"csrf": client.csrf, "contact_id": "", "email": "accounts@customer.co.uk"})
    token = inv(app, invoice)["pay_token"]
    assert f"/pay/{token}" in outbox[-1]["text"] and f"/pay/{token}" in outbox[-1]["html"]


# --- Reminders --------------------------------------------------------------------------------------------------------

def test_reminder_before_the_due_date_in_your_own_words(app, client, outbox, invoice):
    run(app, "UPDATE invoices SET sent_to=NULL WHERE workspace_id=?", app.ws)
    run(app, "UPDATE invoices SET due_date=?, sent_to='accounts@customer.co.uk' WHERE id=?",
        (TODAY + timedelta(days=2)).isoformat(), invoice)
    number = inv(app, invoice)["number"]
    client.post("/settings/payments", data={
        "csrf": client.csrf, "late_rate": "3.75", "reminders_on": "on", "remind_before": "on",
        "subject_-3": "Heads up: {number} is due {due_date}", "body_-3": "Hello {first_name},\n\n{amount_due} is due. {nope}",
        "subject_3": "", "body_3": ""})
    assert len(query(app, "SELECT 1 FROM reminder_templates WHERE workspace_id=?", app.ws)) == 1
    assert app.test_client().get("/cron/sync", headers=CRON).get_json()["reminders"] == 1
    msg = [m for m in outbox if m["to"] == ["accounts@customer.co.uk"]][-1]
    assert msg["subject"] == f"Heads up: {number} is due {(TODAY + timedelta(days=2)).strftime('%d/%m/%Y')}"
    assert "Hello there," in msg["text"] and "£1,200.00 is due. {nope}" in msg["text"]
    assert app.test_client().get("/cron/sync", headers=CRON).get_json()["reminders"] == 0  # once
    assert query(app, "SELECT stage FROM invoice_reminders WHERE invoice_id=?", invoice)[0][0] == -3
    # Switched off: no reminder before the due date.
    client.post("/settings/payments", data={"csrf": client.csrf, "late_rate": "3.75", "reminders_on": "on"})
    run(app, "DELETE FROM invoice_reminders")
    assert app.test_client().get("/cron/sync", headers=CRON).get_json()["reminders"] == 0


def test_reminders_ask_for_what_is_left(app, client, outbox, invoice):
    run(app, "UPDATE invoices SET sent_to=NULL WHERE workspace_id=?", app.ws)
    run(app, "UPDATE invoices SET due_date=?, sent_to='accounts@customer.co.uk' WHERE id=?",
        (TODAY - timedelta(days=4)).isoformat(), invoice)
    pay(client, invoice, "1000")
    client.post(f"/invoices/{invoice}/remind", data={"csrf": client.csrf})
    assert "£200.00" in outbox[-1]["text"] and "friendly reminder" in outbox[-1]["text"]


# --- Recurring invoices -----------------------------------------------------------------------------------------------

def schedule_form(app, client, **changes):
    company = first_id(app, "companies", app.ws)
    contact = query(app, "SELECT id FROM contacts WHERE workspace_id=? AND company_id=? AND email IS NOT NULL ORDER BY id",
                    app.ws, company)[0][0]
    data = {"csrf": client.csrf, "company_id": company, "contact_id": contact, "description": "Support retainer",
            "frequency": "monthly", "start_date": TODAY.isoformat(), "owner": MEMBER[0],
            "line_desc_0": "Support", "line_qty_0": "1", "line_price_0": "500", "line_vat_0": "20",
            "line_desc_1": "Hosting", "line_qty_1": "2", "line_price_1": "25", "line_vat_1": "20"} | changes
    return client.post("/invoices/recurring", data=data)


def test_recurring_invoices_are_raised_and_emailed(app, client, outbox):
    assert schedule_form(app, client).status_code == 302
    r = query(app, "SELECT * FROM recurring_invoices WHERE workspace_id=?", app.ws)[0]
    assert r["next_date"] == TODAY.isoformat() and r["anchor_day"] == TODAY.day
    assert "£660.00" in client.get("/invoices/recurring").get_data(as_text=True)
    before = query(app, "SELECT COUNT(*) FROM invoices WHERE workspace_id=?", app.ws)[0][0]
    assert app.test_client().get("/cron/sync", headers=CRON).get_json()["recurring_invoices"] == 1
    new = query(app, "SELECT * FROM invoices WHERE workspace_id=? ORDER BY id DESC LIMIT 1", app.ws)[0]
    assert query(app, "SELECT COUNT(*) FROM invoices WHERE workspace_id=?", app.ws)[0][0] == before + 1
    assert new["net"] + new["vat"] == 66_000 and new["recurring_id"] == r["id"] and new["sent_to"]
    assert any(m["subject"].startswith(f"Invoice {new['number']}") for m in outbox)
    r = query(app, "SELECT * FROM recurring_invoices WHERE id=?", r["id"])[0]
    assert r["next_date"] == date(2026, 11, 16).isoformat() and r["last_invoice_id"] == new["id"] and not r["last_error"]
    assert app.test_client().get("/cron/sync", headers=CRON).get_json()["recurring_invoices"] == 0  # not due again yet
    member_id = query(app, "SELECT id FROM users WHERE name=?", MEMBER[0])[0][0]
    assert query(app, "SELECT title FROM notifications WHERE user_id=? ORDER BY id DESC", member_id)[0][0].startswith(
        f"Recurring invoice {new['number']} raised")


def test_month_ends_and_end_dates(app, client):
    import recurring
    assert recurring.add_months(date(2027, 1, 31), 1, 31) == date(2027, 2, 28)
    assert recurring.add_months(date(2027, 2, 28), 1, 31) == date(2027, 3, 31)
    assert recurring.add_months(date(2027, 11, 30), 3, 30) == date(2028, 2, 29)
    assert recurring.add_months(date(2026, 12, 15), 12, 15) == date(2027, 12, 15)
    schedule_form(app, client, end_date=(TODAY + timedelta(days=10)).isoformat(), frequency="quarterly")
    app.config["CRON_SECRET"] = "cron-secret"
    app.test_client().get("/cron/sync", headers=CRON)
    assert query(app, "SELECT active FROM recurring_invoices")[0][0] == 0  # that was the last one


def test_recurring_invoices_are_checked_and_can_be_paused(app, client, rival):
    assert schedule_form(app, client, start_date=(TODAY - timedelta(days=1)).isoformat()).status_code == 302
    assert not query(app, "SELECT 1 FROM recurring_invoices")  # can't start in the past
    schedule_form(app, client, line_price_0="nope")
    assert not query(app, "SELECT 1 FROM recurring_invoices")
    other_contact = query(app, "SELECT id FROM contacts WHERE workspace_id=? AND company_id<>? ORDER BY id", app.ws,
                          first_id(app, "companies", app.ws))[0][0]
    schedule_form(app, client, contact_id=other_contact)
    assert not query(app, "SELECT 1 FROM recurring_invoices")  # the contact must work at the customer
    schedule_form(app, client)
    sid = query(app, "SELECT id FROM recurring_invoices")[0][0]
    client.post("/invoices/recurring", data={"csrf": client.csrf, "schedule_id": sid, "action": "pause"})
    assert query(app, "SELECT active FROM recurring_invoices")[0][0] == 0
    assert rival.post("/invoices/recurring", data={"csrf": rival.csrf, "schedule_id": sid, "action": "stop"}).status_code == 404
    assert 'value="Support retainer"' not in rival.get(f"/invoices/recurring?edit={sid}").get_data(as_text=True)
    company = first_id(app, "companies", app.ws)
    run(app, "DELETE FROM invoices WHERE company_id=?", company)
    from conftest import query as q
    client.post(f"/companies/{company}/delete", data={"csrf": client.csrf})
    assert q(app, "SELECT 1 FROM companies WHERE id=?", company)  # kept: it has a recurring invoice
    client.post("/invoices/recurring", data={"csrf": client.csrf, "schedule_id": sid, "action": "stop"})
    assert not query(app, "SELECT 1 FROM recurring_invoices")


# --- Isolation and the API --------------------------------------------------------------------------------------------

def test_payments_stay_in_their_own_workspace(app, client, rival, invoice):
    assert pay(rival, invoice, "100").status_code == 404
    client.post(f"/invoices/{invoice}/credit-notes", data={"csrf": client.csrf, "amount": "10", "reason": "Goodwill"})
    note = query(app, "SELECT id FROM credit_notes")[0][0]
    assert rival.get(f"/credit-notes/{note}/pdf").status_code == 404
    assert rival.post(f"/invoices/{invoice}/late-charges", data={"csrf": rival.csrf}).status_code == 404
    rival_invoice = query(app, "SELECT id FROM invoices WHERE workspace_id=? ORDER BY id LIMIT 1", app.rival_ws)[0][0]
    assert client.post(f"/invoices/{rival_invoice}/credit-notes", data={"csrf": client.csrf, "amount": "1",
                                                                         "reason": "x"}).status_code == 404


def test_api_shows_the_balance(app, client, invoice):
    import re
    page = client.post("/settings/api/keys", data={"csrf": client.csrf, "name": "Books", "access": "read"})
    key = re.search(r'id="new-key" value="(cae_[^"]+)"', page.get_data(as_text=True)).group(1)
    pay(client, invoice, "300")
    data = app.test_client().get(f"/api/v1/invoices/{invoice}", headers={"Authorization": f"Bearer {key}"}).get_json()
    assert data["paid_pence"] == 30_000 and data["balance_pence"] == 90_000 and data["gross_pence"] == 120_000
