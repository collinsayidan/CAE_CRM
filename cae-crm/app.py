"""CAE CRM - a UK-standard sales CRM built with Flask and SQLite.

Run:  python app.py   (then open http://127.0.0.1:5000)
      or: flask --app app run
"""

import calendar
import json
import os
import secrets
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from flask import (Flask, Response, abort, current_app, flash, jsonify, redirect, render_template,
                   request, session, url_for)

import charts
import ukfmt
from db import (ACTIVITY_KINDS, LAWFUL_BASES, MONTHLY_TARGET, OPEN_STAGES, OWNERS, SOURCES,
                STAGE_PROBABILITY, STAGES, close_db, get_db, init_db, next_invoice_number)
from ukfmt import add_months, fy_quarter, money, vat_amount, vat_quarter, working_days

NAV = [("overview", "Overview", "home"), ("pipeline", "Pipeline", "pipeline"), ("customers", "Customers", "building"),
       ("schedule", "Schedule", "calendar"), ("finance", "Finance", "pound"), ("growth", "Growth", "trend"),
       ("projects", "Projects", "flag")]
# Stages are ordinal, so they share one sequential ramp (defined per theme in style.css).
STAGE_COLOURS = {s: f"var(--stage-{i + 1})" for i, s in enumerate(OPEN_STAGES)}
OPEN_SQL = f"stage IN ({','.join(repr(s) for s in OPEN_STAGES)})"
PROJECT_STATUSES = ["On track", "At risk", "Blocked", "Complete"]
REGIONS = ["London", "South East", "South West", "East of England", "East Midlands", "West Midlands",
           "Yorkshire", "North West", "North East", "Scotland", "Wales", "Northern Ireland"]
UK_TZ = ZoneInfo("Europe/London")


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
    app.add_template_filter(lambda s: s.lower().replace(" ", "-"), "slug")
    app.add_template_filter(days_until, "days_until")

    @app.context_processor
    def inject_globals():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(24)
        t = today()
        hour = datetime.now(UK_TZ).hour
        return dict(
            nav=NAV, csrf_token=session["csrf"], today=t, stage_colours=STAGE_COLOURS,
            pennies=lambda p: money(p, pennies=True),
            greeting="Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening",
            counts=dict(
                pipeline=scalar(f"SELECT COUNT(*) FROM deals WHERE {OPEN_SQL}"),
                schedule=scalar("SELECT COUNT(*) FROM activities WHERE done=0 AND substr(due_at,1,10)=?", t.isoformat()),
                finance=scalar("SELECT COUNT(*) FROM invoices WHERE paid_date IS NULL AND due_date < ?", t.isoformat()),
            ),
            # Choices for the quick-create dialogs available on every page.
            all_companies=company_options, stages=STAGES, owners=OWNERS, sources=SOURCES, kinds=ACTIVITY_KINDS,
            vat_rates=ukfmt.VAT_RATES, regions=REGIONS, lawful_bases=LAWFUL_BASES,
        )

    @app.before_request
    def check_csrf():
        if request.method == "POST":
            token = request.form.get("csrf") or request.headers.get("X-CSRF-Token")
            if token != session.get("csrf"):
                abort(400, "Your session expired. Reload the page and try again.")

    register_routes(app)
    return app


def today():
    return current_app.config["TODAY"] or date.today()


def days_until(value):
    days = (ukfmt.to_date(value) - today()).days
    if days == 0:
        return "today"
    if days == 1:
        return "tomorrow"
    if days == -1:
        return "yesterday"
    return f"in {days} days" if days > 0 else f"{-days} days ago"


def scalar(sql, *args):
    return get_db().execute(sql, args).fetchone()[0] or 0


def company_options():
    return get_db().execute("SELECT id, name FROM companies ORDER BY name").fetchall()


def won_between(start, end):
    return scalar("SELECT SUM(value) FROM deals WHERE stage='Won' AND closed_at >= ? AND closed_at < ?",
                  start.isoformat(), end.isoformat())


def wants_json():
    return request.headers.get("X-Requested-With") == "fetch"


def back(default):
    target = request.form.get("next") or ""
    return redirect(target if target.startswith("/") and not target.startswith("//") else url_for(default))


