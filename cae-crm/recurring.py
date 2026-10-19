"""Recurring invoices: the same invoice raised monthly, quarterly or yearly for a customer, and emailed to their
contact with the PDF attached. The daily job (integrations.cron_sync) raises the ones that are due, one per schedule a
day, and tells the owner. A schedule that starts on the 31st falls on the last day of shorter months."""

import calendar
import json
from datetime import date

from flask import abort, current_app, flash, g, redirect, render_template, request, url_for

import ukfmt
from core import get_or_404, log_event, now, one, owned, rows, today, workspace, ws
from db import get_db

FREQUENCIES = {"monthly": ("Monthly", 1), "quarterly": ("Every quarter", 3), "yearly": ("Yearly", 12)}
MAX_LINES = 6


def add_months(d, months, anchor_day):
    """The date `months` after d, on anchor_day or the last day of that month if it's shorter."""
    month = d.month - 1 + months
    year, month = d.year + month // 12, month % 12 + 1
    return date(year, month, min(anchor_day, calendar.monthrange(year, month)[1]))


def lines_of(r):
    return [tuple(li) for li in json.loads(r["lines"])]


def schedule_total(lines, vat_registered):
    from ukfmt import vat_amount
    net = sum(qty * price for _, qty, price, _ in lines)
    vat = sum(vat_amount(qty * price, rate if vat_registered else 0) for _, qty, price, rate in lines)
    return net + vat


def run_due(limit=100):
    """For the daily job: raise and email each recurring invoice that's due. Returns how many were raised."""
    import mail
    from crm import notify_owner
    from documents import send_invoice
    from finance import raise_invoice
    db = get_db()
    raised = 0
    due = rows("SELECT * FROM recurring_invoices WHERE active=1 AND next_date <= ? ORDER BY next_date, id LIMIT ?",
               today().isoformat(), limit)
    for r in due:
        g.public_workspace = r["workspace_id"]
        g.pop("workspace", None)
        months = FREQUENCIES[r["frequency"]][1]
        following = add_months(date.fromisoformat(r["next_date"]), months, r["anchor_day"])
        ended = bool(r["end_date"] and following.isoformat() > r["end_date"])
        company = one("SELECT id FROM companies WHERE id=? AND workspace_id=?", r["company_id"], r["workspace_id"])
        if company is None:
            db.execute("UPDATE recurring_invoices SET active=0, last_error=? WHERE id=?", ("The customer was deleted.", r["id"]))
            db.commit()
            continue
        items = [(desc, qty, price, 0, rate) for desc, qty, price, rate in lines_of(r)]
        invoice_id, number, gross = raise_invoice(r["company_id"], r["description"], items, recurring_id=r["id"])
        error = None
        contact = one("SELECT * FROM contacts WHERE id=? AND workspace_id=?", r["contact_id"], r["workspace_id"]) \
            if r["contact_id"] else None
        if contact and contact["email"] and mail.configured():
            i = one("SELECT * FROM invoices WHERE id=?", invoice_id)
            try:
                send_invoice(i, workspace(), contact["email"], f"{contact['first_name']} {contact['last_name']}")
                db.execute("UPDATE invoices SET sent_at=?, sent_to=? WHERE id=?",
                           (now().isoformat(timespec="minutes"), contact["email"].lower(), invoice_id))
                log_event(f"Invoice {number} emailed", f"Sent to {contact['email']} on schedule, PDF attached.", kind="email",
                          author="CAE CRM", company_id=r["company_id"], contact_id=contact["id"])
            except mail.MailError as e:
                error = f"Invoice {number} was raised but not emailed: {e}"
        else:
            error = f"Invoice {number} was raised but not emailed, as there's no contact with an email address" + \
                    ("" if mail.configured() else " or email isn't switched on") + "."
        db.execute("UPDATE recurring_invoices SET next_date=?, active=?, last_invoice_id=?, last_error=? WHERE id=?",
                   (following.isoformat(), 0 if ended else 1, invoice_id, error, r["id"]))
        if r["owner"]:
            notify_owner(r["owner"], f"Recurring invoice {number} raised for {ukfmt.money(gross, pennies=True)}",
                         error or ("The last one on this schedule." if ended else None),
                         url_for("invoice", invoice_id=invoice_id))
        db.commit()
        raised += 1
    g.pop("public_workspace", None)
    g.pop("workspace", None)
    return raised


