"""Deals pipeline, products and line items, tasks, and delivery projects."""

import calendar
from collections import defaultdict
from datetime import date, datetime, timedelta

from flask import abort, flash, g, jsonify, redirect, render_template, request, url_for

import ukfmt
from core import (OPEN_SQL, advance_lifecycle, back, chosen_owner, get_or_404, log_event, one, owned, owner_names, rows,
                  scalar, today, wants_json, ws)
from crm import line_totals, render_index, resolve_links
from db import ACTIVITY_KINDS, BILLING_PERIODS, OPEN_STAGES, SOURCES, STAGE_PROBABILITY, get_db
from ukfmt import add_months, money

PROJECT_STATUSES = ["On track", "At risk", "Blocked", "Complete"]


def recalc_deal_value(deal_id):
    """A deal with line items is worth the sum of its lines, excluding VAT."""
    lines = rows("SELECT * FROM line_items WHERE workspace_id=? AND deal_id=?", ws(), deal_id)
    if lines:
        get_db().execute("UPDATE deals SET value=? WHERE id=? AND workspace_id=?", (line_totals(lines)["net"], deal_id, ws()))


def parse_line(f):
    """(name, quantity, unit price in pence, discount %, VAT rate) from a line-item form, or None if invalid."""
    name = f.get("name", "").strip()
    qty = f.get("quantity", "1").strip()
    price = ukfmt.parse_amount(f.get("unit_price"))
    discount = f.get("discount_pct", "0").strip() or "0"
    rate = f.get("vat_rate", "20")
    if not (name and qty.isdigit() and 0 < int(qty) <= 100_000 and price is not None and discount.isdigit()
            and 0 <= int(discount) <= 100 and rate.isdigit() and int(rate) in ukfmt.VAT_RATES):
        return None
    return name, int(qty), price, int(discount), int(rate)


def set_stage(deal, stage, reason=None):
    """Move a deal to a stage, with what follows from it (a delivery project when won). Returns a message. No commit."""
    db = get_db()
    closed = today().isoformat() if stage in ("Won", "Lost") else None
    db.execute("UPDATE deals SET stage=?, probability=?, closed_at=? WHERE id=? AND workspace_id=?",
               (stage, STAGE_PROBABILITY[stage], closed, deal["id"], ws()))
    links = dict(deal_id=deal["id"], company_id=deal["company_id"], contact_id=deal["contact_id"])
    if stage == "Won":
        db.insert("projects", workspace_id=ws(), company_id=deal["company_id"], deal_id=deal["id"],
                  name=f"Deliver: {deal['title']}", owner=deal["owner"], status="On track", progress=0,
                  due_date=(today() + timedelta(days=60)).isoformat())
        log_event("Deal won", reason or f"{money(deal['value'])}. Delivery project created.", **links)
        advance_lifecycle(deal["contact_id"], "Customer", f"Won the deal {deal['title']}")
        return f"Won: {deal['title']}, {money(deal['value'])}. Delivery project created."
    if stage == "Lost":
        log_event("Deal lost", reason, **links)
        return f"Marked as lost: {deal['title']}."
    log_event(f"Stage changed to {stage}", f"Was {deal['stage']}", **links)
    return f"Moved to {stage}: {deal['title']}."


