"""Getting paid: payments against invoices (in part or in full), credit notes, late payment charges under the Late
Payment of Commercial Debts (Interest) Act 1998, each invoice's private payment page, and card payments through the
business's own Stripe account.

Card payments use Stripe Connect. An admin clicks Connect Stripe and signs in to their own Stripe account; CAE CRM
keeps only the account's id. The payment page opens Stripe Checkout on that account, so the money goes straight to the
business and Stripe's fees are theirs. Stripe tells us about payments through the Connect webhook, and the payment page
checks the Checkout session itself when the customer comes back, so a payment is recorded even if one of the two is
late. Either way it's recorded once.

Every amount is in pence. An invoice's balance is its total, plus any late payment charges, less credit notes and
payments. It's paid when nothing is left."""

import json
import secrets
from datetime import date

from flask import abort, current_app, flash, g, redirect, render_template, request, session, url_for

import auth
import stripe_api
from core import get_or_404, log_event, now, one, rows, today, workspace, ws
from db import get_db
from events import emit
from ukfmt import money, parse_money, uk_date

METHODS = ("Bank transfer", "Card", "Cash", "Cheque", "Other")
STATUTORY_MARGIN_BP = 800  # the Act's interest is 8% over the Bank of England reference rate
MIN_CARD_PAYMENT = 30  # Stripe's smallest charge in pence


def total(i):
    return i["net"] + i["vat"]


def late_charges(i):
    return i["late_interest"] + i["late_compensation"]


def balance(i):
    """What's left to pay, in pence. Negative if the customer has paid more than they owe."""
    return total(i) + late_charges(i) - i["credited"] - i["amount_paid"]


def money_p(pence):
    return money(pence, pennies=True)


def pay_token(i):
    """The invoice's private payment page token, made the first time it's needed. No commit."""
    if i["pay_token"]:
        return i["pay_token"]
    token = secrets.token_urlsafe(18)
    get_db().execute("UPDATE invoices SET pay_token=? WHERE id=?", (token, i["id"]))
    return token


def pay_url(i, external=False):
    return url_for("pay_invoice", token=pay_token(i), _external=external)


def card_ready(business):
    return bool(stripe_api.connect_configured() and business["stripe_account_id"])


def refresh(invoice_id, reopen=False):
    """Recalculate an invoice's paid and credited totals from its payments and credit notes, and mark it paid when
    nothing is left. reopen clears the paid date if something is left again (a payment deleted). Returns True if it
    has just become paid. No commit."""
    db = get_db()
    paid = int(one("SELECT COALESCE(SUM(amount), 0) FROM invoice_payments WHERE invoice_id=?", invoice_id)[0])
    credited = int(one("SELECT COALESCE(SUM(net + vat), 0) FROM credit_notes WHERE invoice_id=?", invoice_id)[0])
    db.execute("UPDATE invoices SET amount_paid=?, credited=? WHERE id=?", (paid, credited, invoice_id))
    i = one("SELECT * FROM invoices WHERE id=?", invoice_id)
    left = balance(i)
    if left <= 0 and not i["paid_date"]:
        last = one("SELECT MAX(paid_on) FROM invoice_payments WHERE invoice_id=?", invoice_id)[0]
        db.execute("UPDATE invoices SET paid_date=? WHERE id=?", (last or today().isoformat(), invoice_id))
        return True
    if left > 0 and i["paid_date"] and reopen:
        db.execute("UPDATE invoices SET paid_date=NULL WHERE id=?", (invoice_id,))
    return False


def record_payment(i, amount, paid_on, method, reference=None, by=None, stripe_session=None):
    """Add a payment to an invoice, with its timeline entry and events. Returns True if that paid it off. No commit."""
    db = get_db()
    db.insert("invoice_payments", workspace_id=i["workspace_id"], invoice_id=i["id"], amount=amount,
              paid_on=paid_on, method=method, reference=(reference or "")[:120] or None, stripe_session=stripe_session,
              recorded_by=by, created_at=now().isoformat(timespec="minutes"))
    log_event(f"Payment of {money_p(amount)} received for invoice {i['number']}",
              f"{method}{', reference ' + reference if reference else ''}, on {uk_date(paid_on)}.",
              company_id=i["company_id"], deal_id=i["deal_id"])
    emit("invoice.payment_received", i["id"], amount_gbp=amount / 100, method=method)
    became_paid = refresh(i["id"])
    if became_paid:
        log_event(f"Invoice {i['number']} paid", company_id=i["company_id"], deal_id=i["deal_id"])
        emit("invoice.paid", i["id"])
    return became_paid


