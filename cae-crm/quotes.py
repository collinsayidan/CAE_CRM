"""Quotes: priced from a deal's line items, shared with the customer as a private link, accepted online with a typed
signature (valid for most UK commercial contracts under the Electronic Communications Act 2000), then invoiced."""

import secrets
from datetime import timedelta

from flask import abort, flash, g, redirect, render_template, request, url_for

import mail
from events import emit
from core import back, get_or_404, log_event, now, one, owned, rows, today, workspace, ws
from db import get_db, next_quote_number
from finance import raise_invoice
from ukfmt import money, uk_date, vat_amount

QUOTE_STATUSES = ["Draft", "Sent", "Accepted", "Declined"]
VALID_DAYS = 30
DEFAULT_TERMS = ("Prices are in pounds sterling and exclude VAT unless shown. This quote is valid until the date above. "
                 "Work starts once the quote is accepted. Invoices are payable within our usual payment terms.")


def quote_state(q, on=None):
    """Draft, Sent, Accepted, Declined, or Expired for a sent quote past its expiry date."""
    if q["status"] == "Sent" and q["expiry_date"] < (on or today()).isoformat():
        return "Expired"
    return q["status"]


def price_lines(lines, vat_registered):
    """(description, qty, unit price, discount %, VAT rate) -> priced rows, VAT per line as on invoices."""
    priced = []
    for desc, qty, price, discount, rate in lines:
        rate = rate if vat_registered else 0
        net = qty * price * (100 - discount) // 100
        priced.append(dict(description=desc, quantity=qty, unit_price=price, discount_pct=discount, vat_rate=rate,
                           net=net, vat=vat_amount(net, rate)))
    return priced


def vat_summary(lines):
    by_rate = {}
    for li in lines:
        net, vat = by_rate.get(li["vat_rate"], (0, 0))
        by_rate[li["vat_rate"]] = (net + li["net"], vat + li["vat"])
    return sorted(by_rate.items(), reverse=True)


def quote_lines(quote_id):
    return rows("SELECT * FROM quote_lines WHERE workspace_id=? AND quote_id=? ORDER BY id", ws(), quote_id)


def links(q):
    return dict(deal_id=q["deal_id"], company_id=q["company_id"], contact_id=q["contact_id"])


def tell_owner(q, title, body):
    """Notify the person who owns the quote's deal, or whoever drafted it."""
    from notifications import notify, user_named
    owner = one("SELECT owner FROM deals WHERE id=?", q["deal_id"])["owner"] if q["deal_id"] else q["created_by"]
    notify([user_named(owner, q["workspace_id"])], title, body, url_for("quote", quote_id=q["id"]), q["workspace_id"])


def client_ip():
    # Vercel puts the visitor's address in X-Real-IP and overwrites any value the visitor sends.
    return (request.headers.get("X-Real-IP") or (request.access_route[0] if request.access_route else "")
            or request.remote_addr or "")[:64]


def public_quote_or_404(token):
    q = one("SELECT * FROM quotes WHERE token=?", token) if token and len(token) < 80 else None
    if q is None or q["status"] == "Draft":
        abort(404)
    g.public_workspace = q["workspace_id"]
    return q