def register(app):

    # --- Deals ----------------------------------------------------------------

    @app.route("/pipeline")
    def pipeline():
        if request.args.get("view") == "list":
            return render_index("deals", "deals.html", all_stages=OPEN_STAGES + ["Won", "Lost"])
        owner = request.args.get("owner", "")
        sql = (f"SELECT d.*, c.name AS company FROM deals d JOIN companies c ON c.id=d.company_id"
               f" WHERE d.workspace_id=? AND d.{OPEN_SQL}")
        args = [ws()]
        if owner in owner_names():
            sql += " AND d.owner=?"
            args.append(owner)
        columns = defaultdict(list)
        for deal in rows(sql + " ORDER BY d.close_date", *args):
            columns[deal["stage"]].append(deal)
        return render_template("pipeline.html", columns=columns, owner=owner)

    @app.post("/deals")
    def create_deal():
        f = request.form
        value = ukfmt.parse_amount(f.get("value")) if f.get("value", "").strip() else 0
        stage = f.get("stage") if f.get("stage") in OPEN_STAGES else "Lead"
        try:
            close_date = date.fromisoformat(f.get("close_date", ""))
        except ValueError:
            close_date = None
        company_id = owned("companies", f.get("company_id"))
        contact_id = owned("contacts", f.get("contact_id"))
        if not (f.get("title", "").strip() and value is not None and close_date and company_id):
            flash("Deal not added. It needs a name, a company, a value in £ and an expected close date.", "error")
            return back("pipeline")
        db = get_db()
        deal_id = db.insert("deals", workspace_id=ws(), company_id=company_id, contact_id=contact_id,
                            title=f["title"].strip(), value=value, stage=stage, probability=STAGE_PROBABILITY[stage],
                            owner=chosen_owner(f.get("owner")), source=f.get("source") if f.get("source") in SOURCES else SOURCES[0],
                            close_date=close_date.isoformat(), created_at=today().isoformat())
        log_event("Deal created", f"{f['title'].strip()}, {money(value)}, in {stage}", deal_id=deal_id,
                  company_id=company_id, contact_id=contact_id)
        advance_lifecycle(contact_id, "Opportunity", f"Linked to the deal {f['title'].strip()}")
        db.commit()
        flash(f"Deal added: {f['title'].strip()}. Add products to build its value.", "ok")
        return redirect(url_for("deal", deal_id=deal_id))

    @app.post("/deals/<int:deal_id>/stage")
    def move_deal(deal_id):
        deal = get_or_404("deals", deal_id)
        stage = request.form.get("stage")
        if stage not in STAGE_PROBABILITY:
            abort(400)
        message = set_stage(deal, stage)
        get_db().commit()
        if wants_json():
            return jsonify(ok=True, stage=stage, probability=STAGE_PROBABILITY[stage], message=message)
        flash(message, "ok")
        return back("pipeline")

    # --- Line items -------------------------------------------------------------

    @app.post("/deals/<int:deal_id>/lines")
    def add_line(deal_id):
        d = get_or_404("deals", deal_id)
        f = request.form
        product_id = owned("products", f.get("product_id"))
        db = get_db()
        if product_id and not f.get("name"):
            p = one("SELECT * FROM products WHERE id=?", product_id)
            qty = f.get("quantity", "1")
            line = (p["name"], int(qty) if qty.isdigit() and int(qty) > 0 else 1, p["unit_price"], 0, p["vat_rate"])
        else:
            line = parse_line(f)
        if not line:
            flash("Line not added. Check the quantity, price, discount (0 to 100%) and VAT rate.", "error")
            return redirect(url_for("deal", deal_id=deal_id))
        name, qty, price, discount, rate = line
        if not one("SELECT vat_registered FROM workspaces WHERE id=?", ws())["vat_registered"]:
            rate = 0
        db.insert("line_items", workspace_id=ws(), deal_id=deal_id, product_id=product_id, name=name, quantity=qty,
                  unit_price=price, discount_pct=discount, vat_rate=rate)
        recalc_deal_value(deal_id)
        log_event(f"Line item added: {qty} × {name}", deal_id=deal_id, company_id=d["company_id"])
        db.commit()
        return redirect(url_for("deal", deal_id=deal_id) + "#line-items")

    @app.post("/deals/<int:deal_id>/lines/<int:line_id>")
    def edit_line(deal_id, line_id):
        get_or_404("deals", deal_id)
        li = get_or_404("line_items", line_id)
        if li["deal_id"] != deal_id:
            abort(404)
        db = get_db()
        if request.form.get("action") == "delete":
            db.execute("DELETE FROM line_items WHERE id=? AND workspace_id=?", (line_id, ws()))
        else:
            line = parse_line(request.form)
            if not line:
                flash("Line not updated. Check the quantity, price, discount and VAT rate.", "error")
                return redirect(url_for("deal", deal_id=deal_id) + "#line-items")
            name, qty, price, discount, rate = line
            db.execute("UPDATE line_items SET name=?, quantity=?, unit_price=?, discount_pct=?, vat_rate=? WHERE id=?",
                       (name, qty, price, discount, rate, line_id))
        recalc_deal_value(deal_id)
        if not scalar("SELECT COUNT(*) FROM line_items WHERE workspace_id=? AND deal_id=?", ws(), deal_id):
            db.execute("UPDATE deals SET value=0 WHERE id=? AND workspace_id=?", (deal_id, ws()))
        db.commit()
        return redirect(url_for("deal", deal_id=deal_id) + "#line-items")

    # --- Products ---------------------------------------------------------------

    @app.route("/products")
    def products():
        show = request.args.get("show", "active")
        items = rows("SELECT p.*, (SELECT COUNT(*) FROM line_items li JOIN deals d ON d.id=li.deal_id"
                     f" WHERE li.product_id=p.id AND d.{OPEN_SQL}) AS in_deals FROM products p"
                     " WHERE p.workspace_id=? AND p.active=? ORDER BY LOWER(p.name)", ws(), 0 if show == "archived" else 1)
        return render_template("products.html", items=items, show=show, billing_periods=BILLING_PERIODS,
                               edit=one("SELECT * FROM products WHERE id=? AND workspace_id=?",
                                        int(request.args["edit"]), ws()) if request.args.get("edit", "").isdigit() else None)

    def product_from_form(f):
        name = f.get("name", "").strip()
        price = ukfmt.parse_amount(f.get("unit_price"))
        rate = f.get("vat_rate", "20")
        billing = f.get("billing") if f.get("billing") in BILLING_PERIODS else "One-off"
        if not name or price is None or not rate.isdigit() or int(rate) not in ukfmt.VAT_RATES:
            return None
        return dict(name=name, sku=f.get("sku", "").strip().upper(), description=f.get("description", "").strip(),
                    unit_price=price, vat_rate=int(rate), billing=billing)

    @app.post("/products")
    def create_product():
        data = product_from_form(request.form)
        if not data:
            flash("Product not added. It needs a name, a price in £ and a VAT rate.", "error")
            return redirect(url_for("products"))
        get_db().insert("products", workspace_id=ws(), **data, active=1, created_at=today().isoformat())
        get_db().commit()
        flash(f"Product added: {data['name']}.", "ok")
        return redirect(url_for("products"))

    @app.post("/products/<int:product_id>")
    def update_product(product_id):
        p = get_or_404("products", product_id)
        db = get_db()
        if request.form.get("action") in ("archive", "restore"):
            db.execute("UPDATE products SET active=? WHERE id=? AND workspace_id=?",
                       (1 if request.form["action"] == "restore" else 0, product_id, ws()))
            db.commit()
            flash(f"{p['name']} {'restored' if request.form['action'] == 'restore' else 'archived'}.", "ok")
            return redirect(url_for("products"))
        data = product_from_form(request.form)
        if not data:
            flash("Product not saved. It needs a name, a price in £ and a VAT rate.", "error")
            return redirect(url_for("products", edit=product_id))
        db.execute("UPDATE products SET name=?, sku=?, description=?, unit_price=?, vat_rate=?, billing=? WHERE id=? AND workspace_id=?",
                   (*data.values(), product_id, ws()))
        db.commit()
        flash("Product saved. Deals already quoted keep their original price.", "ok")
        return redirect(url_for("products"))

    # --- Tasks ------------------------------------------------------------------

    @app.route("/tasks")
    def tasks():
        t = today()
        try:
            month = date.fromisoformat(request.args.get("month", "") + "-01")
        except ValueError:
            month = t.replace(day=1)
        month_end = add_months(month, 1)
        mine = request.args.get("mine") == "1"
        sql = ("SELECT a.*, c.name AS company, d.title AS deal, ct.first_name || ' ' || ct.last_name AS contact"
               " FROM activities a LEFT JOIN companies c ON c.id=a.company_id LEFT JOIN deals d ON d.id=a.deal_id"
               " LEFT JOIN contacts ct ON ct.id=a.contact_id"
               " WHERE a.workspace_id=? AND ((a.due_at >= ? AND a.due_at < ?) OR (a.done=0 AND a.due_at < ?))")
        args = [ws(), month.isoformat(), month_end.isoformat(), t.isoformat()]
        if mine:
            sql += " AND a.owner=?"
            args.append(g.user["name"])
        data = rows(sql + " ORDER BY a.due_at", *args)
        days = defaultdict(list)
        for a in data:
            days[a["due_at"][:10]].append(a)
        overdue = sum(1 for a in data if not a["done"] and a["due_at"][:10] < t.isoformat())
        weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(month.year, month.month)
        return render_template("schedule.html", days=sorted(days.items()), overdue=overdue, weeks=weeks, mine=mine,
                               month=month, prev_month=add_months(month, -1), next_month=month_end,
                               day_counts={k: len(v) for k, v in days.items()}, bank_holidays=ukfmt.BANK_HOLIDAYS)

    @app.post("/activities")
    def create_activity():
        f = request.form
        try:
            due = datetime.fromisoformat(f"{f.get('date')}T{f.get('time') or '09:00'}")
        except ValueError:
            due = None
        if not f.get("subject", "").strip() or not due or f.get("kind") not in ACTIVITY_KINDS:
            flash("Task not created. It needs a type, a subject and a date.", "error")
            return back("tasks")
        get_db().insert("activities", workspace_id=ws(), kind=f["kind"], subject=f["subject"].strip(),
                        owner=chosen_owner(f.get("owner")), due_at=due.isoformat(timespec="minutes"), done=0,
                        **resolve_links(f))
        get_db().commit()
        flash(f"Scheduled for {ukfmt.uk_datetime(due.isoformat())}: {f['subject'].strip()}.", "ok")
        return back("tasks")

    @app.post("/activities/<int:activity_id>/toggle")
    def toggle_activity(activity_id):
        get_or_404("activities", activity_id)
        db = get_db()
        db.execute("UPDATE activities SET done = 1 - done WHERE id=? AND workspace_id=?", (activity_id, ws()))
        db.commit()
        if wants_json():
            done = one("SELECT done FROM activities WHERE id=?", activity_id)
            return jsonify(ok=True, done=bool(done and done[0]))
        return back("tasks")

    # --- Projects ---------------------------------------------------------------

    @app.route("/projects")
    def projects():
        data = rows("SELECT p.*, c.name AS company FROM projects p JOIN companies c ON c.id=p.company_id"
                    " WHERE p.workspace_id=? ORDER BY p.status='Complete', p.due_date", ws())
        return render_template("projects.html", projects=data, statuses=PROJECT_STATUSES)

    @app.post("/projects/<int:project_id>")
    def update_project(project_id):
        get_or_404("projects", project_id)
        f = request.form
        status = f.get("status")
        try:
            progress = max(0, min(100, int(f.get("progress", 0))))
        except ValueError:
            abort(400)
        if status not in PROJECT_STATUSES:
            abort(400)
        if progress == 100:
            status = "Complete"
        db = get_db()
        db.execute("UPDATE projects SET status=?, progress=? WHERE id=? AND workspace_id=?", (status, progress, project_id, ws()))
        db.commit()
        if wants_json():
            return jsonify(ok=True, status=status, progress=progress)
        return back("projects")

