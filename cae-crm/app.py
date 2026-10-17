"""CAE CRM - a UK-standard sales CRM built with Flask and SQLite.

Run:  python app.py   (then open http://127.0.0.1:5000)
      or: flask --app app run
"""

import json
import os
import secrets
from collections import defaultdict
from datetime import date, datetime, timedelta

from flask import (Flask, Response, abort, current_app, flash, redirect, render_template,
                   request, session, url_for)

import charts
import ukfmt
from db import (ACTIVITY_KINDS, LAWFUL_BASES, MONTHLY_TARGET, OPEN_STAGES, OWNERS, SOURCES,
                STAGE_PROBABILITY, STAGES, close_db, get_db, init_db, next_invoice_number)
from ukfmt import add_months, fy_quarter, money, vat_amount, vat_quarter

NAV = [("overview", "Overview"), ("pipeline", "Pipeline"), ("customers", "Customers"),
       ("schedule", "Schedule"), ("finance", "Finance"), ("growth", "Growth"), ("projects", "Projects")]
STAGE_COLOURS = {"Lead": "#d8cfbf", "Qualified": "#d9b44a", "Proposal": "#2f5d50",
                 "Negotiation": "#c4522a", "Closing": "var(--stage-closing)"}
OPEN_SQL = f"stage IN ({','.join(repr(s) for s in OPEN_STAGES)})"


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.update(
        SECRET_KEY=os.environ.get("CAE_SECRET_KEY") or secrets.token_hex(32),
        DATABASE=os.path.join(app.instance_path, "cae_crm.sqlite3"),
        TODAY=None,  # tests pin the date; otherwise the real date is used
    )
    app.config.update(config or {})
    os.makedirs(app.instance_path, exist_ok=True)
    if not os.path.exists(app.config["DATABASE"]):
        init_db(app.config["DATABASE"], app.config["TODAY"] or date.today())
    app.teardown_appcontext(close_db)

    for name in ("money", "money_short", "uk_date", "uk_date_short", "uk_datetime"):
        app.add_template_filter(getattr(ukfmt, name), name)
    app.add_template_filter(lambda n: "".join(p[0] for p in n.split()[:2]).upper(), "initials")
    app.add_template_filter(lambda n: sum(map(ord, n)) * 37 % 360, "hue")

    @app.context_processor
    def inject_globals():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(24)
        return dict(nav=NAV, csrf_token=session["csrf"], today=today(), stage_colours=STAGE_COLOURS,
                    pennies=lambda p: money(p, pennies=True))

    @app.before_request
    def check_csrf():
        if request.method == "POST" and request.form.get("csrf") != session.get("csrf"):
            abort(400, "Your session expired - please reload the page and try again.")

    register_routes(app)
    return app


def today():
    return current_app.config["TODAY"] or date.today()


def scalar(sql, *args):
    return get_db().execute(sql, args).fetchone()[0] or 0


def company_options():
    return get_db().execute("SELECT id, name FROM companies ORDER BY name").fetchall()


def won_between(start, end):
    return scalar("SELECT SUM(value) FROM deals WHERE stage='Won' AND closed_at >= ? AND closed_at < ?",
                  start.isoformat(), end.isoformat())


def back(default):
    target = request.form.get("next") or ""
    return redirect(target if target.startswith("/") and not target.startswith("//") else url_for(default))