def register_routes(app):

    # --- Overview -----------------------------------------------------------

    @app.route("/")
    def overview():
        db, t = get_db(), today()
        this_month = t.replace(day=1)
        next_month = add_months(this_month, 1)
        won_this = won_between(this_month, next_month)
        # Compare like-for-like: last month up to the same day of the month.
        last_month = add_months(this_month, -1)
        won_last = won_between(last_month, last_month + timedelta(days=t.day))
        change = round((won_this - won_last) / won_last * 100) if won_last else None

        # The month track: won revenue against target, paced by UK working days.
        days = working_days(this_month, next_month)
        elapsed = sum(1 for d in days if d < t)
        expected = MONTHLY_TARGET * elapsed / len(days)
        left = len(days) - elapsed
        track = dict(
            target=MONTHLY_TARGET, won=won_this, days=days, elapsed=elapsed, left=left,
            won_pct=min(100, won_this / MONTHLY_TARGET * 100), expected_pct=elapsed / len(days) * 100,
            gap=won_this - expected, per_day=max(0, MONTHLY_TARGET - won_this) / left if left else 0,
            month=t.strftime("%B"),
        )

        months = [add_months(this_month, -i) for i in reversed(range(12))]
        by_month = dict(db.execute(
            "SELECT substr(closed_at,1,7), SUM(value) FROM deals WHERE stage='Won' AND closed_at >= ? GROUP BY 1",
            (months[0].isoformat(),)).fetchall())
        series = [{"label": m.strftime("%b"), "full": m.strftime("%B %Y"),
                   "value": by_month.get(m.strftime("%Y-%m"), 0) / 100, "partial": m == this_month} for m in months]

        pipeline_value = scalar(f"SELECT SUM(value) FROM deals WHERE {OPEN_SQL}")
        open_count = scalar(f"SELECT COUNT(*) FROM deals WHERE {OPEN_SQL}")
        forecast = scalar(f"SELECT SUM(value * probability / 100) FROM deals WHERE {OPEN_SQL}")
        year_ago = add_months(this_month, -11).isoformat()
        won_n = scalar("SELECT COUNT(*) FROM deals WHERE stage='Won' AND closed_at >= ?", year_ago)
        lost_n = scalar("SELECT COUNT(*) FROM deals WHERE stage='Lost' AND closed_at >= ?", year_ago)
        win_rate = round(won_n / (won_n + lost_n) * 100) if won_n + lost_n else 0
        created = dict(db.execute(
            "SELECT substr(created_at,1,7), SUM(value) FROM deals WHERE created_at >= ? GROUP BY 1",
            (months[0].isoformat(),)).fetchall())

        closing_soon = db.execute(
            f"SELECT d.*, c.name AS company FROM deals d JOIN companies c ON c.id=d.company_id"
            f" WHERE {OPEN_SQL} AND d.close_date <= ? ORDER BY d.close_date, d.value DESC LIMIT 6",
            ((t + timedelta(days=30)).isoformat(),)).fetchall()
        mix_rows = {r["stage"]: r for r in db.execute(
            f"SELECT stage, SUM(value) AS total, COUNT(*) AS n FROM deals WHERE {OPEN_SQL} GROUP BY stage")}
        mix = [dict(stage=s, total=mix_rows[s]["total"] if s in mix_rows else 0,
                    n=mix_rows[s]["n"] if s in mix_rows else 0) for s in OPEN_STAGES]
        peak = max([m["total"] for m in mix] + [1])

        fy_label, q, q_start, q_end = fy_quarter(t)
        quota = MONTHLY_TARGET * 3
        quota_won = won_between(q_start, q_end)
        quota_pct = quota_won / quota * 100

        # Everything today (done or not), then whatever is still to do after it.
        agenda = db.execute(
            "SELECT a.*, c.name AS company FROM activities a LEFT JOIN companies c ON c.id=a.company_id"
            " WHERE a.due_at >= ? AND (a.done=0 OR substr(a.due_at,1,10)=?) ORDER BY a.due_at LIMIT 6",
            (t.isoformat(), t.isoformat())).fetchall()

        return render_template(
            "overview.html", track=track, change=change, won_this=won_this,
            pipeline_value=pipeline_value, open_count=open_count, forecast=forecast, win_rate=win_rate,
            won_n=won_n, closed_n=won_n + lost_n,
            spark_won=charts.sparkline([s["value"] for s in series]),
            spark_created=charts.sparkline([created.get(m.strftime("%Y-%m"), 0) for m in months]),
            series_json=json.dumps({"series": series, "target": MONTHLY_TARGET / 100}),
            closing_soon=closing_soon, soon_cutoff=(t + timedelta(days=7)).isoformat(), mix=mix, peak=peak,
            quota=quota, quota_won=quota_won, quota_pct=quota_pct,
            quota_ring=charts.ring(quota_pct, label=f"{quota_pct:.0f}% of quarterly quota"),
            fy_label=fy_label, fy_q=q, q_end=q_end - timedelta(days=1),
            agenda=agenda)

    # --- Search (command palette) -------------------------------------------

    @app.route("/api/search")
    def search():
        q = request.args.get("q", "").strip()
        if len(q) < 2:
            return jsonify([])
        like, db = f"%{q}%", get_db()
        results = [dict(kind="Customer", title=r["name"], detail=f"{r['city']}, {r['postcode']}",
                        url=url_for("company", company_id=r["id"]))
                   for r in db.execute("SELECT * FROM companies WHERE name LIKE ? OR city LIKE ? OR postcode LIKE ?"
                                       " ORDER BY name LIMIT 5", (like, like, like))]
        results += [dict(kind="Deal", title=r["title"], detail=f"{r['company']}, {money(r['value'])}, {r['stage']}",
                         url=url_for("company", company_id=r["company_id"]))
                    for r in db.execute("SELECT d.*, c.name AS company FROM deals d JOIN companies c ON c.id=d.company_id"
                                        f" WHERE {OPEN_SQL} AND (d.title LIKE ? OR c.name LIKE ?)"
                                        " ORDER BY d.value DESC LIMIT 5", (like, like))]
        results += [dict(kind="Contact", title=f"{r['first_name']} {r['last_name']}", detail=f"{r['role']}, {r['company']}",
                         url=url_for("company", company_id=r["company_id"]))
                    for r in db.execute("SELECT ct.*, c.name AS company FROM contacts ct JOIN companies c ON c.id=ct.company_id"
                                        " WHERE ct.first_name || ' ' || ct.last_name LIKE ? OR ct.email LIKE ? LIMIT 5",
                                        (like, like))]
        return jsonify(results)

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
        return render_template("pipeline.html", columns=columns, owner=owner)

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
            flash("Deal not added. It needs a title, a customer, a value in £ and an expected close date.", "error")
            return back("pipeline")
        get_db().execute(
            "INSERT INTO deals (company_id, title, value, stage, probability, owner, source, close_date, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (int(f["company_id"]), f["title"].strip(), value, stage, STAGE_PROBABILITY[stage],
             f.get("owner") if f.get("owner") in OWNERS else OWNERS[0],
             f.get("source") if f.get("source") in SOURCES else SOURCES[0],
             close_date.isoformat(), today().isoformat()))
        get_db().commit()
        flash(f"Deal added: {f['title'].strip()}, {money(value)}.", "ok")
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
            message = f"Won: {deal['title']}, {money(deal['value'])}. Delivery project created."
        elif stage == "Lost":
            message = f"Marked as lost: {deal['title']}."
        else:
            message = f"Moved to {stage}: {deal['title']}."
        db.commit()
        if wants_json():
            return jsonify(ok=True, stage=stage, probability=STAGE_PROBABILITY[stage], message=message)
        flash(message, "ok")
        return back("pipeline")

    # --- Customers ----------------------------------------------------------

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

    @app.route("/customers")
    def customers():
        q = request.args.get("q", "").strip()
        return render_template("customers.html", companies=company_list(q), q=q)

    def validate_company(f):
        errors, data = {}, {}
        data["name"] = f.get("name", "").strip()
        if not data["name"]:
            errors["name"] = "Enter the company name."
        data["postcode"] = ukfmt.normalise_postcode(f.get("postcode"))
        if not data["postcode"]:
            errors["postcode"] = "Enter a valid UK postcode, like EH2 2AN."
        data["company_no"] = ukfmt.normalise_company_no(f.get("company_no"))
        if data["company_no"] is None:
            errors["company_no"] = "Companies House numbers have 8 characters, like 08451236 or SC512345."
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
            return render_template("customers.html", companies=company_list(), q="",
                                   customer_form=request.form, customer_errors=errors), 422
        db = get_db()
        cur = db.execute(
            "INSERT INTO companies (name, company_no, vat_no, industry, address, city, postcode, region, created_at)"
            " VALUES (:name,:company_no,:vat_no,:industry,:address,:city,:postcode,:region,:created)",
            data | {"created": today().isoformat()})
        db.commit()
        flash(f"Customer added: {data['name']}.", "ok")
        return redirect(url_for("company", company_id=cur.lastrowid))

    @app.route("/customers/<int:company_id>")
    def company(company_id, contact_errors=None, contact_form=None):
        db = get_db()
        c = db.execute("SELECT * FROM companies WHERE id=?", (company_id,)).fetchone() or abort(404)
        stats = dict(
            lifetime=scalar("SELECT SUM(value) FROM deals WHERE company_id=? AND stage='Won'", company_id),
            pipeline=scalar(f"SELECT SUM(value) FROM deals WHERE company_id=? AND {OPEN_SQL}", company_id),
            outstanding=scalar("SELECT SUM(net + vat) FROM invoices WHERE company_id=? AND paid_date IS NULL", company_id),
        )
        return render_template(
            "company.html", c=c, stats=stats,
            contacts=db.execute("SELECT * FROM contacts WHERE company_id=? ORDER BY last_name", (company_id,)).fetchall(),
            deals=db.execute("SELECT * FROM deals WHERE company_id=? ORDER BY close_date DESC", (company_id,)).fetchall(),
            invoices=db.execute("SELECT * FROM invoices WHERE company_id=? ORDER BY issue_date DESC", (company_id,)).fetchall(),
            activities=db.execute("SELECT * FROM activities WHERE company_id=? ORDER BY due_at DESC LIMIT 12",
                                  (company_id,)).fetchall(),
            errors=contact_errors or {}, form=contact_form or {})

    @app.post("/customers/<int:company_id>/contacts")
    def create_contact(company_id):
        f, errors = request.form, {}
        first, last = f.get("first_name", "").strip(), f.get("last_name", "").strip()
        if not first or not last:
            errors["name"] = "Enter a first and last name."
        email = f.get("email", "").strip().lower()
        if email and ("@" not in email or "." not in email.split("@")[-1]):
            errors["email"] = "Enter a valid email address."
        phone = ukfmt.normalise_phone(f.get("phone"))
        if phone is None:
            errors["phone"] = "Enter a UK number, like 0131 496 0000 or +44 7700 900123."
        basis = f.get("lawful_basis")
        if basis not in LAWFUL_BASES:
            errors["lawful_basis"] = "Choose the UK GDPR lawful basis for holding this person's data."
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
        flash(f"Contact added: {first} {last}.", "ok")
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
        flash("Contact erased. Their personal data has been deleted.", "ok")
        return redirect(url_for("company", company_id=row["company_id"]))

    # --- Schedule -----------------------------------------------------------

    @app.route("/schedule")
    def schedule():
        t = today()
        try:
            month = date.fromisoformat(request.args.get("month", "") + "-01")
        except ValueError:
            month = t.replace(day=1)
        month_end = add_months(month, 1)
        rows = get_db().execute(
            "SELECT a.*, c.name AS company, d.title AS deal FROM activities a"
            " LEFT JOIN companies c ON c.id=a.company_id LEFT JOIN deals d ON d.id=a.deal_id"
            " WHERE (a.due_at >= ? AND a.due_at < ?) OR (a.done=0 AND a.due_at < ?) ORDER BY a.due_at",
            (month.isoformat(), month_end.isoformat(), t.isoformat())).fetchall()
        days = defaultdict(list)
        for a in rows:
            days[a["due_at"][:10]].append(a)
        overdue = sum(1 for a in rows if not a["done"] and a["due_at"][:10] < t.isoformat())
        # Calendar grid, weeks starting Monday as in the UK.
        weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(month.year, month.month)
        return render_template("schedule.html", days=sorted(days.items()), overdue=overdue, weeks=weeks,
                               month=month, prev_month=add_months(month, -1), next_month=month_end,
                               day_counts={k: len(v) for k, v in days.items()},
                               bank_holidays=ukfmt.BANK_HOLIDAYS)

    @app.post("/activities")
    def create_activity():
        f = request.form
        try:
            due = datetime.fromisoformat(f"{f.get('date')}T{f.get('time') or '09:00'}")
        except ValueError:
            due = None
        if not f.get("subject", "").strip() or not due or f.get("kind") not in ACTIVITY_KINDS:
            flash("Activity not scheduled. It needs a type, a subject and a date.", "error")
            return back("schedule")
        company_id = int(f["company_id"]) if f.get("company_id", "").isdigit() else None
        get_db().execute(
            "INSERT INTO activities (company_id, kind, subject, owner, due_at) VALUES (?,?,?,?,?)",
            (company_id, f["kind"], f["subject"].strip(), f.get("owner") if f.get("owner") in OWNERS else OWNERS[0],
             due.isoformat(timespec="minutes")))
        get_db().commit()
        flash(f"Scheduled for {ukfmt.uk_datetime(due.isoformat())}: {f['subject'].strip()}.", "ok")
        return back("schedule")

    @app.post("/activities/<int:activity_id>/toggle")
    def toggle_activity(activity_id):
        db = get_db()
        db.execute("UPDATE activities SET done = 1 - done WHERE id=?", (activity_id,))
        db.commit()
        if wants_json():
            done = db.execute("SELECT done FROM activities WHERE id=?", (activity_id,)).fetchone()
            return jsonify(ok=True, done=bool(done and done[0]))
        return back("schedule")

    # --- Finance ------------------------------------------------------------

    @app.route("/finance")
    def finance():
        db, t = get_db(), today()
        invoices = db.execute(
            "SELECT i.*, c.name AS company FROM invoices i JOIN companies c ON c.id=i.company_id"
            " ORDER BY i.issue_date DESC, i.id DESC").fetchall()

        def state(i):
            if i["paid_date"]:
                return "Paid"
            return "Overdue" if i["due_date"] < t.isoformat() else "Due"

        rows = [(i, state(i)) for i in invoices]
        fy_label, _, _, _ = fy_quarter(t)
        fy_start = date(t.year if t.month >= 4 else t.year - 1, 4, 1)
        vq_start, vq_end = vat_quarter(t)
        # Aged debt, the way UK credit control reports it.
        aging = {"Not yet due": 0, "1–30 days late": 0, "31–60 days late": 0, "Over 60 days late": 0}
        for i in invoices:
            if i["paid_date"]:
                continue
            late = (t - date.fromisoformat(i["due_date"])).days
            key = ("Not yet due" if late <= 0 else "1–30 days late" if late <= 30
                   else "31–60 days late" if late <= 60 else "Over 60 days late")
            aging[key] += i["net"] + i["vat"]
        totals = {
            "outstanding": sum(aging.values()),
            "overdue": sum(v for k, v in aging.items() if k != "Not yet due"),
            "overdue_n": sum(1 for _, s in rows if s == "Overdue"),
            "paid_fy": sum(i["net"] + i["vat"] for i in invoices if i["paid_date"] and i["paid_date"] >= fy_start.isoformat()),
            "vat_quarter": sum(i["vat"] for i in invoices if vq_start.isoformat() <= i["issue_date"] < vq_end.isoformat()),
        }
        return render_template("finance.html", rows=rows, totals=totals, aging=aging, fy_label=fy_label,
                               vq_start=vq_start, vq_end=vq_end - timedelta(days=1))

    @app.post("/invoices")
    def create_invoice():
        f = request.form
        net = ukfmt.parse_money(f.get("net"))
        rate = int(f.get("vat_rate", 20)) if f.get("vat_rate", "20").isdigit() else -1
        if not (net and rate in ukfmt.VAT_RATES and f.get("company_id", "").isdigit() and f.get("description", "").strip()):
            flash("Invoice not raised. Choose a customer, describe the work and enter a net amount in £.", "error")
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
        flash(f"Invoice {number} raised for {money(net + vat_amount(net, rate), pennies=True)} including VAT.", "ok")
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
        return render_template("projects.html", projects=rows, statuses=PROJECT_STATUSES)

    @app.post("/projects/<int:project_id>")
    def update_project(project_id):
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
        db.execute("UPDATE projects SET status=?, progress=? WHERE id=?", (status, progress, project_id))
        db.commit()
        if wants_json():
            return jsonify(ok=True, status=status, progress=progress)
        return back("projects")


if __name__ == "__main__":
    create_app().run(debug=os.environ.get("FLASK_DEBUG") == "1")
