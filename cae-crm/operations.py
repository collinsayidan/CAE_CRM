"""Guided setup, worker telemetry and readiness without exposing credentials or customer data."""

import hmac
import json
import time
from datetime import timedelta
from flask import abort, current_app, g, jsonify, redirect, render_template, request, url_for
import auth
from core import now, one, rows, ws
from db import get_db

TEMPLATES = {
    "consultancy": {
        "name": "Consultancy",
        "fields": [
            ("deals", "Engagement type", "choice", ["Advisory", "Implementation", "Retainer"]),
            ("companies", "Contract renewal", "date", []),
        ],
        "stages": [("Enquiry", 10), ("Discovery", 30), ("Scope agreed", 60), ("Contract review", 90)],
    },
    "agency": {
        "name": "Agency",
        "fields": [
            ("deals", "Service", "choice", ["Design", "Marketing", "Development", "Retainer"]),
            ("companies", "Account review date", "date", []),
        ],
        "stages": [("Enquiry", 10), ("Brief received", 30), ("Proposal shared", 60), ("Contract review", 90)],
    },
    "it_support": {
        "name": "IT support",
        "fields": [
            ("companies", "Support tier", "choice", ["Standard", "Priority", "Managed"]),
            ("companies", "Renewal date", "date", []),
        ],
        "stages": [
            ("Enquiry", 10),
            ("Technical assessment", 30),
            ("Solution proposed", 60),
            ("Contract review", 90),
        ],
    },
}


def setup_checks():
    from notifications import checklist
    from core import workspace

    checks = checklist(workspace(), g.user)
    return checks + [
        (
            "Review team permissions",
            one("SELECT COUNT(*) FROM users WHERE workspace_id=? AND role NOT IN ('admin','member')", ws())[0]
            > 0,
            url_for("access_settings"),
        ),
        (
            "Connect a mailbox",
            one(
                "SELECT COUNT(*) FROM connections WHERE workspace_id=? AND user_id=? AND provider IN ('google','microsoft')",
                ws(),
                g.user["id"],
            )[0]
            > 0,
            url_for("integrations"),
        ),
        (
            "Set up your sales pipeline",
            one("SELECT COUNT(*) FROM sales_pipelines WHERE workspace_id=?", ws())[0] > 0,
            url_for("pipeline_settings"),
        ),
        (
            "Create your meeting booking link",
            one("SELECT id FROM booking_pages WHERE workspace_id=? AND user_id=?", ws(), g.user["id"])
            is not None,
            url_for("calendar_page"),
        ),
    ]


def fast_jobs():
    import automation, sequences, insights, integrations, webhooks

    db = get_db()
    stamp = now().isoformat(timespec="seconds")
    old = one("SELECT * FROM job_health WHERE name='fast'")
    if not old:
        db.insert("job_health", name="fast", status="idle")
        db.commit()
    # One fast worker per installation, with a lease recoverable after 15 minutes.
    claimed = db.execute(
        "UPDATE job_health SET status='running',started_at=? WHERE name='fast' AND (status<>'running' OR started_at<?) RETURNING id",
        (stamp, (now() - timedelta(minutes=30)).isoformat(timespec="seconds")),
    ).fetchone()
    db.commit()
    if not claimed:
        return dict(status="already_running")
    try:
        summary = {}
        synced = 0
        for c in rows(
            "SELECT * FROM connections WHERE provider IN ('google','microsoft') AND (last_sync_at IS NULL OR last_sync_at<=?) ORDER BY COALESCE(last_sync_at,''),id LIMIT 3",
            (now() - timedelta(minutes=5)).isoformat(timespec="minutes"),
        ):
            integrations.run_sync(c)
            synced += 1
        summary.update(
            workflow_steps=automation.run_due(limit=50),
            sequence_steps=sequences.run_due(limit=10),
            scheduled_reports=insights.run_schedules(limit=5),
            mailboxes_checked=synced,
        )
        # Deliver webhooks on the fast cadence too; their own queue controls retries.
        summary["webhooks"] = webhooks.retry_due()
        db.execute(
            "DELETE FROM portal_links WHERE expires_at<?",
            ((now() - timedelta(days=1)).isoformat(timespec="seconds"),),
        )
        db.execute(
            "DELETE FROM portal_attempts WHERE created_at<?",
            ((now() - timedelta(days=1)).isoformat(timespec="seconds"),),
        )
        db.execute(
            "UPDATE job_health SET status='ok',finished_at=?,summary=? WHERE name='fast'",
            (now().isoformat(timespec="seconds"), json.dumps(summary)),
        )
        db.commit()
        return summary
    except Exception:
        db.rollback()
        db.execute(
            "UPDATE job_health SET status='failed',finished_at=? WHERE name='fast'",
            (now().isoformat(timespec="seconds"),),
        )
        db.commit()
        raise