def register_routes(app):

    # --- Overview -----------------------------------------------------------

    @app.route("/")
    def overview():
        db, t = get_db(), today()
        span = 6 if request.args.get("span") == "6m" else 12
        this_month = t.replace(day=1)
        won_this = won_between(this_month, add_months(this_month, 1))
        # Compare like-for-like: last month up to the same day of the month.
        last_month = add_months(this_month, -1)
        won_last = won_between(last_month, last_month + timedelta(days=t.day))
        change = round((won_this - won_last) / won_last * 100) if won_last else None

        pipeline_value = scalar(f"SELECT SUM(value) FROM deals WHERE {OPEN_SQL}")
        open_count = scalar(f"SELECT COUNT(*) FROM deals WHERE {OPEN_SQL}")
        won_n = scalar("SELECT COUNT(*) FROM deals WHERE stage='Won'")
        lost_n = scalar("SELECT COUNT(*) FROM deals WHERE stage='Lost'")
        win_rate = round(won_n / (won_n + lost_n) * 100) if won_n + lost_n else 0

        months = [add_months(this_month, -i) for i in reversed(range(span))]
        by_month = dict(db.execute(
            "SELECT substr(closed_at,1,7), SUM(value) FROM deals WHERE stage='Won' AND closed_at >= ? GROUP BY 1",
            (months[0].isoformat(),)).fetchall())
        series = [(m.strftime("%b"), by_month.get(m.strftime("%Y-%m"), 0)) for m in months]
        # The current month is still in progress, so it is not judged against target.
        at_target = sum(1 for _, v in series[:-1] if v >= MONTHLY_TARGET)

        hot = db.execute(
            f"SELECT d.*, c.name AS company FROM deals d JOIN companies c ON c.id=d.company_id"
            f" WHERE {OPEN_SQL} ORDER BY d.value * d.probability DESC LIMIT 6").fetchall()
        mix_rows = {r["stage"]: r for r in db.execute(
            f"SELECT stage, SUM(value) AS total, COUNT(*) AS n FROM deals WHERE {OPEN_SQL} GROUP BY stage")}
        mix = [(s, mix_rows[s]["total"] if s in mix_rows else 0, mix_rows[s]["n"] if s in mix_rows else 0)
               for s in OPEN_STAGES]

        fy_label, q, q_start, q_end = fy_quarter(t)
        quota = MONTHLY_TARGET * 3
        quota_won = won_between(q_start, q_end)
        quota_pct = quota_won / quota * 100

        upcoming = db.execute(
            "SELECT a.*, c.name AS company FROM activities a LEFT JOIN companies c ON c.id=a.company_id"
            " WHERE a.done=0 AND a.due_at >= ? ORDER BY a.due_at LIMIT 5", (t.isoformat(),)).fetchall()

        return render_template(
            "overview.html", won_this=won_this, change=change, pipeline_value=pipeline_value,
            open_count=open_count, win_rate=win_rate, span=span, series=series,
            revenue_total=sum(v for _, v in series), at_target=at_target, target=MONTHLY_TARGET,
            chart=charts.revenue_chart(series, MONTHLY_TARGET), hot=hot, mix=mix,
            quota_pct=quota_pct, quota=quota, quota_won=quota_won, gauge=charts.gauge(quota_pct),
            fy_label=fy_label, fy_q=q, q_end=q_end - timedelta(days=1), upcoming=upcoming)

    # --- Pipeline -----------------------------------------------------------

    @app.route("/pipeline")
    def pipeline():
        owner = request.args.get("owner", "")
        sql = (f"SELECT d.*, c.name AS company FROM deals d JOIN companies c ON c.id=d.company_id"
               f" WHERE {OPEN_SQL}")
        args = []
        if owner in OWNERS:
            sql += " AND d.owner=?"
            args.append(owner)
        columns = defaultdict(list)
        for deal in get_db().execute(sql + " ORDER BY d.close_date", args):
            columns[deal["stage"]].append(deal)
        return render_template("pipeline.html", stages=STAGES, columns=columns, owners=OWNERS,
                               owner=owner, sources=SOURCES, companies=company_options())

    @app.post("/deals")
    def create_deal():
        f = request.form
        value = ukfmt.parse_money(f.get("value"))
        stage = f.get("stage") if f.get("stage") in OPEN_STAGES else "Lead"
        try:
            close_date = date.fromisoformat(f.get("close_date", ""))
        except ValueError:
            close_date = None
        if not (f.get("title", "").strip() and value and close_date and f.get("company_id", "").isdigit()):
            flash("Please give the deal a title, company, value in £ and an expected close date.", "error")
            return back("pipeline")
        get_db().execute(
            "INSERT INTO deals (company_id, title, value, stage, probability, owner, source, close_date, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (int(f["company_id"]), f["title"].strip(), value, stage, STAGE_PROBABILITY[stage],
             f.get("owner") if f.get("owner") in OWNERS else OWNERS[0],
             f.get("source") if f.get("source") in SOURCES else SOURCES[0],
             close_date.isoformat(), today().isoformat()))
        get_db().commit()
        flash(f"Deal “{f['title'].strip()}” added at {money(value)}.", "ok")
        return back("pipeline")

    @app.post("/deals/<int:deal_id>/stage")
    def move_deal(deal_id):
        db = get_db()
        deal = db.execute("SELECT * FROM deals WHERE id=?", (deal_id,)).fetchone() or abort(404)
        stage = request.form.get("stage")
        if stage not in STAGE_PROBABILITY:
            abort(400)
        closed = today().isoformat() if stage in ("Won", "Lost") else None
        db.execute("UPDATE deals SET stage=?, probability=?, closed_at=? WHERE id=?",
                   (stage, STAGE_PROBABILITY[stage], closed, deal_id))
        if stage == "Won":
            db.execute(
                "INSERT INTO projects (company_id, deal_id, name, owner, status, progress, due_date)"
                " VALUES (?,?,?,?,'On track',0,?)",
                (deal["company_id"], deal_id, f"Deliver: {deal['title']}", deal["owner"],
                 (today() + timedelta(days=60)).isoformat()))
            flash(f"🎉 “{deal['title']}” won – {money(deal['value'])}. A delivery project has been created.", "ok")
        else:
            flash(f"“{deal['title']}” moved to {stage}.", "ok")
        db.commit()
        return back("pipeline")

    # --- Customers ----------------------------------------------------------

    @app.route("/customers")
    def customers():
        q = request.args.get("q", "").strip()
        return render_template("customers.html", companies=company_list(q), q=q, form={}, errors={})

    def company_list(q=""):
        sql = (f"SELECT c.*,"
               f" (SELECT SUM(value) FROM deals WHERE company_id=c.id AND {OPEN_SQL}) AS pipeline,"
               f" (SELECT SUM(value) FROM deals WHERE company_id=c.id AND stage='Won') AS lifetime,"
               f" (SELECT COUNT(*) FROM contacts WHERE company_id=c.id) AS contacts"
               f" FROM companies c")
        args = []
        if q:
            sql += " WHERE c.name LIKE ? OR c.city LIKE ? OR c.postcode LIKE ? OR c.industry LIKE ?"
            args = [f"%{q}%"] * 4
        return get_db().execute(sql + " ORDER BY lifetime DESC", args).fetchall()

    def validate_company(f):
        errors, data = {}, {}
        data["name"] = f.get("name", "").strip()
        if not data["name"]:
            errors["name"] = "Company name is required."
        data["postcode"] = ukfmt.normalise_postcode(f.get("postcode"))
        if not data["postcode"]:
            errors["postcode"] = "Enter a valid UK postcode, e.g. EH2 2AN."
        data["company_no"] = ukfmt.normalise_company_no(f.get("company_no"))
        if data["company_no"] is None:
            errors["company_no"] = "Companies House numbers are 8 characters, e.g. 08451236 or SC512345."
        data["vat_no"] = ukfmt.normalise_vat(f.get("vat_no"))
        if data["vat_no"] is None:
            errors["vat_no"] = "UK VAT numbers look like GB123456789."
        for key in ("industry", "address", "city", "region"):
            data[key] = f.get(key, "").strip()
        return data, errors

    @app.post("/customers")
    def create_company():
        data, errors = validate_company(request.form)
        if errors:
            return render_template("customers.html", companies=company_list(), q="", form=request.form,
                                   errors=errors, open_form=True), 422
        db = get_db()
        cur = db.execute(
            "INSERT INTO companies (name, company_no, vat_no, industry, address, city, postcode, region, created_at)"
            " VALUES (:name,:company_no,:vat_no,:industry,:address,:city,:postcode,:region,:created)",
            data | {"created": today().isoformat()})
        db.commit()
        flash(f"{data['name']} added.", "ok")
        return redirect(url_for("company", company_id=cur.lastrowid))

    @app.route("/customers/<int:company_id>")
    def company(company_id, contact_errors=None, contact_form=None):
        db = get_db()
        c = db.execute("SELECT * FROM companies WHERE id=?", (company_id,)).fetchone() or abort(404)
        return render_template(
            "company.html", c=c,
            contacts=db.execute("SELECT * FROM contacts WHERE company_id=? ORDER BY last_name", (company_id,)).fetchall(),
            deals=db.execute("SELECT * FROM deals WHERE company_id=? ORDER BY close_date DESC", (company_id,)).fetchall(),
            invoices=db.execute("SELECT * FROM invoices WHERE company_id=? ORDER BY issue_date DESC", (company_id,)).fetchall(),
            activities=db.execute("SELECT * FROM activities WHERE company_id=? ORDER BY due_at DESC LIMIT 10",
                                  (company_id,)).fetchall(),
            lawful_bases=LAWFUL_BASES, errors=contact_errors or {}, form=contact_form or {})

    @app.post("/customers/<int:company_id>/contacts")
    def create_contact(company_id):
        f, errors = request.form, {}
        first, last = f.get("first_name", "").strip(), f.get("last_name", "").strip()
        if not first or not last:
            errors["name"] = "First and last name are required."
        email = f.get("email", "").strip().lower()
        if email and ("@" not in email or "." not in email.split("@")[-1]):
            errors["email"] = "Enter a valid email address."
        phone = ukfmt.normalise_phone(f.get("phone"))
        if phone is None:
            errors["phone"] = "Enter a UK number, e.g. 0131 496 0000 or +44 7700 900123."
        basis = f.get("lawful_basis")
        if basis not in LAWFUL_BASES:
            errors["lawful_basis"] = "Record the UK GDPR lawful basis for processing."
        # PECR: electronic marketing needs explicit opt-in, recorded separately from the lawful basis.
        consent = f.get("marketing_consent") == "on"
        if errors:
            return company(company_id, contact_errors=errors, contact_form=f), 422
        db = get_db()
        db.execute(
            "INSERT INTO contacts (company_id, first_name, last_name, role, email, phone, lawful_basis,"
            " marketing_consent, consent_date, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (company_id, first, last, f.get("role", "").strip(), email, phone, basis, int(consent),
             today().isoformat() if consent else None, today().isoformat()))
        db.commit()
        flash(f"{first} {last} added.", "ok")
        return redirect(url_for("company", company_id=company_id))

    @app.route("/contacts/<int:contact_id>/export")
    def export_contact(contact_id):
        """Subject access request: everything held about one person, as JSON."""
        db = get_db()
        row = db.execute("SELECT ct.*, c.name AS company FROM contacts ct JOIN companies c ON c.id=ct.company_id"
                         " WHERE ct.id=?", (contact_id,)).fetchone() or abort(404)
        payload = {"exported_at": datetime.now().isoformat(timespec="seconds"), "controller": "CAE CRM",
                   "data_subject": dict(row)}
        return Response(json.dumps(payload, indent=2), mimetype="application/json",
                        headers={"Content-Disposition": f"attachment; filename=sar-contact-{contact_id}.json"})

    @app.post("/contacts/<int:contact_id>/erase")
    def erase_contact(contact_id):
        """Right to erasure (UK GDPR Art. 17)."""
        db = get_db()
        row = db.execute("SELECT * FROM contacts WHERE id=?", (contact_id,)).fetchone() or abort(404)
        db.execute("DELETE FROM contacts WHERE id=?", (contact_id,))
        db.commit()
        flash("Contact's personal data has been erased.", "ok")
        return redirect(url_for("company", company_id=row["company_id"]))

    # --- Schedule -----------------------------------------------------------

    @app.route("/schedule")
    def schedule():
        t = today()
        rows = get_db().execute(
            "SELECT a.*, c.name AS company, d.title AS deal FROM activities a"
            " LEFT JOIN companies c ON c.id=a.company_id LEFT JOIN deals d ON d.id=a.deal_id"
            " WHERE a.due_at >= ? OR a.done=0 ORDER BY a.due_at", ((t - timedelta(days=7)).isoformat(),)).fetchall()
        days = defaultdict(list)
        for a in rows:
            days[a["due_at"][:10]].append(a)
        overdue = sum(1 for a in rows if not a["done"] and a["due_at"][:10] < t.isoformat())
        return render_template("schedule.html", days=sorted(days.items()), overdue=overdue,
                               kinds=ACTIVITY_KINDS, owners=OWNERS, companies=company_options())

    @app.post("/activities")
    def create_activity():
        f = request.form
        try:
            due = datetime.fromisoformat(f"{f.get('date')}T{f.get('time') or '09:00'}")
        except ValueError:
            due = None
        if not f.get("subject", "").strip() or not due or f.get("kind") not in ACTIVITY_KINDS:
            flash("Please give the activity a type, subject and date.", "error")
            return back("schedule")
        company_id = int(f["company_id"]) if f.get("company_id", "").isdigit() else None
        get_db().execute(
            "INSERT INTO activities (company_id, kind, subject, owner, due_at) VALUES (?,?,?,?,?)",
            (company_id, f["kind"], f["subject"].strip(), f.get("owner") if f.get("owner") in OWNERS else OWNERS[0],
             due.isoformat(timespec="minutes")))
        get_db().commit()
        flash("Activity scheduled.", "ok")
        return back("schedule")

    @app.post("/activities/<int:activity_id>/toggle")
    def toggle_activity(activity_id):
        db = get_db()
        db.execute("UPDATE activities SET done = 1 - done WHERE id=?", (activity_id,))
        db.commit()
        return back("schedule")

    # --- Finance ------------------------------------------------------------

    @app.route("/finance")
    def finance():
        db, t = get_db(), today()
        status = request.args.get("status", "")
        invoices = db.execute(
            "SELECT i.*, c.name AS company FROM invoices i JOIN companies c ON c.id=i.company_id"
            " ORDER BY i.issue_date DESC, i.id DESC").fetchall()

        def state(i):
            if i["paid_date"]:
                return "Paid"
            return "Overdue" if i["due_date"] < t.isoformat() else "Due"

        rows = [(i, state(i)) for i in invoices]
        if status in ("Paid", "Due", "Overdue"):
            rows = [r for r in rows if r[1] == status]
        fy_label, _, _, _ = fy_quarter(t)
        fy_start = date(t.year if t.month >= 4 else t.year - 1, 4, 1)
        vq_start, vq_end = vat_quarter(t)
        totals = {
            "outstanding": sum(i["net"] + i["vat"] for i in invoices if not i["paid_date"]),
            "overdue": sum(i["net"] + i["vat"] for i in invoices if state(i) == "Overdue"),
            "overdue_n": sum(1 for i in invoices if state(i) == "Overdue"),
            "paid_fy": sum(i["net"] + i["vat"] for i in invoices if i["paid_date"] and i["paid_date"] >= fy_start.isoformat()),
            "vat_quarter": sum(i["vat"] for i in invoices if vq_start.isoformat() <= i["issue_date"] < vq_end.isoformat()),
        }
        return render_template("finance.html", rows=rows, totals=totals, status=status, fy_label=fy_label,
                               vq_start=vq_start, vq_end=vq_end - timedelta(days=1), vat_rates=ukfmt.VAT_RATES,
                               companies=company_options())

    @app.post("/invoices")
    def create_invoice():
        f = request.form
        net = ukfmt.parse_money(f.get("net"))
        rate = int(f.get("vat_rate", 20)) if f.get("vat_rate", "20").isdigit() else -1
        if not (net and rate in ukfmt.VAT_RATES and f.get("company_id", "").isdigit() and f.get("description", "").strip()):
            flash("Please choose a customer, describe the work and enter a net amount in £.", "error")
            return back("finance")
        db = get_db()
        issue = today()
        number = next_invoice_number(db)
        db.execute(
            "INSERT INTO invoices (number, company_id, description, net, vat_rate, vat, issue_date, due_date)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (number, int(f["company_id"]), f["description"].strip(), net, rate, vat_amount(net, rate),
             issue.isoformat(), (issue + timedelta(days=30)).isoformat()))
        db.commit()
        flash(f"Invoice {number} raised for {money(net + vat_amount(net, rate), pennies=True)} inc. VAT.", "ok")
        return back("finance")

    @app.route("/invoices/<int:invoice_id>")
    def invoice(invoice_id):
        i = get_db().execute(
            "SELECT i.*, c.name AS company, c.address, c.city, c.postcode, c.vat_no AS customer_vat"
            " FROM invoices i JOIN companies c ON c.id=i.company_id WHERE i.id=?", (invoice_id,)).fetchone() or abort(404)
        return render_template("invoice.html", i=i)

    @app.post("/invoices/<int:invoice_id>/paid")
    def mark_paid(invoice_id):
        db = get_db()
        db.execute("UPDATE invoices SET paid_date=? WHERE id=? AND paid_date IS NULL", (today().isoformat(), invoice_id))
        db.commit()
        flash("Invoice marked as paid.", "ok")
        return back("finance")

    # --- Growth -------------------------------------------------------------

    @app.route("/growth")
    def growth():
        db = get_db()

        def breakdown(column):
            rows = db.execute(
                f"SELECT {column} AS k,"
                f" SUM(stage='Won') AS won_n, SUM(stage='Lost') AS lost_n,"
                f" SUM(CASE WHEN stage='Won' THEN value END) AS won_value,"
                f" SUM(CASE WHEN {OPEN_SQL} THEN value END) AS pipeline"
                f" FROM deals GROUP BY {column} ORDER BY won_value DESC").fetchall()
            peak = max([r["won_value"] or 0 for r in rows] + [1])
            return [dict(r) | {"rate": round(r["won_n"] / (r["won_n"] + r["lost_n"]) * 100) if r["won_n"] + r["lost_n"] else 0,
                               "share": (r["won_value"] or 0) / peak * 100} for r in rows]

        avg_deal = scalar("SELECT AVG(value) FROM deals WHERE stage='Won'")
        cycle = scalar("SELECT AVG(julianday(closed_at) - julianday(created_at)) FROM deals WHERE stage='Won'")
        new_customers = scalar("SELECT COUNT(*) FROM companies WHERE created_at >= ?",
                               (today() - timedelta(days=90)).isoformat())
        return render_template("growth.html", by_source=breakdown("source"), by_owner=breakdown("owner"),
                               avg_deal=avg_deal, cycle=round(cycle), new_customers=new_customers)

    # --- Projects -----------------------------------------------------------

    @app.route("/projects")
    def projects():
        rows = get_db().execute(
            "SELECT p.*, c.name AS company FROM projects p JOIN companies c ON c.id=p.company_id"
            " ORDER BY p.status='Complete', p.due_date").fetchall()
        return render_template("projects.html", projects=rows,
                               statuses=["On track", "At risk", "Blocked", "Complete"])

    @app.post("/projects/<int:project_id>")
    def update_project(project_id):
        f = request.form
        status = f.get("status")
        try:
            progress = max(0, min(100, int(f.get("progress", 0))))
        except ValueError:
            abort(400)
        if status not in ("On track", "At risk", "Blocked", "Complete"):
            abort(400)
        if progress == 100:
            status = "Complete"
        db = get_db()
        db.execute("UPDATE projects SET status=?, progress=? WHERE id=?", (status, progress, project_id))
        db.commit()
        return back("projects")


if __name__ == "__main__":
    create_app().run(debug=os.environ.get("FLASK_DEBUG") == "1")