def late_claim(i, business, on=None):
    """What the business could claim under the Late Payment Act on an overdue invoice, or None. Interest is simple
    interest at 8% over the reference rate on what's left of the invoice, for each day after the due date; fixed
    compensation depends on the size of the debt."""
    on = on or today()
    days = (on - date.fromisoformat(i["due_date"])).days
    owed = total(i) - i["credited"] - i["amount_paid"]
    if days <= 0 or owed <= 0 or i["paid_date"]:
        return None
    rate_bp = (business["late_rate_bp"] or 0) + STATUTORY_MARGIN_BP
    interest = owed * rate_bp * days // (10_000 * 365)
    compensation = 4000 if owed < 100_000 else 7000 if owed < 1_000_000 else 10_000
    return dict(days=days, owed=owed, rate=rate_bp / 100, interest=interest, compensation=compensation,
                total=interest + compensation, daily=owed * rate_bp // (10_000 * 365))


def credit_note_lines(c, i):
    rate = i["vat_rate"] if i["vat_rate"] >= 0 else (round(c["vat"] * 100 / c["net"]) if c["net"] else 0)
    return [dict(description=f"Credit against invoice {i['number']}: {c['reason']}", quantity=1, unit_price=c["net"],
                 discount_pct=0, vat_rate=rate, net=c["net"], vat=c["vat"])]


def credit_note_pdf(c, i, business):
    from documents import render_pdf, vat_totals, gbp
    company = one("SELECT * FROM companies WHERE id=?", i["company_id"])
    lines = credit_note_lines(c, i)
    facts = [("Credit note number", c["number"]), ("Date", uk_date(c["issue_date"])), ("Against invoice", i["number"])]
    totals = vat_totals(c["net"], c["vat"], lines, business) + [("Total credit in GBP", gbp(c["net"] + c["vat"]), True)]
    notes = [("About this credit note", f"This reduces what's owed on invoice {i['number']} by {money_p(c['net'] + c['vat'])}.")]
    return render_pdf("Credit note", c["number"], facts, business, company, lines, totals, notes)


def next_credit_number(workspace_id):
    count = one("SELECT COUNT(*) FROM credit_notes WHERE workspace_id=?", workspace_id)[0]
    return f"CN-{count + 1:04d}"


def apply_checkout(workspace_id, cs):
    """Record a completed Stripe Checkout session on its invoice, once. Returns the invoice or None. No commit."""
    if cs.get("payment_status") != "paid":
        return None
    meta = cs.get("metadata") or {}
    if str(meta.get("workspace_id")) != str(workspace_id) or not str(meta.get("invoice_id", "")).isdigit():
        return None
    i = one("SELECT * FROM invoices WHERE id=? AND workspace_id=?", int(meta["invoice_id"]), workspace_id)
    if i is None or one("SELECT 1 FROM invoice_payments WHERE stripe_session=?", cs["id"]):
        return i
    g.public_workspace = workspace_id
    record_payment(i, int(cs.get("amount_total") or 0), today().isoformat(), "Card", cs.get("payment_intent") or cs["id"],
                   by="Stripe", stripe_session=cs["id"])
    from crm import notify_owner
    company = one("SELECT owner FROM companies WHERE id=?", i["company_id"])
    if company and company["owner"]:
        notify_owner(company["owner"], f"{money_p(int(cs.get('amount_total') or 0))} paid by card on invoice {i['number']}",
                     url=url_for("invoice", invoice_id=i["id"]))
    return i


def register(app):

    def back_to(invoice_id):
        return redirect(url_for("invoice", invoice_id=invoice_id) + "#payments")

    # --- On the invoice page --------------------------------------------------------------------------------------

    @app.post("/invoices/<int:invoice_id>/payments")
    def add_payment(invoice_id):
        i = get_or_404("invoices", invoice_id)
        f = request.form
        amount = parse_money(f.get("amount"))
        method = f.get("method") if f.get("method") in METHODS else None
        try:
            paid_on = date.fromisoformat(f.get("paid_on") or today().isoformat())
        except ValueError:
            paid_on = None
        if not amount or not method or not paid_on or paid_on > today():
            flash("Payment not recorded. Enter the amount in £, how it was paid and a date that isn't in the future.", "error")
            return back_to(invoice_id)
        if amount > max(balance(i), 0) + 100:  # a pound over is fine (bank charges, rounding); more is likely a typo
            flash(f"Payment not recorded. Only {money_p(max(balance(i), 0))} is left to pay on {i['number']}.", "error")
            return back_to(invoice_id)
        paid = record_payment(i, amount, paid_on.isoformat(), method, (f.get("reference") or "").strip(), g.user["name"])
        get_db().commit()
        flash(f"Payment of {money_p(amount)} recorded." + (f" Invoice {i['number']} is now paid." if paid else ""), "ok")
        return back_to(invoice_id)

    @app.post("/invoices/<int:invoice_id>/payments/<int:payment_id>/delete")
    def delete_payment(invoice_id, payment_id):
        auth.admin_required()
        i = get_or_404("invoices", invoice_id)
        p = one("SELECT * FROM invoice_payments WHERE id=? AND invoice_id=? AND workspace_id=?", payment_id, invoice_id, ws())
        if p is None:
            abort(404)
        if p["stripe_session"]:
            flash("Card payments can't be deleted here. Refund them in Stripe, then record a credit note.", "error")
            return back_to(invoice_id)
        db = get_db()
        db.execute("DELETE FROM invoice_payments WHERE id=?", (payment_id,))
        refresh(invoice_id, reopen=True)
        log_event(f"Payment of {money_p(p['amount'])} removed from invoice {i['number']}", f"By {g.user['name']}.",
                  company_id=i["company_id"], deal_id=i["deal_id"])
        db.commit()
        flash("Payment removed.", "ok")
        return back_to(invoice_id)

    @app.post("/invoices/<int:invoice_id>/credit-notes")
    def add_credit_note(invoice_id):
        i = get_or_404("invoices", invoice_id)
        amount = parse_money(request.form.get("amount"))
        reason = (request.form.get("reason") or "").strip()[:200]
        room = total(i) - i["credited"]
        if not amount or not reason:
            flash("Credit note not raised. Enter the amount in £, including VAT, and a reason.", "error")
            return back_to(invoice_id)
        if amount > room:
            flash(f"Credit note not raised. You can credit up to {money_p(room)} on {i['number']}.", "error")
            return back_to(invoice_id)
        vat = round(amount * i["vat"] / total(i)) if total(i) else 0  # the same share of VAT as the invoice
        db = get_db()
        number = next_credit_number(ws())
        db.insert("credit_notes", workspace_id=ws(), invoice_id=invoice_id, number=number, reason=reason,
                  net=amount - vat, vat=vat, issue_date=today().isoformat(), created_by=g.user["name"])
        log_event(f"Credit note {number} raised for {money_p(amount)}", f"Against invoice {i['number']}: {reason}",
                  company_id=i["company_id"], deal_id=i["deal_id"])
        emit("credit_note.created", invoice_id, number=number, amount_gbp=amount / 100)
        if refresh(invoice_id):
            log_event(f"Invoice {i['number']} paid", "Settled by credit note.", company_id=i["company_id"], deal_id=i["deal_id"])
            emit("invoice.paid", invoice_id)
        db.commit()
        refund = i["amount_paid"] > total(i) - i["credited"] - amount
        flash(f"Credit note {number} raised." + (" The customer has paid more than they now owe, so a refund is due."
                                                 if refund else ""), "ok")
        return back_to(invoice_id)

    @app.get("/credit-notes/<int:credit_note_id>/pdf")
    def credit_note_pdf_view(credit_note_id):
        from documents import pdf_response
        c = one("SELECT * FROM credit_notes WHERE id=? AND workspace_id=?", credit_note_id, ws())
        if c is None:
            abort(404)
        i = one("SELECT * FROM invoices WHERE id=?", c["invoice_id"])
        return pdf_response(credit_note_pdf(c, i, workspace()), f"{c['number']}.pdf", request.args.get("download") == "1")

    @app.post("/invoices/<int:invoice_id>/late-charges")
    def late_charges_update(invoice_id):
        i = get_or_404("invoices", invoice_id)
        db = get_db()
        if request.form.get("action") == "remove":
            db.execute("UPDATE invoices SET late_interest=0, late_compensation=0, late_charged_on=NULL WHERE id=?", (invoice_id,))
            log_event(f"Late payment charges removed from invoice {i['number']}", f"By {g.user['name']}.",
                      company_id=i["company_id"], deal_id=i["deal_id"])
            refresh(invoice_id)
            db.commit()
            flash("Late payment charges removed.", "ok")
            return back_to(invoice_id)
        claim = late_claim(i, workspace())
        if claim is None:
            flash("Only an unpaid invoice past its due date can have late payment charges.", "error")
            return back_to(invoice_id)
        db.execute("UPDATE invoices SET late_interest=?, late_compensation=?, late_charged_on=? WHERE id=?",
                   (claim["interest"], claim["compensation"], today().isoformat(), invoice_id))
        log_event(f"Late payment charges of {money_p(claim['total'])} added to invoice {i['number']}",
                  f"Interest of {money_p(claim['interest'])} ({claim['rate']:.2f}% a year for {claim['days']} days) and "
                  f"fixed compensation of {money_p(claim['compensation'])}, under the Late Payment of Commercial Debts "
                  f"(Interest) Act 1998. By {g.user['name']}.", company_id=i["company_id"], deal_id=i["deal_id"])
        db.commit()
        flash(f"Late payment charges of {money_p(claim['total'])} added. They're on the payment page and the PDF.", "ok")
        return back_to(invoice_id)

    # --- The customer's payment page ------------------------------------------------------------------------------

    def invoice_by_token(token):
        i = one("SELECT * FROM invoices WHERE pay_token=?", token) if token and len(token) < 60 else None
        if i is None:
            abort(404)
        g.public_workspace = i["workspace_id"]
        return i

    def pay_page(i, notice=None, status=200):
        from documents import logo_url
        business = workspace()
        company = one("SELECT name FROM companies WHERE id=?", i["company_id"])
        credits = rows("SELECT number, net, vat, issue_date FROM credit_notes WHERE invoice_id=? ORDER BY id", i["id"])
        payments = rows("SELECT amount, paid_on, method FROM invoice_payments WHERE invoice_id=? ORDER BY paid_on, id", i["id"])
        left = balance(i)
        return render_template("public/pay.html", business=business, logo=logo_url(business), i=i, company=company,
                               credits=credits, payments=payments, left=left, total=total(i), late=late_charges(i),
                               card=card_ready(business) and left >= MIN_CARD_PAYMENT and not i["paid_date"],
                               notice=notice, token=i["pay_token"]), status

    @app.get("/pay/<token>")
    def pay_invoice(token):
        i = invoice_by_token(token)
        notice = None
        session_id = request.args.get("session_id", "")
        business = workspace()
        if session_id.startswith("cs_") and len(session_id) < 200 and card_ready(business):
            try:
                cs = stripe_api.request("GET", f"/checkout/sessions/{session_id}", account=business["stripe_account_id"])
                if apply_checkout(i["workspace_id"], cs):
                    get_db().commit()
                    i = one("SELECT * FROM invoices WHERE id=?", i["id"])
                notice = ("Thank you, your payment has gone through." if cs.get("payment_status") == "paid"
                          else "Thank you. Your payment is being processed, and this page will update once it clears.")
            except stripe_api.StripeError:
                notice = "Thank you. We're confirming your payment with Stripe, which can take a minute."
        elif request.args.get("cancelled"):
            notice = "Payment cancelled. Nothing has been taken."
        return pay_page(i, notice)

    @app.get("/pay/<token>/pdf")
    def pay_invoice_pdf(token):
        from documents import invoice_pdf, pdf_response
        i = invoice_by_token(token)
        return pdf_response(invoice_pdf(i, workspace()), f"{i['number']}.pdf", True)

    @app.post("/pay/<token>/card")
    def pay_by_card(token):
        i = invoice_by_token(token)
        business = workspace()
        left = balance(i)
        if not card_ready(business) or i["paid_date"] or left < MIN_CARD_PAYMENT:
            return pay_page(i, "Card payments aren't available for this invoice.", 409)
        base = url_for("pay_invoice", token=token, _external=True)
        try:
            cs = stripe_api.request("POST", "/checkout/sessions", {
                "mode": "payment",
                "line_items": [{"quantity": 1, "price_data": {"currency": "gbp", "unit_amount": left,
                                                              "product_data": {"name": f"Invoice {i['number']}"}}}],
                "success_url": base + "?session_id={CHECKOUT_SESSION_ID}",
                "cancel_url": base + "?cancelled=1",
                "client_reference_id": str(i["id"]),
                "customer_email": i["sent_to"] or None,
                "metadata": {"invoice_id": i["id"], "workspace_id": i["workspace_id"], "invoice_number": i["number"]},
                "payment_intent_data": {"description": f"Invoice {i['number']} from {business['name']}",
                                        "metadata": {"invoice_id": i["id"], "invoice_number": i["number"]}},
            }, account=business["stripe_account_id"])
        except stripe_api.StripeError as e:
            current_app.logger.warning("Checkout for invoice %s failed: %s", i["id"], e)
            return pay_page(i, "Sorry, card payments aren't working just now. Please try again later, or pay by bank "
                               "transfer.", 502)
        return redirect(cs["url"], 303)

    @app.post("/webhooks/stripe-connect")
    def stripe_connect_webhook():
        payload = request.get_data()
        if not stripe_api.verify_webhook(payload, request.headers.get("Stripe-Signature", ""),
                                         current_app.config.get("STRIPE_CONNECT_WEBHOOK_SECRET")):
            abort(400)
        event = json.loads(payload)
        account = event.get("account") or ""
        w = one("SELECT id FROM workspaces WHERE stripe_account_id=?", account) if account else None
        if w is None:
            return "", 200  # not one of ours, or since disconnected
        kind = event.get("type", "")
        obj = (event.get("data") or {}).get("object") or {}
        if kind in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
            apply_checkout(w["id"], obj)
        elif kind == "account.application.deauthorized":
            get_db().execute("UPDATE workspaces SET stripe_account_id=NULL, stripe_account_name=NULL WHERE id=?", (w["id"],))
        get_db().commit()
        return "", 200

    # --- Settings ---------------------------------------------------------------------------------------------------

    @app.get("/settings/payments/stripe")
    def stripe_connect():
        auth.admin_required()
        if not stripe_api.connect_configured():
            abort(404)
        state = secrets.token_urlsafe(24)
        session["stripe_connect_state"] = state
        from urllib.parse import urlencode
        params = {"response_type": "code", "client_id": current_app.config.get("STRIPE_CONNECT_CLIENT_ID", ""),
                  "scope": "read_write", "state": state, "redirect_uri": url_for("stripe_connect_return", _external=True)}
        return redirect(f"{stripe_api.CONNECT}/oauth/authorize?{urlencode(params)}")

    @app.get("/settings/payments/stripe/return")
    def stripe_connect_return():
        import hmac
        auth.admin_required()
        if not stripe_api.connect_configured():
            abort(404)
        expected = session.pop("stripe_connect_state", "")
        if not (expected and hmac.compare_digest(expected, request.args.get("state", ""))):
            flash("Stripe wasn't connected. Please try again from this page.", "error")
            return redirect(url_for("payment_settings"))
        if request.args.get("error") or not request.args.get("code"):
            flash("Stripe wasn't connected. " + (request.args.get("error_description") or "You cancelled at Stripe.")[:200],
                  "error")
            return redirect(url_for("payment_settings"))
        try:
            token = stripe_api.request("POST", "/oauth/token", {"grant_type": "authorization_code",
                                                                "code": request.args["code"]}, oauth=True)
            account_id = token["stripe_user_id"]
            try:
                acct = stripe_api.request("GET", f"/accounts/{account_id}")
                name = ((acct.get("settings") or {}).get("dashboard") or {}).get("display_name") \
                    or (acct.get("business_profile") or {}).get("name") or acct.get("email") or account_id
            except stripe_api.StripeError:
                name = account_id
        except (stripe_api.StripeError, KeyError) as e:
            flash(f"Stripe wasn't connected. {e}", "error")
            return redirect(url_for("payment_settings"))
        db = get_db()
        db.execute("UPDATE workspaces SET stripe_account_id=?, stripe_account_name=?, stripe_connected_at=?, "
                   "stripe_connected_by=? WHERE id=?", (account_id, str(name)[:120], now().isoformat(timespec="minutes"),
                                                       g.user["name"], ws()))
        db.commit()
        flash(f"Stripe connected ({name}). Customers can now pay invoices by card.", "ok")
        return redirect(url_for("payment_settings"))

    @app.post("/settings/payments/stripe/disconnect")
    def stripe_disconnect():
        auth.admin_required()
        w = workspace()
        if w["stripe_account_id"]:
            try:
                stripe_api.request("POST", "/oauth/deauthorize", {
                    "client_id": current_app.config.get("STRIPE_CONNECT_CLIENT_ID", ""),
                    "stripe_user_id": w["stripe_account_id"]}, oauth=True)
            except stripe_api.StripeError as e:  # disconnect here anyway; they can remove us in Stripe too
                current_app.logger.warning("Stripe deauthorise failed for workspace %s: %s", w["id"], e)
        get_db().execute("UPDATE workspaces SET stripe_account_id=NULL, stripe_account_name=NULL WHERE id=?", (ws(),))
        get_db().commit()
        flash("Stripe disconnected. Customers can still pay by bank transfer.", "ok")
        return redirect(url_for("payment_settings"))

    @app.route("/settings/payments", methods=["GET", "POST"])
    def payment_settings():
        from documents import REMINDER_STAGES, STAGE_NAMES, reminder_template, DEFAULT_REMINDERS
        auth.admin_required()
        w = workspace()
        db = get_db()
        if request.method == "POST":
            f = request.form
            raw = (f.get("late_rate") or "").replace("%", "").strip()
            try:
                rate_bp = round(float(raw) * 100)
                if not 0 <= rate_bp <= 2000:
                    raise ValueError
            except ValueError:
                flash("Not saved. Enter the reference rate as a percentage, for example 3.75.", "error")
                return redirect(url_for("payment_settings"))
            db.execute("UPDATE workspaces SET reminders_on=?, remind_before=?, late_rate_bp=? WHERE id=?",
                       (int(f.get("reminders_on") == "on"), int(f.get("remind_before") == "on"), rate_bp, ws()))
            for stage in REMINDER_STAGES:
                subject = (f.get(f"subject_{stage}") or "").strip()[:200]
                body = (f.get(f"body_{stage}") or "").strip()[:4000]
                db.execute("DELETE FROM reminder_templates WHERE workspace_id=? AND stage=?", (ws(), stage))
                if subject and body and (subject, body) != DEFAULT_REMINDERS[stage]:
                    db.insert("reminder_templates", workspace_id=ws(), stage=stage, subject=subject, body=body)
            db.commit()
            flash("Payment settings saved.", "ok")
            return redirect(url_for("payment_settings"))
        templates = [(s, STAGE_NAMES[s], *reminder_template(w["id"], s)) for s in REMINDER_STAGES]
        return render_template("payment_settings.html", w=w, templates=templates, connect=stripe_api.connect_configured(),
                               rate=f"{(w['late_rate_bp'] or 0) / 100:.2f}")