def register(app):
    @app.route("/getting-started", methods=["GET", "POST"])
    def onboarding_page():
        auth.admin_required()
        if request.method == "POST":
            template = TEMPLATES.get(request.form.get("template"))
            if not template:
                abort(422)
            if one("SELECT id FROM workspace_templates WHERE workspace_id=?", ws()):
                abort(
                    409,
                    "An industry template has already been applied. Edit fields and pipelines directly to customise it.",
                )
            if (
                one("SELECT COUNT(*) FROM custom_fields WHERE workspace_id=?", ws())[0]
                + len(template["fields"])
                > 30
            ):
                abort(422)
            db = get_db()
            pid = db.insert(
                "sales_pipelines",
                workspace_id=ws(),
                name=template["name"] + " sales",
                created_at=now().isoformat(),
            )
            for i, (stage, probability) in enumerate(template["stages"]):
                db.insert(
                    "pipeline_stages",
                    workspace_id=ws(),
                    pipeline_id=pid,
                    name=stage,
                    probability=probability,
                    position=i,
                    required_fields="[]",
                )
            for i, (obj, label, kind, options) in enumerate(template["fields"]):
                if not one(
                    "SELECT id FROM custom_fields WHERE workspace_id=? AND object=? AND label=?",
                    ws(),
                    obj,
                    label,
                ):
                    db.insert(
                        "custom_fields",
                        workspace_id=ws(),
                        object=obj,
                        label=label,
                        field_type=kind,
                        options=json.dumps(options),
                        position=i,
                        created_at=now().isoformat(),
                    )
            db.insert(
                "workspace_templates", workspace_id=ws(), name=template["name"], applied_at=now().isoformat()
            )
            db.commit()
            return redirect(url_for("onboarding_page"))
        return render_template(
            "onboarding_page.html",
            checks=setup_checks(),
            templates=TEMPLATES,
            applied=one("SELECT * FROM workspace_templates WHERE workspace_id=?", ws()),
        )

    @app.get("/settings/reliability")
    def reliability_page():
        auth.admin_required()
        return render_template(
            "reliability_page.html",
            worker=one("SELECT * FROM job_health WHERE name='fast'"),
            connections=rows(
                "SELECT provider,account,last_sync_at,last_error FROM connections WHERE workspace_id=?", ws()
            ),
            failed_workflows=one(
                "SELECT COUNT(*) FROM automation_jobs WHERE workspace_id=? AND status='failed'", ws()
            )[0],
            failed_sequences=one(
                "SELECT COUNT(*) FROM sequence_enrollments WHERE workspace_id=? AND status IN ('failed','sending')",
                ws(),
            )[0],
            pending=one(
                "SELECT COUNT(*) FROM automation_jobs WHERE workspace_id=? AND status='queued' AND due_at<?",
                ws(),
                (now() - timedelta(minutes=15)).isoformat(timespec="seconds"),
            )[0],
            monitoring=current_app.config.get("MONITORING"),
            stale=not one(
                "SELECT id FROM job_health WHERE name='fast' AND status='ok' AND finished_at>=?",
                (now() - timedelta(minutes=15)).isoformat(timespec="seconds"),
            ),
        )

    @app.get("/readyz")
    def readiness():
        try:
            get_db().execute("SELECT 1").fetchone()
        except Exception:
            return jsonify(status="unavailable"), 503
        return jsonify(status="ready"), 200, {"Cache-Control": "no-store"}

    @app.get("/cron/fast")
    def cron_fast():
        secret = current_app.config.get("CRON_SECRET")
        if not secret or not hmac.compare_digest(
            request.headers.get("Authorization", ""), "Bearer " + secret
        ):
            abort(403)
        g.user = None
        return jsonify(fast_jobs())

    @app.before_request
    def start_request_timer():
        g.request_started = time.monotonic()

    @app.after_request
    def request_timing(response):
        start = g.get("request_started")
        if start is not None:
            elapsed = (time.monotonic() - start) * 1000
            response.headers["Server-Timing"] = f"app;dur={elapsed:.1f}"
            if elapsed > 2000:
                current_app.logger.warning(
                    "Slow request endpoint=%s duration_ms=%.0f", request.endpoint, elapsed
                )
        if request.endpoint and request.endpoint.startswith(("public_portal_", "public_booking")):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
        return response
