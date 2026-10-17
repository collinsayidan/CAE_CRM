import hashlib
import hmac
import json
import time
from datetime import timedelta

import pytest

from conftest import ADMIN, TODAY, first_id, login, query

WEBHOOK_SECRET = "whsec_test_billing"


class FakeStripe:
    """Stands in for the Stripe API: remembers what was asked and answers like Stripe would."""

    def __init__(self, workspace_id):
        self.calls = []
        self.sub = {"id": "sub_1", "customer": "cus_1", "status": "active", "cancel_at_period_end": False,
                    "metadata": {"workspace_id": str(workspace_id)},
                    "items": {"data": [{"id": "si_1", "quantity": 2, "current_period_end": 1798761600}]}}

    def request(self, method, path, params):
        self.calls.append((method, path, params))
        if path == "/checkout/sessions":
            return {"id": "cs_test_1", "url": "https://checkout.stripe.test/cs_test_1"}
        if path.startswith("/checkout/sessions/"):
            return {"client_reference_id": self.sub["metadata"]["workspace_id"], "subscription": self.sub}
        if path == "/subscriptions/sub_1":
            return self.sub
        if path == "/subscription_items/si_1":
            self.sub["items"]["data"][0]["quantity"] = params["quantity"]
            return self.sub["items"]["data"][0]
        if path == "/billing_portal/sessions":
            return {"url": "https://billing.stripe.test/portal"}
        raise AssertionError(f"unexpected Stripe call {method} {path}")


@pytest.fixture
def stripe(app):
    fake = FakeStripe(app.ws)
    app.config.update(STRIPE_BACKEND=fake, STRIPE_PRICE_ID="price_seat", STRIPE_WEBHOOK_SECRET=WEBHOOK_SECRET,
                      STRIPE_TAX_RATE_ID="txr_vat20", BILLING_EXEMPT="")
    return fake


def set_trial(app, ws_id, days_from_today):
    with app.app_context():
        from db import get_db
        get_db().execute("UPDATE workspaces SET trial_ends=? WHERE id=?", ((TODAY + timedelta(days=days_from_today)).isoformat(), ws_id))
        get_db().commit()


def add_contact(client):
    return client.post("/contacts", data={"csrf": client.csrf, "first_name": "Ada", "last_name": "Byron",
                                          "lawful_basis": "Contract", "email": "ada.byron@example.co.uk"})


def webhook(app, event, secret=WEBHOOK_SECRET):
    body = json.dumps(event).encode()
    stamp = int(time.time())
    sig = hmac.new(secret.encode(), f"{stamp}.".encode() + body, hashlib.sha256).hexdigest()
    return app.test_client().post("/webhooks/stripe", data=body, headers={"Stripe-Signature": f"t={stamp},v1={sig}"})


def test_billing_is_off_without_stripe(app, client):
    assert "Billing is off" in client.get("/billing").get_data(as_text=True)
    set_trial(app, app.ws, -30)
    assert add_contact(client).status_code == 302
    assert query(app, "SELECT COUNT(*) FROM contacts WHERE email='ada.byron@example.co.uk'")[0][0] == 1


def test_new_workspaces_start_a_trial(app, client, stripe):
    plan, ends = query(app, "SELECT plan_status, trial_ends FROM workspaces WHERE id=?", app.ws)[0]
    assert plan == "trialing" and ends == (TODAY + timedelta(days=14)).isoformat()
    assert "14 days left in your free trial" in client.get("/billing").get_data(as_text=True)
    set_trial(app, app.ws, 5)
    assert "5 days left in your free trial" in client.get("/contacts").get_data(as_text=True)


def test_after_the_trial_the_workspace_is_read_only(app, client, stripe):
    set_trial(app, app.ws, -1)
    page = client.get("/contacts").get_data(as_text=True)
    assert "Read-only." in page
    resp = add_contact(client)
    assert resp.status_code == 302 and resp.headers["Location"] == "/billing"
    assert query(app, "SELECT COUNT(*) FROM contacts WHERE email='ada.byron@example.co.uk'")[0][0] == 0
    deal = first_id(app, "deals", app.ws)
    assert client.post(f"/deals/{deal}/stage", data={"csrf": client.csrf, "stage": "Won"},
                       headers={"X-Requested-With": "fetch"}).status_code == 402
    # Still allowed: reading, exporting, and UK GDPR erasure.
    assert client.get("/export/contacts").status_code == 200
    contact = first_id(app, "contacts", app.ws)
    client.post(f"/contacts/{contact}/erase", data={"csrf": client.csrf})
    assert query(app, "SELECT COUNT(*) FROM contacts WHERE id=?", contact)[0][0] == 0


