"""Allowlisted report builder and auditable sales forecast reviews."""

import json
from datetime import date, timedelta
from flask import abort, flash, g, redirect, render_template, request, url_for
import auth
from core import get_or_404, log_event, now, one, rows, today, ws
from db import get_db
from permissions import can, staff_in_scope

ENTITIES = {
    "deals": ("Deals", ["owner", "stage", "source"], "value", "sales"),
    "tickets": ("Tickets", ["owner", "status", "priority", "category"], None, "support"),
    "invoices": ("Invoices", ["paid_date"], "net", "finance"),
}
METRICS = {"count": "Record count", "value": "Total value (£)", "weighted": "Weighted value (£)"}
CATEGORIES = ("Pipeline", "Best case", "Commit", "Omitted")


def definition(form):
    default = next((k for k, v in ENTITIES.items() if can(v[3])), "deals")
    obj = form.get("object", default)
    dimension = form.get("dimension", ENTITIES[obj][1][0] if obj in ENTITIES else "owner")
    metric = form.get("metric", "count")
    if obj not in ENTITIES or not can(ENTITIES[obj][3]):
        abort(403)
    if dimension not in ENTITIES[obj][1] + ["month"] or metric not in METRICS:
        abort(422)
    if (obj == "tickets" and metric != "count") or (metric == "weighted" and obj != "deals"):
        abort(422)
    try:
        start = date.fromisoformat(form.get("start", today().replace(day=1).isoformat()))
        end = date.fromisoformat(form.get("end", today().isoformat()))
    except (ValueError, TypeError):
        abort(422)
    if start > end or (end - start).days > 1096:
        abort(422, "Choose a date range up to three years.")
    return dict(object=obj, dimension=dimension, metric=metric, start=start.isoformat(), end=end.isoformat())


def results(d):
    obj = d["object"]
    dimension = d["dimension"]
    metric = d["metric"]
    stamp = "issue_date" if obj == "invoices" else "created_at"
    # Dates and identifiers are validated against fixed choices before this function is called.
    group = (
        f"substr({stamp},1,7)"
        if dimension == "month"
        else (
            "CASE WHEN paid_date IS NULL THEN 'Unpaid' ELSE 'Paid' END"
            if dimension == "paid_date"
            else dimension
        )
    )
    expression = (
        "COUNT(*)"
        if metric == "count"
        else "SUM(value * probability / 100)" if metric == "weighted" else "SUM(" + ENTITIES[obj][2] + ")"
    )
    return rows(
        f"SELECT {group} AS label, {expression} AS amount FROM {obj} WHERE workspace_id=? AND substr({stamp},1,10)>=? AND substr({stamp},1,10)<=? GROUP BY 1 ORDER BY 1",
        ws(),
        d["start"],
        d["end"],
    )


def compare(d):
    start = date.fromisoformat(d["start"])
    end = date.fromisoformat(d["end"])
    days = (end - start).days + 1
    return dict(
        d, start=(start - timedelta(days=days)).isoformat(), end=(start - timedelta(days=1)).isoformat()
    )


def run_schedules(limit=20):
    import mail
    from markupsafe import escape

    db = get_db()
    sent = 0
    for r in rows(
        "SELECT * FROM report_definitions WHERE schedule='weekly' AND next_send<=? ORDER BY id LIMIT ?",
        now().isoformat(timespec="seconds"),
        limit,
    ):
        g.public_workspace = r["workspace_id"]
        g.pop("workspace", None)
        try:
            # Only an active admin's scheduled report is allowed to read all workspace records.
            creator = one("SELECT * FROM users WHERE id=? AND workspace_id=?", r["created_by"], ws())
            recipient = one("SELECT * FROM users WHERE id=? AND workspace_id=?", r["recipient_id"], ws())
            if not creator or creator["role"] != "admin" or not recipient or recipient["role"] != "admin":
                db.execute(
                    "UPDATE report_definitions SET schedule=NULL,last_error='Scheduling requires an active administrator recipient and creator' WHERE id=?",
                    (r["id"],),
                )
                db.commit()
                continue
            due = r["next_send"]
            next_due = (now() + timedelta(days=7)).isoformat(timespec="seconds")
            if not db.execute(
                "UPDATE report_definitions SET next_send=? WHERE id=? AND next_send=? RETURNING id",
                (next_due, r["id"], due),
            ).fetchone():
                continue
            db.commit()
            d = json.loads(r["definition"])
            d.update(start=(today() - timedelta(days=6)).isoformat(), end=today().isoformat())
            lines = [
                f"{x['label'] or 'Unassigned'}: {x['amount'] if d['metric']=='count' else format(x['amount']/100,'.2f')}"
                for x in results(d)
            ]
            text = r["name"] + "\nLast seven days\n\n" + "\n".join(lines)
            msg = mail.message(
                recipient["email"], r["name"], "<pre>" + str(escape(text)) + "</pre>", text, "CAE CRM"
            )
            if mail.from_demo(msg):
                continue
            if __import__("flask").current_app.config.get("MAIL_BACKEND") == "memory":
                mail.send(msg)
            else:
                mail.check_allowance(1)
                mail._post("/emails", msg, idempotency_key=f"report-{r['id']}-{due}")
            db.execute("UPDATE report_definitions SET last_error=NULL WHERE id=?", (r["id"],))
            db.commit()
            sent += 1
        except Exception:
            db.rollback()
            # Don't resend uncertain deliveries automatically.
            db.execute(
                "UPDATE report_definitions SET last_error='Report delivery needs review; the next scheduled run is unchanged' WHERE id=?",
                (r["id"],),
            )
            db.commit()
        finally:
            g.pop("public_workspace", None)
            g.pop("workspace", None)
    return sent


