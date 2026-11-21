"""Durable, delayed workflow chains with conditional steps and transactional checkpoints."""

import json
from datetime import timedelta
from uuid import uuid4
from flask import abort, current_app, flash, g, redirect, render_template, request, url_for
import auth
import workflows
from core import log_event, now, one, rows, ws
from db import get_db

CONDITIONS = {"owner": "Owner", "stage": "Deal stage", "priority": "Ticket priority", "source": "Source"}


def enqueue(evt):
    if evt["event"] not in workflows.TRIGGERS:
        return
    db = get_db()
    stamp = now().isoformat(timespec="seconds")
    key = evt.get("event_key") or uuid4().hex
    for p in rows(
        "SELECT * FROM automation_plans WHERE workspace_id=? AND on_event=? AND active=1", ws(), evt["event"]
    ):
        if one("SELECT id FROM automation_jobs WHERE plan_id=? AND event_key=?", p["id"], key):
            continue
        steps = json.loads(p["steps"])
        db.insert(
            "automation_jobs",
            workspace_id=ws(),
            plan_id=p["id"],
            event_key=key,
            event_data=json.dumps(evt),
            steps=p["steps"],
            position=0,
            status="queued",
            due_at=(now() + timedelta(hours=steps[0]["delay"])).isoformat(timespec="seconds"),
            created_at=stamp,
        )
    db.commit()


def execute_step(job):
    evt = json.loads(job["event_data"])
    ctx = workflows.context(evt)
    if ctx is None:
        return "cancelled"
    step = json.loads(job["steps"])[job["position"]]
    condition = step.get("condition")
    action = step["action"]
    if condition:
        record = one(f"SELECT * FROM {ctx['table']} WHERE id=? AND workspace_id=?", ctx["id"], ws())
        matches = (
            condition["field"] in record.keys()
            and str(record[condition["field"]] or "") == condition["value"]
        )
        if not matches:
            if not step.get("otherwise"):
                return "skipped"
            action = step["otherwise"]
    settings = step["settings"]
    rule = dict(
        action=action,
        settings=json.dumps(settings),
        name=job["name"],
        runs=job["position"],
        created_by=job["created_by"],
    )
    note = workflows.act(rule, ctx)
    if note:
        log_event("Workflow: " + job["name"], note, **ctx["links"])
    return "done"


def run_due(limit=100):
    db = get_db()
    stamp = now().isoformat(timespec="seconds")
    total = 0
    db.execute(
        "UPDATE automation_jobs SET status='queued' WHERE status='running' AND lease_until<?", (stamp,)
    )
    db.commit()
    jobs = rows(
        "SELECT j.*,p.name,p.created_by FROM automation_jobs j JOIN automation_plans p ON p.id=j.plan_id WHERE j.status='queued' AND j.due_at<=? AND p.active=1 ORDER BY j.due_at,j.id LIMIT ?",
        stamp,
        limit,
    )
    for job in jobs:
        g.public_workspace = job["workspace_id"]
        g.pop("workspace", None)
        try:
            if not __import__("billing").state(__import__("core").workspace())["can_write"]:
                continue
            claim = db.execute(
                "UPDATE automation_jobs SET status='running',lease_until=? WHERE id=? AND status='queued' RETURNING id",
                ((now() + timedelta(minutes=10)).isoformat(timespec="seconds"), job["id"]),
            ).fetchone()
            db.commit()
            if not claim:
                continue
            outcome = execute_step(job)
            steps = json.loads(job["steps"])
            position = job["position"] + 1
            status = "cancelled" if outcome == "cancelled" else "done" if position == len(steps) else "queued"
            due = now() + timedelta(hours=steps[position]["delay"] if position < len(steps) else 0)
            db.execute(
                "UPDATE automation_jobs SET position=?,status=?,due_at=?,lease_until=NULL,last_error=NULL WHERE id=?",
                (position, status, due.isoformat(timespec="seconds"), job["id"]),
            )
            db.commit()
            total += 1
        except Exception:
            db.rollback()
            current_app.logger.exception("Workflow job %s failed", job["id"])
            db.execute(
                "UPDATE automation_jobs SET status='failed',attempts=attempts+1,last_error=?,lease_until=NULL WHERE id=?",
                (
                    "This step failed. No database changes from this attempt were kept. Review the rule and retry.",
                    job["id"],
                ),
            )
            db.commit()
        finally:
            g.pop("public_workspace", None)
            g.pop("workspace", None)
    return total


