"""Landing page, Overview dashboard, global search and Reports."""

import json
from datetime import timedelta

from flask import g, jsonify, redirect, render_template, request, url_for

import charts
import ukfmt
from core import OPEN_SQL, company_options, contact_options, owner_names, plain, rows, scalar, sla_state, today, workspace, ws
from db import (ACTIVITY_KINDS, BILLING_PERIODS, LAWFUL_BASES, LIFECYCLE_STAGES, OPEN_STAGES, SOURCES, STAGES,
                TICKET_CATEGORIES, TICKET_PRIORITIES, TICKET_SOURCES, get_db)
from ukfmt import add_months, fy_quarter, money, working_days

# Stages are ordinal, so they share one sequential ramp (defined per theme in style.css).
STAGE_COLOURS = {s: f"var(--stage-{i + 1})" for i, s in enumerate(OPEN_STAGES)}
REGIONS = ["London", "South East", "South West", "East of England", "East Midlands", "West Midlands",
           "Yorkshire", "North West", "North East", "Scotland", "Wales", "Northern Ireland"]


def quick_create_choices():
    """Choices for the quick-create dialogs, which are on every page."""
    w = workspace()
    vat_rates = ukfmt.VAT_RATES if w["vat_registered"] else (0,)
    return dict(all_companies=company_options, all_contacts=contact_options, stages=STAGES, owners=owner_names(),
                sources=SOURCES, kinds=ACTIVITY_KINDS, vat_rates=vat_rates,
                vat_labels=[{20: "20% standard", 5: "5% reduced", 0: "0% zero-rated"}[r] for r in vat_rates],
                regions=REGIONS, lawful_bases=LAWFUL_BASES, lifecycle_stages=LIFECYCLE_STAGES,
                ticket_priorities=TICKET_PRIORITIES, ticket_categories=TICKET_CATEGORIES, ticket_sources=TICKET_SOURCES,
                billing_periods=BILLING_PERIODS, stage_colours=STAGE_COLOURS)


def won_between(start, end):
    return scalar("SELECT SUM(value) FROM deals WHERE workspace_id=? AND stage='Won' AND closed_at >= ? AND closed_at < ?",
                  ws(), start.isoformat(), end.isoformat())