def register(app):
    @app.route("/reports/builder", methods=["GET", "POST"])
    def report_builder():
        selected = (
            one(
                "SELECT * FROM report_definitions WHERE id=? AND workspace_id=?",
                request.args.get("report_id"),
                ws(),
            )
            if request.args.get("report_id")
            else None
        )
        if request.args.get("report_id") and not selected:
            abort(404)
        d = definition(
            json.loads(selected["definition"])
            if selected and not request.args.get("object")
            else request.values
        )
        current = results(d)
        previous = results(compare(d))
        if request.method == "POST":
            auth.admin_required()
            name = request.form.get("name", "").strip()[:80]
            if not name:
                abort(422)
            schedule = "weekly" if request.form.get("weekly") == "on" else None
            get_db().insert(
                "report_definitions",
                workspace_id=ws(),
                name=name,
                definition=json.dumps(d),
                created_by=g.user["id"],
                recipient_id=g.user["id"] if schedule else None,
                schedule=schedule,
                next_send=(now() + timedelta(days=7)).isoformat(timespec="seconds") if schedule else None,
            )
            get_db().commit()
            return redirect(url_for("report_builder"))
        return render_template(
            "report_builder.html",
            definition=d,
            results=current,
            previous_total=sum(r["amount"] for r in previous),
            total=sum(r["amount"] for r in current),
            entities={k: v for k, v in ENTITIES.items() if can(v[3])},
            metrics=METRICS,
            saved=[
                r
                for r in rows("SELECT * FROM report_definitions WHERE workspace_id=? ORDER BY name", ws())
                if can(ENTITIES[json.loads(r["definition"])["object"]][3])
            ],
        )

    @app.post("/reports/saved/<int:report_id>/delete")
    def delete_saved_report(report_id):
        auth.admin_required()
        get_db().execute("DELETE FROM report_definitions WHERE id=? AND workspace_id=?", (report_id, ws()))
        get_db().commit()
        return redirect(url_for("report_builder"))

    @app.route("/forecast", methods=["GET", "POST"])
    def forecast_page():
        if not can("sales"):
            abort(403)
        if request.method == "POST":
            if g.user["role"] not in ("admin", "manager"):
                abort(403)
            deal = get_or_404("deals", request.form.get("deal_id"))
            category = request.form.get("category")
            if category not in CATEGORIES:
                abort(422)
            note = request.form.get("note", "").strip()[:500]
            get_db().execute(
                "UPDATE deals SET forecast_category=? WHERE id=? AND workspace_id=?",
                (category, deal["id"], ws()),
            )
            get_db().insert(
                "forecast_reviews",
                workspace_id=ws(),
                deal_id=deal["id"],
                category=category,
                note=note,
                reviewed_by=g.user["name"],
                created_at=now().isoformat(timespec="seconds"),
            )
            log_event("Forecast review: " + category, note, deal_id=deal["id"], company_id=deal["company_id"])
            get_db().commit()
            return redirect(url_for("forecast_page", month=request.form.get("month")))
        month = request.args.get("month", today().strftime("%Y-%m"))
        try:
            date.fromisoformat(month + "-01")
        except (ValueError, TypeError):
            abort(422)
        deals = rows(
            "SELECT * FROM deals WHERE workspace_id=? AND substr(close_date,1,7)=? AND stage NOT IN ('Won','Lost') ORDER BY owner,close_date",
            ws(),
            month,
        )
        totals = {
            category: sum(d["value"] for d in deals if d["forecast_category"] == category)
            for category in CATEGORIES
        }
        targets = rows(
            "SELECT t.*,u.name,u.department FROM sales_targets t JOIN users u ON u.id=t.user_id WHERE t.workspace_id=? AND t.month=?",
            ws(),
            month,
        )
        targets = [t for t in targets if staff_in_scope(dict(id=t["user_id"], department=t["department"]))]
        return render_template(
            "forecast_page.html",
            month=month,
            deals=deals,
            categories=CATEGORIES,
            totals=totals,
            weighted=sum(
                d["value"] * d["probability"] // 100 for d in deals if d["forecast_category"] != "Omitted"
            ),
            targets=targets,
            people=rows("SELECT id,name FROM users WHERE workspace_id=? ORDER BY name", ws()),
            reviews=rows(
                "SELECT r.* FROM forecast_reviews r JOIN deals d ON d.id=r.deal_id WHERE r.workspace_id=? ORDER BY r.id DESC LIMIT 30",
                ws(),
            ),
        )

    @app.post("/forecast/targets")
    def forecast_target():
        if g.user["role"] not in ("admin", "manager"):
            abort(403)
        from ukfmt import parse_amount

        amount = parse_amount(request.form.get("amount", ""))
        uid = request.form.get("user_id")
        month = request.form.get("month", "")
        try:
            date.fromisoformat(month + "-01")
        except ValueError:
            abort(422)
        if amount is None or amount < 0:
            abort(422)
        person = one("SELECT id,department FROM users WHERE workspace_id=? AND id=?", ws(), uid)
        if not person or not staff_in_scope(person):
            abort(404)
        db = get_db()
        old = one("SELECT id FROM sales_targets WHERE user_id=? AND month=?", uid, month)
        if old:
            db.execute("UPDATE sales_targets SET amount=? WHERE id=?", (amount, old[0]))
        else:
            db.insert("sales_targets", workspace_id=ws(), user_id=int(uid), month=month, amount=amount)
        db.commit()
        return redirect(url_for("forecast_page", month=month))