def register(app):
    @app.route("/automation", methods=["GET", "POST"])
    def automation_page():
        auth.admin_required()
        error = None
        if request.method == "POST":
            name = request.form.get("name", "").strip()[:80]
            event = request.form.get("on_event")
            steps = []
            for i in range(6):
                action = request.form.get(f"action_{i}")
                if not action:
                    continue
                delay = request.form.get(f"delay_{i}", "0")
                if action not in workflows.ACTIONS or not delay.isdigit() or int(delay) > 2160:
                    abort(422)
                who = request.form.get(f"person_{i}", "owner")
                if who not in workflows.team_names() + ["owner", "rotate"]:
                    abort(422)
                subject = request.form.get(f"subject_{i}", "").strip()[:120]
                stage = request.form.get(f"lifecycle_{i}", "Lead")
                if action == "lifecycle" and stage not in __import__("db").LIFECYCLE_STAGES:
                    abort(422)
                if action == "task" and not subject:
                    abort(422, "A task needs a subject.")
                field = request.form.get(f"condition_{i}", "")
                if field and field not in CONDITIONS:
                    abort(422)
                condition = (
                    dict(field=field, value=request.form.get(f"equals_{i}", "")[:100]) if field else None
                )
                # The alternate branch skips the action; each subsequent step has its own condition.
                steps.append(
                    dict(
                        action=action,
                        delay=int(delay),
                        condition=condition,
                        settings=dict(
                            person=who, subject=subject, kind="Task", days=0, message=subject, stage=stage
                        ),
                    )
                )
            if not name or event not in workflows.TRIGGERS or not steps:
                abort(422, "Give the workflow a name, trigger and at least one step.")
            if one("SELECT COUNT(*) FROM automation_plans WHERE workspace_id=?", ws())[0] >= 50:
                abort(422)
            get_db().insert(
                "automation_plans",
                workspace_id=ws(),
                name=name,
                on_event=event,
                steps=json.dumps(steps),
                created_by=g.user["name"],
                created_at=now().isoformat(),
            )
            get_db().commit()
            flash(
                "Workflow saved. Each conditional step runs if its condition matches; otherwise it is skipped.",
                "ok",
            )
            return redirect(url_for("automation_page"))
        return render_template(
            "automation_page.html",
            plans=rows("SELECT * FROM automation_plans WHERE workspace_id=? ORDER BY id DESC", ws()),
            jobs=rows(
                "SELECT j.*,p.name FROM automation_jobs j JOIN automation_plans p ON p.id=j.plan_id WHERE j.workspace_id=? ORDER BY j.id DESC LIMIT 100",
                ws(),
            ),
            triggers=workflows.TRIGGERS,
            actions=workflows.ACTIONS,
            people=workflows.team_names(),
            conditions=CONDITIONS,
            lifecycle=__import__("db").LIFECYCLE_STAGES,
        )

    @app.post("/automation/<int:plan_id>/toggle")
    def automation_toggle(plan_id):
        auth.admin_required()
        if not one("SELECT id FROM automation_plans WHERE id=? AND workspace_id=?", plan_id, ws()):
            abort(404)
        get_db().execute(
            "UPDATE automation_plans SET active=1-active WHERE id=? AND workspace_id=?", (plan_id, ws())
        )
        get_db().commit()
        return redirect(url_for("automation_page"))

    @app.post("/automation/jobs/<int:job_id>/retry")
    def automation_retry(job_id):
        auth.admin_required()
        job = one("SELECT * FROM automation_jobs WHERE id=? AND workspace_id=?", job_id, ws())
        if not job:
            abort(404)
        get_db().execute(
            "UPDATE automation_jobs SET status='queued',due_at=?,last_error=NULL WHERE id=? AND status='failed'",
            (now().isoformat(timespec="seconds"), job_id),
        )
        get_db().commit()
        return redirect(url_for("automation_page"))
