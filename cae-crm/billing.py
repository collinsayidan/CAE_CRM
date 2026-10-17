"""Billing: a 14-day trial without a card, then a Stripe subscription priced per user a month, plus VAT.
When a trial ends unpaid or a subscription lapses, the workspace becomes read-only: people can still sign in, see and
export everything, and erase personal data, but can't add or change records until someone subscribes.

With no Stripe keys, billing is off and every workspace has full access, so the app runs anywhere without it."""

import json
from datetime import date, datetime, timedelta, timezone

from flask import abort, current_app, flash, g, jsonify, redirect, render_template, request, url_for

import auth
import stripe_api
from core import one, today, workspace, ws
from db import get_db

WRITING_STATUSES = {"active", "past_due"}
# What a read-only workspace can still do: sign out, manage its own sign-in, pay, and meet UK GDPR duties.
ALWAYS_ALLOWED = {"auth.logout", "auth.account", "auth.account_profile", "billing", "billing_checkout", "billing_portal",
                  "billing_return", "erase_contact", "oauth_disconnect", "static"}


def trial_days():
    return int(current_app.config.get("TRIAL_DAYS") or 14)


def seat_price():
    """Price per user a month in pence, before VAT, for display. Stripe's price is what's charged."""
    return int(current_app.config.get("SEAT_PRICE") or 1500)


def exempt(workspace_id):
    ids = {s.strip() for s in str(current_app.config.get("BILLING_EXEMPT") or "").split(",") if s.strip()}
    return str(workspace_id) in ids


def team_size(workspace_id):
    return one("SELECT COUNT(*) FROM users WHERE workspace_id=?", workspace_id)[0]


def trial_end(w):
    if w["trial_ends"]:
        return date.fromisoformat(w["trial_ends"][:10])
    return date.fromisoformat(w["created_at"][:10]) + timedelta(days=trial_days())


def state(w):
    """Where a workspace stands: whether billing applies, whether it can make changes, and what to tell people."""
    if not stripe_api.configured():
        return dict(enabled=False, can_write=True, status="off", exempt=False)
    if exempt(w["id"]):
        return dict(enabled=True, can_write=True, status="exempt", exempt=True)
    status = w["plan_status"] or "trialing"
    ends = trial_end(w)
    days_left = (ends - today()).days
    subscribed = bool(w["stripe_subscription_id"])
    if status in WRITING_STATUSES or (status == "trialing" and (subscribed or days_left >= 0)):
        can_write = True
    else:
        can_write = False
    if status == "trialing" and not subscribed and days_left < 0:
        status = "trial_over"
    return dict(enabled=True, can_write=can_write, status=status, exempt=False, subscribed=subscribed,
                trial_ends=ends, days_left=max(days_left, 0), seats=w["seats"], period_end=w["period_end"],
                cancelling=bool(w["cancel_at_period_end"]))


def guard_writes():
    """Called before every request. Stops changes in a read-only workspace."""
    if request.method != "POST" or not g.get("user") or request.endpoint in ALWAYS_ALLOWED:
        return None
    if state(workspace())["can_write"]:
        return None
    message = "Your workspace is read-only until someone subscribes. An admin can do this under Billing."
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify(error=message), 402
    flash(message, "error")
    return redirect(url_for("billing"))


def apply_subscription(sub, workspace_id=None):
    """Store a Stripe subscription's state on its workspace. Returns the workspace id, or None if it isn't ours."""
    db = get_db()
    workspace_id = workspace_id or (sub.get("metadata") or {}).get("workspace_id")
    if not workspace_id:
        row = one("SELECT id FROM workspaces WHERE stripe_subscription_id=? OR stripe_customer_id=?",
                  sub.get("id"), sub.get("customer"))
        workspace_id = row["id"] if row else None
    if not workspace_id or not one("SELECT 1 FROM workspaces WHERE id=?", int(workspace_id)):
        return None
    items = (sub.get("items") or {}).get("data") or [{}]
    period_end = items[0].get("current_period_end") or sub.get("current_period_end")
    db.execute("UPDATE workspaces SET plan_status=?, stripe_customer_id=?, stripe_subscription_id=?, seats=?, period_end=?, "
               "cancel_at_period_end=? WHERE id=?",
               (sub.get("status"), sub.get("customer"), sub.get("id"), items[0].get("quantity"),
                datetime.fromtimestamp(period_end, timezone.utc).date().isoformat() if period_end else None,
                int(bool(sub.get("cancel_at_period_end"))), int(workspace_id)))
    db.commit()
    return int(workspace_id)