def register(app):

    @app.route("/quotes")
    def quotes():
        status = request.args.get("status", "")
        data = rows("SELECT q.*, c.name AS company, d.title AS deal FROM quotes q JOIN companies c ON c.id=q.company_id "
                    "LEFT JOIN deals d ON d.id=q.deal_id WHERE q.workspace_id=? ORDER BY q.id DESC", ws())
        table = [(q, quote_state(q)) for q in data]
        counts = {s: sum(1 for _, st in table if st == s) for s in QUOTE_STATUSES + ["Expired"]}
        if status:
            table = [(q, st) for q, st in table if st == status]
        open_value = sum(q["net"] for q, st in [(q, quote_state(q)) for q in data] if st == "Sent")
        return render_template("quotes.html", rows=table, status=status, counts=counts, open_value=open_value,
                               statuses=QUOTE_STATUSES + ["Expired"])

    @app.post("/deals/<int:deal_id>/quote")
    def quote_deal(deal_id):
        d = get_or_404("deals", deal_id)
        lines = rows("SELECT * FROM line_items WHERE workspace_id=? AND deal_id=? ORDER BY id", ws(), deal_id)
        if lines:
            items = [(li["name"], li["quantity"], li["unit_price"], li["discount_pct"], li["vat_rate"]) for li in lines]
        elif d["value"]:
            items = [(d["title"], 1, d["value"], 0, 20)]
        else:
            flash("Add products or a value to the deal before quoting it.", "error")
            return redirect(url_for("deal", deal_id=deal_id))
        db, w, t = get_db(), workspace(), today()
        priced = price_lines(items, w["vat_registered"])
        quote_id = db.insert("quotes", workspace_id=ws(), number=next_quote_number(db, ws()), deal_id=deal_id,
                             company_id=d["company_id"], contact_id=d["contact_id"], title=d["title"],
                             terms=DEFAULT_TERMS, status="Draft", token=secrets.token_urlsafe(24),
                             net=sum(p["net"] for p in priced), vat=sum(p["vat"] for p in priced),
                             issue_date=t.isoformat(), expiry_date=(t + timedelta(days=VALID_DAYS)).isoformat(),
                             created_by=g.user["name"], created_at=now().isoformat(timespec="minutes"))
        for p in priced:
            db.insert("quote_lines", workspace_id=ws(), quote_id=quote_id, **p)
        number = one("SELECT number FROM quotes WHERE id=?", quote_id)["number"]
        log_event(f"Quote {number} drafted", f"{money(sum(p['net'] for p in priced))} excluding VAT",
                  deal_id=deal_id, company_id=d["company_id"], contact_id=d["contact_id"])
        db.commit()
        flash(f"Quote {number} drafted from the deal. Check it, then mark it as sent and share the link.", "ok")
        return redirect(url_for("quote", quote_id=quote_id))

    @app.route("/quotes/<int:quote_id>")
    def quote(quote_id):
        q = get_or_404("quotes", quote_id)
        lines = quote_lines(quote_id)
        company = one("SELECT * FROM companies WHERE id=? AND workspace_id=?", q["company_id"], ws())
        contact = one("SELECT * FROM contacts WHERE id=? AND workspace_id=?", q["contact_id"], ws()) if q["contact_id"] else None
        contacts = rows("SELECT id, first_name || ' ' || last_name AS name FROM contacts WHERE workspace_id=? AND company_id=? "
                        "ORDER BY first_name", ws(), q["company_id"])
        invoice = one("SELECT id, number FROM invoices WHERE id=? AND workspace_id=?", q["invoice_id"], ws()) if q["invoice_id"] else None
        deal = one("SELECT id, title, stage FROM deals WHERE id=? AND workspace_id=?", q["deal_id"], ws()) if q["deal_id"] else None
        return render_template("quote.html", q=q, state=quote_state(q), lines=lines, by_rate=vat_summary(lines),
                               mail_ready=mail.configured(),
                               company=company, contact=contact, contacts=contacts, invoice=invoice, deal=deal,
                               business=workspace(), public_url=url_for("public_quote", token=q["token"], _external=True))

    @app.post("/quotes/<int:quote_id>/edit")
    def edit_quote(quote_id):
        q = get_or_404("quotes", quote_id)
        if q["status"] not in ("Draft", "Sent"):
            flash("An accepted or declined quote can't be changed. Draft a new one from the deal instead.", "error")
            return redirect(url_for("quote", quote_id=quote_id))
        f = request.form
        title = f.get("title", "").strip()[:140] or q["title"]
        expiry = f.get("expiry_date", "")
        if len(expiry) != 10 or expiry < today().isoformat():
            flash("Quote not saved. Choose an expiry date from today onwards.", "error")
            return redirect(url_for("quote", quote_id=quote_id))
        contact_id = owned("contacts", f.get("contact_id"))
        get_db().execute("UPDATE quotes SET title=?, expiry_date=?, terms=?, contact_id=? WHERE id=? AND workspace_id=?",
                         (title, expiry, f.get("terms", "").strip()[:4000], contact_id, quote_id, ws()))
        get_db().commit()
        flash("Quote saved.", "ok")
        return redirect(url_for("quote", quote_id=quote_id))

    @app.post("/quotes/<int:quote_id>/send")
    def send_quote(quote_id):
        q = get_or_404("quotes", quote_id)
        if q["status"] != "Draft":
            return redirect(url_for("quote", quote_id=quote_id))
        db = get_db()
        db.execute("UPDATE quotes SET status='Sent', sent_at=? WHERE id=? AND workspace_id=?",
                   (now().isoformat(timespec="minutes"), quote_id, ws()))
        log_event(f"Quote {q['number']} sent", f"Shared by {g.user['name']}. Valid until {q['expiry_date']}.", **links(q))
        db.commit()
        flash(f"Quote {q['number']} is live. Copy the link and send it to your customer.", "ok")
        return redirect(url_for("quote", quote_id=quote_id))

    @app.post("/quotes/<int:quote_id>/email")
    def email_quote(quote_id):
        """Email the customer a link to the quote, and mark a draft as sent."""
        q = get_or_404("quotes", quote_id)
        back_to = redirect(url_for("quote", quote_id=quote_id))
        if quote_state(q) not in ("Draft", "Sent"):
            flash("Only a draft or an open quote can be emailed.", "error")
            return back_to
        contact = one("SELECT * FROM contacts WHERE id=? AND workspace_id=?", q["contact_id"], ws()) if q["contact_id"] else None
        if not contact or not contact["email"]:
            flash("Choose a contact with an email address under Details first.", "error")
            return back_to
        w = workspace()
        link = url_for("public_quote", token=q["token"], _external=True)
        gross = money(q["net"] + q["vat"], pennies=True)
        from documents import logo_url
        html = render_template("emails/notice.html", business=w, heading=f"Quote {q['number']}", logo=logo_url(w, external=True), paragraphs=[
            f"Hi {contact['first_name']},",
            f"Here's our quote for {q['title']}: {gross} including VAT, valid until {uk_date(q['expiry_date'])}.",
            "You can read it, then accept or decline it online. It only takes a minute."],
            button_url=link, button_label="View your quote",
            footer=f"Sent by {g.user['name']} at {w['legal_name'] or w['name']}. Reply to this email with any questions.")
        text = (f"Hi {contact['first_name']},\n\nHere's our quote for {q['title']}: {gross} including VAT, valid until "
                f"{uk_date(q['expiry_date'])}.\n\nRead it and accept or decline online: {link}\n\n"
                f"{g.user['name']}, {w['name']}\n")
        try:
            mail.send(mail.message(contact["email"], f"Quote {q['number']} from {w['name']}: {q['title']}", html, text,
                                   w["name"], w["reply_to"] or g.user["email"]))
        except mail.MailError as e:
            flash(f"Quote not emailed. {e}", "error")
            return back_to
        db = get_db()
        if q["status"] == "Draft":
            db.execute("UPDATE quotes SET status='Sent', sent_at=? WHERE id=? AND workspace_id=?",
                       (now().isoformat(timespec="minutes"), quote_id, ws()))
        log_event(f"Quote {q['number']} emailed", f"Sent to {contact['email']} by {g.user['name']}.", kind="email",
                  author=g.user["name"], **links(q))
        db.commit()
        flash(f"Quote {q['number']} emailed to {contact['first_name']} {contact['last_name']}.", "ok")
        return back_to

    @app.post("/quotes/<int:quote_id>/invoice")
    def invoice_quote(quote_id):
        q = get_or_404("quotes", quote_id)
        if q["status"] != "Accepted" or q["invoice_id"]:
            flash("Only an accepted quote that hasn't been invoiced can be turned into an invoice.", "error")
            return redirect(url_for("quote", quote_id=quote_id))
        items = [(li["description"], li["quantity"], li["unit_price"], li["discount_pct"], li["vat_rate"])
                 for li in quote_lines(quote_id)]
        invoice_id, number, gross = raise_invoice(q["company_id"], q["title"], items, deal_id=q["deal_id"])
        db = get_db()
        db.execute("UPDATE quotes SET invoice_id=? WHERE id=? AND workspace_id=?", (invoice_id, quote_id, ws()))
        db.commit()
        flash(f"Invoice {number} raised from quote {q['number']} for {money(gross, pennies=True)} including VAT.", "ok")
        return redirect(url_for("invoice", invoice_id=invoice_id))

    @app.post("/quotes/<int:quote_id>/delete")
    def delete_quote(quote_id):
        q = get_or_404("quotes", quote_id)
        if q["status"] == "Accepted":
            flash("Accepted quotes are kept as a record of what the customer agreed to.", "error")
            return redirect(url_for("quote", quote_id=quote_id))
        db = get_db()
        db.execute("DELETE FROM quotes WHERE id=? AND workspace_id=?", (quote_id, ws()))
        log_event(f"Quote {q['number']} deleted", f"Deleted by {g.user['name']}", **links(q))
        db.commit()
        flash(f"Quote {q['number']} deleted.", "ok")
        return redirect(url_for("deal", deal_id=q["deal_id"]) if q["deal_id"] else url_for("quotes"))

    # --- What the customer sees -------------------------------------------------

    @app.route("/q/<token>")
    def public_quote(token):
        q = public_quote_or_404(token)
        staff = g.get("user") and g.user["workspace_id"] == q["workspace_id"]
        if not q["viewed_at"] and not staff:
            db = get_db()
            db.execute("UPDATE quotes SET viewed_at=? WHERE id=?", (now().isoformat(timespec="minutes"), q["id"]))
            log_event(f"Quote {q['number']} opened by the customer", **links(q))
            db.commit()
        lines = quote_lines(q["id"])
        company = one("SELECT * FROM companies WHERE id=?", q["company_id"])
        contact = one("SELECT first_name, last_name, role FROM contacts WHERE id=?", q["contact_id"]) if q["contact_id"] else None
        return render_template("public/quote.html", q=q, state=quote_state(q), lines=lines, by_rate=vat_summary(lines),
                               company=company, contact=contact, business=workspace(), staff=staff, errors={}, embed=False,
                               form={})

    @app.post("/q/<token>/accept")
    def accept_quote(token):
        q = public_quote_or_404(token)
        if quote_state(q) != "Sent":
            return redirect(url_for("public_quote", token=token))
        f = request.form
        errors = {}
        name = f.get("signer_name", "").strip()[:120]
        if len(name.split()) < 2:
            errors["signer_name"] = "Type your full name to sign."
        if f.get("agree") != "on":
            errors["agree"] = "Tick the box to confirm you can accept on behalf of your organisation."
        if errors:
            lines = quote_lines(q["id"])
            return render_template("public/quote.html", q=q, state="Sent", lines=lines, by_rate=vat_summary(lines),
                                   company=one("SELECT * FROM companies WHERE id=?", q["company_id"]), contact=None,
                                   business=workspace(), staff=False, errors=errors, form=f, embed=False), 422
        db = get_db()
        stamp = now().isoformat(timespec="seconds")
        db.execute("UPDATE quotes SET status='Accepted', decided_at=?, signer_name=?, signer_position=?, signer_ip=?, "
                   "signer_agent=? WHERE id=? AND status='Sent'",
                   (stamp, name, f.get("signer_position", "").strip()[:120], client_ip(),
                    request.headers.get("User-Agent", "")[:300], q["id"]))
        log_event(f"Quote {q['number']} accepted", f"Signed online by {name} on {stamp[:16].replace('T', ' at ')}. "
                  f"{money(q['net'] + q['vat'], pennies=True)} including VAT.", **links(q))
        emit("quote.accepted", q["id"])
        tell_owner(q, f"Quote {q['number']} accepted by {name}", f"{money(q['net'] + q['vat'], pennies=True)} including VAT")
        deal = one("SELECT * FROM deals WHERE id=? AND workspace_id=?", q["deal_id"], q["workspace_id"]) if q["deal_id"] else None
        if deal and deal["stage"] not in ("Won", "Lost"):
            from sales import set_stage
            set_stage(deal, "Won", f"Quote {q['number']} accepted by {name}. Delivery project created.")
        if deal:
            db.insert("activities", workspace_id=q["workspace_id"], company_id=q["company_id"], contact_id=q["contact_id"],
                      deal_id=deal["id"], kind="Task", subject=f"Raise the invoice for accepted quote {q['number']}",
                      owner=deal["owner"], due_at=now().isoformat(timespec="minutes"), done=0)
        db.commit()
        return redirect(url_for("public_quote", token=token))

    @app.post("/q/<token>/decline")
    def decline_quote(token):
        q = public_quote_or_404(token)
        if quote_state(q) != "Sent":
            return redirect(url_for("public_quote", token=token))
        reason = request.form.get("reason", "").strip()[:1000]
        db = get_db()
        db.execute("UPDATE quotes SET status='Declined', decided_at=?, decline_reason=? WHERE id=? AND status='Sent'",
                   (now().isoformat(timespec="seconds"), reason, q["id"]))
        log_event(f"Quote {q['number']} declined by the customer", reason or "No reason given.", **links(q))
        emit("quote.declined", q["id"], reason=reason or None)
        tell_owner(q, f"Quote {q['number']} was declined", reason or "No reason given.")
        db.commit()
        return redirect(url_for("public_quote", token=token))
