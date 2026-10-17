"""Xero: send CAE CRM invoices to Xero as approved sales invoices, and mark them paid here when they're paid in Xero.
Xero stays the accounting record; CAE CRM keeps the sales view. VAT uses Xero's UK tax types."""

import re
from datetime import datetime, timezone

from flask import current_app, flash, redirect, request, url_for

import auth
from core import get_or_404, log_event, now, one, rows, workspace, ws
from db import get_db
from integrations import IntegrationError, access_token, connection, http, record_sync

API = "https://api.xero.com/api.xro/2.0"
TAX_TYPES = {20: "OUTPUT2", 5: "RROUTPUT", 0: "ZERORATEDOUTPUT"}  # Xero UK: standard, reduced, zero rated


def headers(conn):
    return {"Authorization": f"Bearer {access_token(conn)}", "xero-tenant-id": conn["tenant_id"]}


def invoice_payload(i, company, lines, vat_registered):
    account = current_app.config.get("XERO_SALES_ACCOUNT") or "200"
    if not lines:  # invoices from the first release have no lines
        lines = [dict(description=i["description"], quantity=1, unit_price=i["net"], discount_pct=0, vat_rate=i["vat_rate"])]
    return {"Invoices": [{
        "Type": "ACCREC", "Contact": {"Name": company["name"]}, "InvoiceNumber": i["number"],
        "Reference": (i["description"] or "")[:255], "Date": i["issue_date"], "DueDate": i["due_date"],
        "CurrencyCode": "GBP", "LineAmountTypes": "Exclusive", "Status": "AUTHORISED",
        "LineItems": [{"Description": li["description"], "Quantity": li["quantity"], "UnitAmount": li["unit_price"] / 100,
                       "DiscountRate": li["discount_pct"] or None, "AccountCode": account,
                       "TaxType": TAX_TYPES.get(li["vat_rate"], "OUTPUT2") if vat_registered else "NONE"} for li in lines],
    }]}


def push(conn, invoice_id):
    """Send one invoice to Xero. Returns Xero's id. Raises IntegrationError."""
    i = get_or_404("invoices", invoice_id)
    if i["xero_invoice_id"]:
        return i["xero_invoice_id"]
    company = one("SELECT name FROM companies WHERE id=?", i["company_id"])
    lines = rows("SELECT * FROM invoice_lines WHERE workspace_id=? AND invoice_id=? ORDER BY id", ws(), invoice_id)
    data = http("PUT", f"{API}/Invoices", headers=headers(conn),
                json_body=invoice_payload(i, company, lines, workspace()["vat_registered"]))
    xero_id = data["Invoices"][0]["InvoiceID"]
    db = get_db()
    db.execute("UPDATE invoices SET xero_invoice_id=? WHERE id=? AND workspace_id=?", (xero_id, invoice_id, ws()))
    log_event(f"Invoice {i['number']} sent to Xero", company_id=i["company_id"], deal_id=i["deal_id"])
    db.commit()
    return xero_id


def xero_date(value):
    """Xero's "/Date(1729123200000+0000)/" to an ISO date."""
    m = re.search(r"/Date\((\d+)", value or "")
    return datetime.fromtimestamp(int(m.group(1)) / 1000, timezone.utc).date().isoformat() if m else None


def sync_payments(conn):
    """Mark invoices paid here once they're fully paid in Xero."""
    pending = rows("SELECT id, number, company_id, deal_id, xero_invoice_id FROM invoices WHERE workspace_id=? "
                   "AND xero_invoice_id IS NOT NULL AND paid_date IS NULL ORDER BY id LIMIT 100", conn["workspace_id"])
    paid = 0
    if pending:
        data = http("GET", f"{API}/Invoices", headers=headers(conn),
                    params={"IDs": ",".join(p["xero_invoice_id"] for p in pending)})
        by_id = {x["InvoiceID"]: x for x in data.get("Invoices") or []}
        db = get_db()
        for p in pending:
            x = by_id.get(p["xero_invoice_id"])
            if x and x.get("Status") == "PAID":
                when = xero_date(x.get("FullyPaidOnDate")) or now().date().isoformat()
                db.execute("UPDATE invoices SET paid_date=? WHERE id=?", (when, p["id"]))
                log_event(f"Invoice {p['number']} paid", "Payment recorded in Xero.", company_id=p["company_id"],
                          deal_id=p["deal_id"])
                paid += 1
        db.commit()
    record_sync(conn["id"])
    return f"Xero: {paid} {'invoice' if paid == 1 else 'invoices'} marked paid."


def register(app):

    @app.post("/invoices/<int:invoice_id>/xero")
    def invoice_to_xero(invoice_id):
        auth.admin_required()
        conn = connection("xero")
        if not conn:
            flash("Connect Xero under Integrations first.", "error")
            return redirect(url_for("invoice", invoice_id=invoice_id))
        try:
            push(conn, invoice_id)
            flash("Invoice sent to Xero.", "ok")
        except IntegrationError as e:
            flash(f"Not sent to Xero. {e}", "error")
        return redirect(request.form.get("next") or url_for("invoice", invoice_id=invoice_id))

    @app.post("/integrations/xero/push-all")
    def xero_push_all():
        auth.admin_required()
        conn = connection("xero")
        if not conn:
            return redirect(url_for("integrations"))
        sent, problems = 0, []
        for i in rows("SELECT id, number FROM invoices WHERE workspace_id=? AND xero_invoice_id IS NULL ORDER BY id LIMIT 50", ws()):
            try:
                push(conn, i["id"])
                sent += 1
            except IntegrationError as e:
                problems.append(f"{i['number']}: {e}")
        flash(f"{sent} {'invoice' if sent == 1 else 'invoices'} sent to Xero." + (f" Not sent: {'; '.join(problems[:3])}" if problems else ""),
              "error" if problems else "ok")
        return redirect(url_for("integrations"))