def sync_seats(workspace_id):
    """Charge for the team as it is now, after someone is added or removed. Stripe prorates the change."""
    w = one("SELECT * FROM workspaces WHERE id=?", workspace_id)
    if not (w and w["stripe_subscription_id"] and stripe_api.configured()) or exempt(workspace_id):
        return
    seats = team_size(workspace_id)
    try:
        sub = stripe_api.request("GET", f"/subscriptions/{w['stripe_subscription_id']}")
        item = sub["items"]["data"][0]
        if item.get("quantity") != seats:
            stripe_api.request("POST", f"/subscription_items/{item['id']}",
                               {"quantity": seats, "proration_behavior": "create_prorations"})
            get_db().execute("UPDATE workspaces SET seats=? WHERE id=?", (seats, workspace_id))
            get_db().commit()
    except (stripe_api.StripeError, KeyError, IndexError):
        current_app.logger.warning("Couldn't update the number of users on workspace %s's subscription", workspace_id)
        flash("The team changed, but the subscription's number of users couldn't be updated. "
              "It will be corrected the next time someone is added or removed.", "error")


def register(app):

    @app.route("/billing")
    def billing():
        w = workspace()
        return render_template("billing.html", b=state(w), w=w, team=team_size(w["id"]), seat_price=seat_price(),
                               vat=bool(current_app.config.get("STRIPE_TAX_RATE_ID")))

    @app.post("/billing/checkout")
    def billing_checkout():
        auth.admin_required()
        w = workspace()
        b = state(w)
        if not b["enabled"] or b["exempt"]:
            return redirect(url_for("billing"))
        if b.get("subscribed") and w["plan_status"] not in ("canceled", "incomplete_expired"):
            return redirect(url_for("billing"))
        params = {
            "mode": "subscription", "client_reference_id": str(w["id"]),
            "line_items": [{"price": current_app.config["STRIPE_PRICE_ID"], "quantity": team_size(w["id"])}],
            "success_url": url_for("billing_return", _external=True) + "?session_id={CHECKOUT_SESSION_ID}",
            "cancel_url": url_for("billing", _external=True),
            "subscription_data": {"metadata": {"workspace_id": str(w["id"])}},
            "metadata": {"workspace_id": str(w["id"])},
            "billing_address_collection": "required", "tax_id_collection": {"enabled": True},
            "allow_promotion_codes": True,
        }
        if w["stripe_customer_id"]:
            params["customer"] = w["stripe_customer_id"]
            params["customer_update"] = {"name": "auto", "address": "auto"}
        else:
            params["customer_email"] = g.user["email"]
        if current_app.config.get("STRIPE_TAX_RATE_ID"):
            params["subscription_data"]["default_tax_rates"] = [current_app.config["STRIPE_TAX_RATE_ID"]]
        # Keep the rest of the free trial. Stripe needs a trial to run at least 48 more hours.
        ends = datetime.combine(trial_end(w), datetime.max.time(), timezone.utc)
        if not b.get("subscribed") and ends - datetime.now(timezone.utc) > timedelta(hours=49):
            params["subscription_data"]["trial_end"] = int(ends.timestamp())
        try:
            session = stripe_api.request("POST", "/checkout/sessions", params)
        except stripe_api.StripeError as e:
            flash(f"Couldn't open checkout. {e}", "error")
            return redirect(url_for("billing"))
        return redirect(session["url"], 303)

    @app.get("/billing/return")
    def billing_return():
        """Back from Stripe Checkout. Record the subscription now, rather than waiting for the webhook."""
        session_id = request.args.get("session_id", "")
        if session_id.startswith("cs_"):
            try:
                session = stripe_api.request("GET", f"/checkout/sessions/{session_id}", {"expand": ["subscription"]})
                if session.get("client_reference_id") == str(ws()) and isinstance(session.get("subscription"), dict):
                    apply_subscription(session["subscription"], ws())
                    flash("Thank you. Your subscription is active.", "ok")
            except stripe_api.StripeError:
                flash("Payment received. Your subscription will show here within a minute.", "ok")
        return redirect(url_for("billing"))

    @app.post("/billing/portal")
    def billing_portal():
        auth.admin_required()
        w = workspace()
        if not w["stripe_customer_id"]:
            return redirect(url_for("billing"))
        try:
            session = stripe_api.request("POST", "/billing_portal/sessions",
                                         {"customer": w["stripe_customer_id"], "return_url": url_for("billing", _external=True)})
        except stripe_api.StripeError as e:
            flash(f"Couldn't open the billing portal. {e}", "error")
            return redirect(url_for("billing"))
        return redirect(session["url"], 303)

    @app.post("/webhooks/stripe")
    def stripe_webhook():
        payload = request.get_data()
        if not stripe_api.verify_webhook(payload, request.headers.get("Stripe-Signature", ""),
                                         current_app.config.get("STRIPE_WEBHOOK_SECRET")):
            abort(400)
        event = json.loads(payload)
        obj = (event.get("data") or {}).get("object") or {}
        kind = event.get("type", "")
        if kind.startswith("customer.subscription."):
            apply_subscription(obj)
        elif kind == "checkout.session.completed" and obj.get("subscription"):
            try:
                sub = stripe_api.request("GET", f"/subscriptions/{obj['subscription']}")
                apply_subscription(sub, obj.get("client_reference_id"))
            except stripe_api.StripeError:
                return "", 500  # Stripe retries
        return "", 200