def register(app):

    @app.route("/welcome")
    def landing():
        if g.get("user"):
            return redirect(url_for("overview"))
        return render_template("landing.html")

    @app.route("/")
    def overview():
        t = today()
        target = workspace()["monthly_target"] or 1
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
        expected = target * elapsed / len(days)
        left = len(days) - elapsed
        track = dict(
            target=target, won=won_this, days=days, elapsed=elapsed, left=left,
            won_pct=min(100, won_this / target * 100), expected_pct=elapsed / len(days) * 100,
            gap=won_this - expected, per_day=max(0, target - won_this) / left if left else 0, month=t.strftime("%B"),
        )

        months = [add_months(this_month, -i) for i in reversed(range(12))]
        by_month = {r[0]: plain(r[1]) for r in rows(
            "SELECT substr(closed_at,1,7), SUM(value) FROM deals WHERE workspace_id=? AND stage='Won' AND closed_at >= ? "
            "GROUP BY 1", ws(), months[0].isoformat())}
        series = [{"label": m.strftime("%b"), "full": m.strftime("%B %Y"),
                   "value": by_month.get(m.strftime("%Y-%m"), 0) / 100, "partial": m == this_month} for m in months]

        pipeline_value = scalar(f"SELECT SUM(value) FROM deals WHERE workspace_id=? AND {OPEN_SQL}", ws())
        open_count = scalar(f"SELECT COUNT(*) FROM deals WHERE workspace_id=? AND {OPEN_SQL}", ws())
        forecast = scalar(f"SELECT SUM(value * probability / 100) FROM deals WHERE workspace_id=? AND {OPEN_SQL}", ws())
        year_ago = add_months(this_month, -11).isoformat()
        won_n = scalar("SELECT COUNT(*) FROM deals WHERE workspace_id=? AND stage='Won' AND closed_at >= ?", ws(), year_ago)
        lost_n = scalar("SELECT COUNT(*) FROM deals WHERE workspace_id=? AND stage='Lost' AND closed_at >= ?", ws(), year_ago)
        win_rate = round(won_n / (won_n + lost_n) * 100) if won_n + lost_n else 0
        created = {r[0]: plain(r[1]) for r in rows(
            "SELECT substr(created_at,1,7), SUM(value) FROM deals WHERE workspace_id=? AND created_at >= ? GROUP BY 1",
            ws(), months[0].isoformat())}

        closing_soon = rows(
            f"SELECT d.*, c.name AS company FROM deals d JOIN companies c ON c.id=d.company_id"
            f" WHERE d.workspace_id=? AND {OPEN_SQL} AND d.close_date <= ? ORDER BY d.close_date, d.value DESC LIMIT 6",
            ws(), (t + timedelta(days=30)).isoformat())
        mix_rows = {r["stage"]: r for r in rows(
            f"SELECT stage, SUM(value) AS total, COUNT(*) AS n FROM deals WHERE workspace_id=? AND {OPEN_SQL} GROUP BY stage",
            ws())}
        mix = [dict(stage=s, total=plain(mix_rows[s]["total"]) if s in mix_rows else 0,
                    n=mix_rows[s]["n"] if s in mix_rows else 0) for s in OPEN_STAGES]

        # Weighted value of open deals by the month they're expected to close, for the next six months.
        closing = {r[0]: plain(r[1]) for r in rows(
            f"SELECT substr(close_date,1,7), SUM(value * probability / 100) FROM deals WHERE workspace_id=? AND {OPEN_SQL} "
            f"GROUP BY 1", ws())}
        forecast_trend = [closing.get(add_months(this_month, i).strftime("%Y-%m"), 0) for i in range(6)]

        fy_label, q, q_start, q_end = fy_quarter(t)
        quota = target * 3
        quota_won = won_between(q_start, q_end)
        quota_pct = quota_won / quota * 100

        # Everything today (done or not), then whatever is still to do after it.
        agenda = rows(
            "SELECT a.*, c.name AS company FROM activities a LEFT JOIN companies c ON c.id=a.company_id"
            " WHERE a.workspace_id=? AND a.due_at >= ? AND (a.done=0 OR substr(a.due_at,1,10)=?) ORDER BY a.due_at LIMIT 6",
            ws(), t.isoformat(), t.isoformat())
        tickets_open = scalar("SELECT COUNT(*) FROM tickets WHERE workspace_id=? AND status <> 'Closed'", ws())
        tickets_breached = sum(1 for r in rows("SELECT first_response_due, first_responded_at, resolution_due FROM tickets "
                                               "WHERE workspace_id=? AND status <> 'Closed'", ws())
                               if sla_state(r["resolution_due"])[0] == "overdue"
                               or sla_state(r["first_response_due"], r["first_responded_at"])[0] in ("overdue", "breached"))

        return render_template(
            "overview.html", track=track, change=change, won_this=won_this,
            pipeline_value=pipeline_value, open_count=open_count, forecast=forecast, win_rate=win_rate,
            won_n=won_n, closed_n=won_n + lost_n,
            spark_won=charts.sparkline([s["value"] for s in series]),
            spark_created=charts.sparkline([created.get(m.strftime("%Y-%m"), 0) for m in months]),
            spark_forecast=charts.sparkline(forecast_trend),
            mix_donut=charts.donut([(m["stage"], m["total"], STAGE_COLOURS[m["stage"]],
                                     f'{m["stage"]}: {money(m["total"])} across {m["n"]} deals') for m in mix]),
            series_json=json.dumps({"series": series, "target": target / 100}),
            closing_soon=closing_soon, soon_cutoff=(t + timedelta(days=7)).isoformat(), mix=mix,
            quota=quota, quota_won=quota_won, quota_pct=quota_pct,
            quota_ring=charts.ring(quota_pct, label=f"{quota_pct:.0f}% of quarterly quota"),
            fy_label=fy_label, fy_q=q, q_end=q_end - timedelta(days=1), agenda=agenda,
            tickets_open=tickets_open, tickets_breached=tickets_breached,
            empty=not scalar("SELECT COUNT(*) FROM companies WHERE workspace_id=?", ws()))

    @app.route("/api/search")
    def search():
        q = request.args.get("q", "").strip()
        if len(q) < 2:
            return jsonify([])
        like = f"%{q.lower()}%"
        results = [dict(kind="Contact", title=f"{r['first_name']} {r['last_name']}",
                        detail=", ".join(filter(None, [r["email"], r["company"]])), url=url_for("contact", contact_id=r["id"]))
                   for r in rows("SELECT ct.*, c.name AS company FROM contacts ct LEFT JOIN companies c ON c.id=ct.company_id"
                                 " WHERE ct.workspace_id=? AND (LOWER(ct.first_name || ' ' || ct.last_name) LIKE ?"
                                 " OR LOWER(ct.email) LIKE ?) ORDER BY ct.first_name LIMIT 5", ws(), like, like)]
        results += [dict(kind="Company", title=r["name"], detail=f"{r['city']}, {r['postcode']}",
                         url=url_for("company", company_id=r["id"]))
                    for r in rows("SELECT * FROM companies WHERE workspace_id=? AND (LOWER(name) LIKE ? OR LOWER(city) LIKE ?"
                                  " OR LOWER(postcode) LIKE ?) ORDER BY name LIMIT 5", ws(), like, like, like)]
        results += [dict(kind="Deal", title=r["title"], detail=f"{r['company']}, {money(r['value'])}, {r['stage']}",
                         url=url_for("deal", deal_id=r["id"]))
                    for r in rows("SELECT d.*, c.name AS company FROM deals d JOIN companies c ON c.id=d.company_id"
                                  " WHERE d.workspace_id=? AND (LOWER(d.title) LIKE ? OR LOWER(c.name) LIKE ?)"
                                  " ORDER BY d.stage IN ('Won','Lost'), d.value DESC LIMIT 5", ws(), like, like)]
        results += [dict(kind="Ticket", title=r["subject"], detail=f"#{r['id']}, {r['status']}, {r['priority']}",
                         url=url_for("ticket", ticket_id=r["id"]))
                    for r in rows("SELECT * FROM tickets WHERE workspace_id=? AND LOWER(subject) LIKE ?"
                                  " ORDER BY status='Closed', id DESC LIMIT 5", ws(), like)]
        return jsonify(results)

    @app.route("/reports")
    def reports():
        db = get_db()

        def breakdown(column):
            data = rows(
                f"SELECT {column} AS k,"
                f" SUM(CASE WHEN stage='Won' THEN 1 ELSE 0 END) AS won_n,"
                f" SUM(CASE WHEN stage='Lost' THEN 1 ELSE 0 END) AS lost_n,"
                f" SUM(CASE WHEN stage='Won' THEN value END) AS won_value,"
                f" SUM(CASE WHEN {OPEN_SQL} THEN value END) AS pipeline"
                f" FROM deals WHERE workspace_id=? GROUP BY {column} ORDER BY won_value DESC NULLS LAST", ws())
            peak = max([plain(r["won_value"]) or 0 for r in data] + [1])
            return [dict(r) | {"rate": round(r["won_n"] / (r["won_n"] + r["lost_n"]) * 100) if r["won_n"] + r["lost_n"] else 0,
                               "share": (plain(r["won_value"]) or 0) / peak * 100} for r in data]

        avg_deal = scalar("SELECT AVG(value) FROM deals WHERE workspace_id=? AND stage='Won'", ws())
        cycle = scalar(f"SELECT AVG({db.days_between('closed_at', 'created_at')}) FROM deals WHERE workspace_id=? "
                       f"AND stage='Won'", ws())
        new_contacts = scalar("SELECT COUNT(*) FROM contacts WHERE workspace_id=? AND created_at >= ?",
                              ws(), (today() - timedelta(days=90)).isoformat())

        # Lifecycle funnel: how many people are at each stage.
        lifecycle = {r[0]: r[1] for r in rows("SELECT lifecycle_stage, COUNT(*) FROM contacts WHERE workspace_id=? GROUP BY 1",
                                              ws())}
        funnel = [(s, lifecycle.get(s, 0)) for s in LIFECYCLE_STAGES if s != "Other"]
        funnel_peak = max([n for _, n in funnel] + [1])

        # Service: tickets and how well service levels are being met.
        tickets = rows("SELECT * FROM tickets WHERE workspace_id=?", ws())
        responded = [t for t in tickets if t["first_responded_at"]]
        first_met = sum(1 for t in responded if t["first_responded_at"] <= t["first_response_due"])
        closed = [t for t in tickets if t["closed_at"]]
        resolved_met = sum(1 for t in closed if t["closed_at"] <= t["resolution_due"])
        service = dict(open=sum(1 for t in tickets if t["status"] != "Closed"), total=len(tickets),
                       first_rate=round(first_met / len(responded) * 100) if responded else None,
                       resolve_rate=round(resolved_met / len(closed) * 100) if closed else None,
                       by_category=sorted(({c: sum(1 for t in tickets if t["category"] == c)
                                            for c in {t["category"] for t in tickets}}).items(), key=lambda kv: -kv[1]))

        # Products by value in the open pipeline.
        products = rows("SELECT li.name, SUM(li.quantity) AS qty, SUM(li.quantity * li.unit_price * (100 - li.discount_pct) / 100)"
                        f" AS value FROM line_items li JOIN deals d ON d.id=li.deal_id WHERE li.workspace_id=? AND d.{OPEN_SQL}"
                        " GROUP BY li.name ORDER BY value DESC LIMIT 8", ws())
        product_peak = max([plain(p["value"]) for p in products] + [1])

        return render_template("reports.html", by_source=breakdown("source"), by_owner=breakdown("owner"),
                               avg_deal=avg_deal, cycle=round(cycle), new_contacts=new_contacts, funnel=funnel,
                               funnel_peak=funnel_peak, service=service, products=products, product_peak=product_peak,
                               plain=plain)

    # Old addresses from the first release.
    @app.route("/growth")
    def growth():
        return redirect(url_for("reports"))

    @app.route("/customers")
    @app.route("/customers/<int:company_id>")
    def customers(company_id=None):
        return redirect(url_for("company", company_id=company_id) if company_id else url_for("companies"))

    @app.route("/schedule")
    def schedule():
        return redirect(url_for("tasks", **request.args))

    @app.route("/finance")
    def finance():
        return redirect(url_for("invoices"))