def register(app):

    def form_values(f, w):
        """(values for the table, error) from the schedule form."""
        company_id = owned("companies", f.get("company_id"))
        contact_id = owned("contacts", f.get("contact_id")) if f.get("contact_id") else None
        description = (f.get("description") or "").strip()[:200]
        frequency = f.get("frequency") if f.get("frequency") in FREQUENCIES else None
        try:
            start = date.fromisoformat(f.get("start_date") or "")
            end = date.fromisoformat(f["end_date"]) if f.get("end_date") else None
        except ValueError:
            return None, "Enter the dates as dates."
        lines = []
        for n in range(MAX_LINES):
            desc = (f.get(f"line_desc_{n}") or "").strip()[:200]
            if not desc:
                continue
            qty = int(f.get(f"line_qty_{n}") or 1) if (f.get(f"line_qty_{n}") or "1").isdigit() else 0
            price = ukfmt.parse_money(f.get(f"line_price_{n}"))
            rate = int(f.get(f"line_vat_{n}") or 20) if (f.get(f"line_vat_{n}") or "20").isdigit() else -1
            if not (qty and price and rate in ukfmt.VAT_RATES):
                return None, f"Check line {n + 1}: it needs a quantity, a price in £ and a VAT rate."
            lines.append((desc, qty, price, rate))
        if not (company_id and description and frequency and lines):
            return None, "Choose a customer and how often, describe the invoice and add at least one line."
        if contact_id and not one("SELECT 1 FROM contacts WHERE id=? AND company_id=?", contact_id, company_id):
            return None, "The contact to email must work at that customer."
        if end and end < start:
            return None, "The end date is before the start date."
        team = [r[0] for r in rows("SELECT name FROM users WHERE workspace_id=?", ws())]
        return dict(company_id=company_id, contact_id=contact_id, description=description, lines=json.dumps(lines),
                    frequency=frequency, end_date=end.isoformat() if end else None,
                    owner=f.get("owner") if f.get("owner") in team else g.user["name"]), start

    def page(edit=None, form=None):
        w = workspace()
        schedules = rows("SELECT r.*, c.name AS company, ct.first_name, ct.last_name, ct.email FROM recurring_invoices r "
                         "JOIN companies c ON c.id=r.company_id LEFT JOIN contacts ct ON ct.id=r.contact_id "
                         "WHERE r.workspace_id=? ORDER BY r.active DESC, r.next_date", ws())
        totals = {r["id"]: schedule_total(lines_of(r), w["vat_registered"]) for r in schedules}
        companies = rows("SELECT id, name FROM companies WHERE workspace_id=? ORDER BY name", ws())
        contacts = rows("SELECT id, company_id, first_name, last_name, email FROM contacts WHERE workspace_id=? "
                        "AND email IS NOT NULL AND email <> '' AND company_id IS NOT NULL ORDER BY first_name", ws())
        team = [r[0] for r in rows("SELECT name FROM users WHERE workspace_id=? ORDER BY name", ws())]
        lines = lines_of(edit) if edit else []
        return render_template("recurring.html", schedules=schedules, totals=totals, companies=companies,
                               contacts=contacts, team=team, edit=edit, lines=lines, frequencies=FREQUENCIES,
                               max_lines=MAX_LINES, vat_rates=ukfmt.VAT_RATES, add_months=add_months,
                               today=today(), from_iso=date.fromisoformat)

    @app.route("/invoices/recurring", methods=["GET", "POST"])
    def recurring_invoices():
        if request.method == "GET":
            edit = None
            if request.args.get("edit", "").isdigit():
                edit = one("SELECT * FROM recurring_invoices WHERE id=? AND workspace_id=?", int(request.args["edit"]), ws())
            return page(edit)
        f = request.form
        db = get_db()
        schedule = None
        if f.get("schedule_id", "").isdigit():
            schedule = one("SELECT * FROM recurring_invoices WHERE id=? AND workspace_id=?", int(f["schedule_id"]), ws())
            if schedule is None:
                abort(404)
        action = f.get("action", "save")
        if schedule and action in ("pause", "resume", "stop"):
            if action == "resume" and schedule["next_date"] < today().isoformat():
                # Don't send a backlog of invoices for the months it was paused: carry on from the next date to come.
                months, nxt = FREQUENCIES[schedule["frequency"]][1], date.fromisoformat(schedule["next_date"])
                while nxt < today():
                    nxt = add_months(nxt, months, schedule["anchor_day"])
                db.execute("UPDATE recurring_invoices SET next_date=? WHERE id=?", (nxt.isoformat(), schedule["id"]))
            if action == "stop":
                db.execute("DELETE FROM recurring_invoices WHERE id=?", (schedule["id"],))
                flash("Recurring invoice stopped. Invoices already raised are kept.", "ok")
            else:
                db.execute("UPDATE recurring_invoices SET active=? WHERE id=?", (int(action == "resume"), schedule["id"]))
                flash("Recurring invoice " + ("resumed." if action == "resume" else "paused."), "ok")
            db.commit()
            return redirect(url_for("recurring_invoices"))
        values, start = form_values(f, workspace())
        if values is None:
            flash(f"Recurring invoice not saved. {start}", "error")
            return redirect(url_for("recurring_invoices", edit=schedule["id"] if schedule else None))
        if schedule:
            changes = dict(values)
            if start.isoformat() != schedule["next_date"]:
                if start < today():
                    flash("Recurring invoice not saved. The next invoice date can't be in the past.", "error")
                    return redirect(url_for("recurring_invoices", edit=schedule["id"]))
                changes.update(next_date=start.isoformat(), anchor_day=start.day)
            db.execute(f"UPDATE recurring_invoices SET {', '.join(f'{k}=?' for k in changes)} WHERE id=?",
                       (*changes.values(), schedule["id"]))
            flash("Recurring invoice saved.", "ok")
        else:
            if start < today():
                flash("Recurring invoice not saved. The first invoice date can't be in the past.", "error")
                return redirect(url_for("recurring_invoices"))
            db.insert("recurring_invoices", workspace_id=ws(), next_date=start.isoformat(), anchor_day=start.day, active=1,
                      created_by=g.user["name"], created_at=now().isoformat(timespec="minutes"), **values)
            company = one("SELECT name FROM companies WHERE id=?", values["company_id"])
            log_event(f"Recurring invoice set up ({FREQUENCIES[values['frequency']][0].lower()})",
                      f"{values['description']}, starting {ukfmt.uk_date(start)}.", company_id=values["company_id"])
            flash(f"Recurring invoice set up for {company['name']}. The first is raised on {ukfmt.uk_date(start)}.", "ok")
        db.commit()
        return redirect(url_for("recurring_invoices"))