def test_subscribing_keeps_the_trial_and_charges_per_user_plus_vat(app, client, stripe):
    resp = client.post("/billing/checkout", data={"csrf": client.csrf})
    assert resp.status_code == 303 and resp.headers["Location"].startswith("https://checkout.stripe.test/")
    params = stripe.calls[0][2]
    assert params["line_items"] == [{"price": "price_seat", "quantity": 2}]  # admin and member
    assert params["subscription_data"]["default_tax_rates"] == ["txr_vat20"]
    assert params["subscription_data"]["metadata"]["workspace_id"] == str(app.ws)
    assert "trial_end" in params["subscription_data"] and params["tax_id_collection"] == {"enabled": True}
    assert "{CHECKOUT_SESSION_ID}" in params["success_url"]

    client.get("/billing/return?session_id=cs_test_1")
    status, customer, seats = query(app, "SELECT plan_status, stripe_customer_id, seats FROM workspaces WHERE id=?", app.ws)[0]
    assert (status, customer, seats) == ("active", "cus_1", 2)
    set_trial(app, app.ws, -10)  # trial dates no longer matter once subscribed
    assert add_contact(client).status_code == 302
    portal = client.post("/billing/portal", data={"csrf": client.csrf})
    assert portal.status_code == 303 and portal.headers["Location"] == "https://billing.stripe.test/portal"


def test_members_cannot_change_billing(app, member_client, stripe):
    assert member_client.get("/billing").status_code == 200
    assert member_client.post("/billing/checkout", data={"csrf": member_client.csrf}).status_code == 403
    assert not stripe.calls


def test_webhooks_track_the_subscription(app, client, stripe):
    client.post("/billing/checkout", data={"csrf": client.csrf})
    client.get("/billing/return?session_id=cs_test_1")
    assert webhook(app, {"type": "customer.subscription.updated", "data": {"object": stripe.sub}}, secret="wrong").status_code == 400
    stripe.sub["status"] = "past_due"
    assert webhook(app, {"type": "customer.subscription.updated", "data": {"object": stripe.sub}}).status_code == 200
    assert "Payment overdue" in client.get("/contacts").get_data(as_text=True)
    assert add_contact(client).status_code == 302  # still allowed while Stripe retries
    stripe.sub["status"] = "canceled"
    webhook(app, {"type": "customer.subscription.deleted", "data": {"object": stripe.sub}})
    set_trial(app, app.ws, -10)
    resp = client.post("/contacts", data={"csrf": client.csrf, "first_name": "Bo", "last_name": "Peep",
                                          "lawful_basis": "Contract"})
    assert resp.headers["Location"] == "/billing"


def test_adding_and_removing_people_updates_the_seats(app, client, stripe):
    client.post("/billing/checkout", data={"csrf": client.csrf})
    client.get("/billing/return?session_id=cs_test_1")
    client.post("/team", data={"csrf": client.csrf, "name": "New Starter", "email": "new@example.co.uk",
                               "password": "fresh temporary pass", "role": "member"})
    assert ("POST", "/subscription_items/si_1", {"quantity": 3, "proration_behavior": "create_prorations"}) in stripe.calls
    newbie = query(app, "SELECT id FROM users WHERE email='new@example.co.uk'")[0][0]
    client.post(f"/team/{newbie}/remove", data={"csrf": client.csrf})
    assert stripe.calls[-1][2]["quantity"] == 2
    assert query(app, "SELECT seats FROM workspaces WHERE id=?", app.ws)[0][0] == 2


def test_exempt_workspaces_never_pay(app, client, stripe):
    app.config["BILLING_EXEMPT"] = f"999, {app.ws}"
    set_trial(app, app.ws, -60)
    assert "Free of charge" in client.get("/billing").get_data(as_text=True)
    assert add_contact(client).status_code == 302
    assert query(app, "SELECT COUNT(*) FROM contacts WHERE email='ada.byron@example.co.uk'")[0][0] == 1


def test_a_webhook_only_touches_its_own_workspace(app, client, rival, stripe):
    stripe.sub["metadata"]["workspace_id"] = str(app.rival_ws)
    stripe.sub["status"] = "canceled"
    webhook(app, {"type": "customer.subscription.updated", "data": {"object": stripe.sub}})
    assert query(app, "SELECT plan_status FROM workspaces WHERE id=?", app.ws)[0][0] == "trialing"
    assert query(app, "SELECT plan_status FROM workspaces WHERE id=?", app.rival_ws)[0][0] == "canceled"
