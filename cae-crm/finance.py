"""Invoices: raised by hand or from a deal's line items, with UK VAT, aged debt and VAT-quarter totals."""

from datetime import date, timedelta

from flask import flash, redirect, render_template, request, url_for

import ukfmt
from core import back, get_or_404, log_event, one, owned, rows, today, workspace, ws
from db import get_db, next_invoice_number
from ukfmt import fy_quarter, money, vat_amount, vat_quarter


def raise_invoice(company_id, description, lines, deal_id=None):
    """Create an invoice from (description, quantity, unit price, discount %, VAT rate) lines. Returns (id, number, gross)."""
    w = workspace()
    db = get_db()
    issue = today()
    number = next_invoice_number(db, ws(), w["invoice_prefix"])
    priced = []
    for desc, qty, price, discount, rate in lines:
        rate = rate if w["vat_registered"] else 0
        net = qty * price * (100 - discount) // 100
        priced.append((desc, qty, price, discount, rate, net, vat_amount(net, rate)))
    net = sum(p[5] for p in priced)
    vat = sum(p[6] for p in priced)
    rates = {p[4] for p in priced}
    invoice_id = db.insert("invoices", workspace_id=ws(), number=number, company_id=company_id, deal_id=deal_id,
                           description=description, net=net, vat_rate=rates.pop() if len(rates) == 1 else -1, vat=vat,
                           issue_date=issue.isoformat(), due_date=(issue + timedelta(days=w["payment_terms"])).isoformat())
    for desc, qty, price, discount, rate, line_net, line_vat in priced:
        db.insert("invoice_lines", workspace_id=ws(), invoice_id=invoice_id, description=desc, quantity=qty,
                  unit_price=price, discount_pct=discount, vat_rate=rate, net=line_net, vat=line_vat)
    log_event(f"Invoice {number} raised", f"{money(net + vat, pennies=True)} including VAT",
              company_id=company_id, deal_id=deal_id)
    return invoice_id, number, net + vat


def register(app):

    @app.route("/invoices")
    def invoices():
        t = today()
        data = rows("SELECT i.*, c.name AS company FROM invoices i JOIN companies c ON c.id=i.company_id"
                    " WHERE i.workspace_id=? ORDER BY i.issue_date DESC, i.id DESC", ws())

        def state(i):
            if i["paid_date"]:
                return "Paid"
            return "Overdue" if i["due_date"] < t.isoformat() else "Due"

        table = [(i, state(i)) for i in data]
        fy_label, _, _, _ = fy_quarter(t)
        fy_start = date(t.year if t.month >= 4 else t.year - 1, 4, 1)
        vq_start, vq_end = vat_quarter(t)
        # Aged debt, the way UK credit control reports it.
        aging = {"Not yet due": 0, "1–30 days late": 0, "31–60 days late": 0, "Over 60 days late": 0}
        for i in data:
            if i["paid_date"]:
                continue
            late = (t - date.fromisoformat(i["due_date"])).days
            key = ("Not yet due" if late <= 0 else "1–30 days late" if late <= 30
                   else "31–60 days late" if late <= 60 else "Over 60 days late")
            aging[key] += i["net"] + i["vat"]
        totals = {
            "outstanding": sum(aging.values()),
            "overdue": sum(v for k, v in aging.items() if k != "Not yet due"),
            "overdue_n": sum(1 for _, s in table if s == "Overdue"),
            "paid_fy": sum(i["net"] + i["vat"] for i in data if i["paid_date"] and i["paid_date"] >= fy_start.isoformat()),
            "vat_quarter": sum(i["vat"] for i in data if vq_start.isoformat() <= i["issue_date"] < vq_end.isoformat()),
        }
        return render_template("finance.html", rows=table, totals=totals, aging=aging, fy_label=fy_label,
                               vq_start=vq_start, vq_end=vq_end - timedelta(days=1))

    @app.post("/invoices")
    def create_invoice():
        f = request.form
        net = ukfmt.parse_money(f.get("net"))
        rate = int(f.get("vat_rate", 20)) if f.get("vat_rate", "20").isdigit() else -1
        company_id = owned("companies", f.get("company_id"))
        if not (net and rate in ukfmt.VAT_RATES and company_id and f.get("description", "").strip()):
            flash("Invoice not raised. Choose a customer, describe the work and enter a net amount in £.", "error")
            return back("invoices")
        _, number, gross = raise_invoice(company_id, f["description"].strip(), [(f["description"].strip(), 1, net, 0, rate)])
        get_db().commit()
        flash(f"Invoice {number} raised for {money(gross, pennies=True)} including VAT.", "ok")
        return back("invoices")

    @app.post("/deals/<int:deal_id>/invoice")
    def invoice_deal(deal_id):
        d = get_or_404("deals", deal_id)
        lines = rows("SELECT * FROM line_items WHERE workspace_id=? AND deal_id=? ORDER BY id", ws(), deal_id)
        if lines:
            items = [(li["name"], li["quantity"], li["unit_price"], li["discount_pct"], li["vat_rate"]) for li in lines]
        elif d["value"]:
            items = [(d["title"], 1, d["value"], 0, 20)]
        else:
            flash("Add products or a value to the deal before invoicing it.", "error")
            return redirect(url_for("deal", deal_id=deal_id))
        invoice_id, number, gross = raise_invoice(d["company_id"], d["title"], items, deal_id=deal_id)
        get_db().commit()
        flash(f"Invoice {number} raised for {money(gross, pennies=True)} including VAT.", "ok")
        return redirect(url_for("invoice", invoice_id=invoice_id))

    @app.route("/invoices/<int:invoice_id>")
    def invoice(invoice_id):
        i = get_or_404("invoices", invoice_id)
        company = one("SELECT * FROM companies WHERE id=? AND workspace_id=?", i["company_id"], ws())
        lines = rows("SELECT * FROM invoice_lines WHERE workspace_id=? AND invoice_id=? ORDER BY id", ws(), invoice_id)
        if not lines:  # invoices from the first release have no lines
            lines = [dict(description=i["description"], quantity=1, unit_price=i["net"], discount_pct=0,
                          vat_rate=i["vat_rate"], net=i["net"], vat=i["vat"])]
        by_rate = {}
        for li in lines:
            net, vat = by_rate.get(li["vat_rate"], (0, 0))
            by_rate[li["vat_rate"]] = (net + li["net"], vat + li["vat"])
        return render_template("invoice.html", i=i, company=company, lines=lines, by_rate=sorted(by_rate.items(), reverse=True),
                               business=workspace())

    @app.post("/invoices/<int:invoice_id>/paid")
    def mark_paid(invoice_id):
        i = get_or_404("invoices", invoice_id)
        if i["paid_date"]:
            flash(f"Invoice {i['number']} was already marked as paid.", "ok")
            return back("invoices")
        db = get_db()
        db.execute("UPDATE invoices SET paid_date=? WHERE id=? AND workspace_id=?", (today().isoformat(), invoice_id, ws()))
        log_event(f"Invoice {i['number']} paid", company_id=i["company_id"], deal_id=i["deal_id"])
        db.commit()
        flash(f"Invoice {i['number']} marked as paid.", "ok")
        return back("invoices")

