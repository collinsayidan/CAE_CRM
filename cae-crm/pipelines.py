"""Workspace-owned sales pipelines. Stage gates apply to UI, API and quote acceptance."""

import json
from flask import abort, flash, g, has_request_context, redirect, render_template, request, url_for
from werkzeug.local import LocalProxy
from db import STAGES as DEFAULT_STAGES, get_db
from core import now, one, rows, ws
import auth

REQUIRED = {"contact_id": "Contact", "value": "Value above zero", "source": "Lead source"}


def catalog():
    return rows("SELECT * FROM sales_pipelines WHERE workspace_id=? ORDER BY id", ws())


def selected_id(strict=True):
    if not has_request_context() or not (g.get("user") or g.get("public_workspace")):
        return None
    deal_id = (request.view_args or {}).get("deal_id")
    if deal_id:
        row = one("SELECT pipeline_id FROM deals WHERE id=? AND workspace_id=?", deal_id, ws())
        if row:
            return row[0]
    raw = request.values.get("pipeline_id")
    if raw:
        row = one(
            "SELECT id FROM sales_pipelines WHERE id=? AND workspace_id=?",
            int(raw) if raw.isdigit() else 0,
            ws(),
        )
        if not row:
            if strict:
                abort(404)
            return None
        return row[0]
    return None


def stage_rows(pipeline_id=None):
    if pipeline_id is None:
        return []
    return rows(
        "SELECT * FROM pipeline_stages WHERE workspace_id=? AND pipeline_id=? ORDER BY position,id",
        ws(),
        pipeline_id,
    )


def choices():
    if not has_request_context() or not (g.get("user") or g.get("public_workspace")):
        return list(DEFAULT_STAGES)
    pid = selected_id(strict=False)
    if pid:
        return [(r["name"], r["probability"]) for r in stage_rows(pid)]
    # Legacy/default pipeline keeps its existing labels. Reports and filters also recognise custom stages.
    extra = rows(
        "SELECT name,probability FROM pipeline_stages WHERE workspace_id=? ORDER BY position,id", ws()
    )
    return list(dict(DEFAULT_STAGES + [(r[0], r[1]) for r in extra]).items())


STAGES = LocalProxy(choices)
OPEN_STAGES = LocalProxy(lambda: [s for s, _ in choices()])
STAGE_PROBABILITY = LocalProxy(lambda: dict(choices()) | {"Won": 100, "Lost": 0})


def validate_stage(deal, stage):
    stages = stage_rows(deal["pipeline_id"])
    options = {r["name"]: r["probability"] for r in stages} if deal["pipeline_id"] else dict(DEFAULT_STAGES)
    if stage in ("Won", "Lost"):
        return 100 if stage == "Won" else 0
    if stage not in options:
        abort(422, "Choose a stage in this deal's pipeline.")
    row = next((r for r in stages if r["name"] == stage), None)
    missing = [REQUIRED[k] for k in json.loads(row["required_fields"]) if not deal[k]] if row else []
    if missing:
        abort(422, "Before moving this deal, complete: " + ", ".join(missing))
    return options[stage]


def register(app):
    app.add_template_global(catalog, "sales_pipelines")

    @app.route("/settings/pipelines", methods=["GET", "POST"])
    def pipeline_settings():
        auth.admin_required()
        error = None
        if request.method == "POST":
            name = request.form.get("name", "").strip()[:70]
            labels = request.form.getlist("stage_name")
            probabilities = request.form.getlist("probability")
            if not labels:  # accessible multiline alternative: name | probability | required field keys
                lines = [l.split("|") for l in request.form.get("stages", "").splitlines() if l.strip()]
                labels = [l[0].strip() for l in lines]
                probabilities = [l[1].strip() if len(l) > 1 else "" for l in lines]
            else:
                lines = [[n, p] for n, p in zip(labels, probabilities)]
            valid = (
                name
                and 1 <= len(labels) <= 12
                and len(set(labels)) == len(labels)
                and all(n and len(n) <= 50 and n not in ("Won", "Lost") for n in labels)
                and len(labels) == len(probabilities)
                and all(p.isdigit() and 0 <= int(p) <= 99 for p in probabilities)
            )
            gates = [[k.strip() for k in l[2].split(",") if k.strip()] if len(l) > 2 else [] for l in lines]
            if not valid or any(k not in REQUIRED for gs in gates for k in gs):
                error = (
                    "Use a unique pipeline name and 1–12 unique stages, each with a probability from 0 to 99."
                )
            elif one("SELECT id FROM sales_pipelines WHERE workspace_id=? AND name=?", ws(), name):
                error = "A pipeline with that name already exists."
            elif len(catalog()) >= 20:
                error = "A workspace can have up to 20 pipelines."
            else:
                db = get_db()
                pid = db.insert("sales_pipelines", workspace_id=ws(), name=name, created_at=now().isoformat())
                for i, (n, p) in enumerate(zip(labels, probabilities)):
                    db.insert(
                        "pipeline_stages",
                        workspace_id=ws(),
                        pipeline_id=pid,
                        name=n,
                        probability=int(p),
                        position=i,
                        required_fields=json.dumps(gates[i]),
                    )
                db.commit()
                flash("Pipeline created. Select it on the Deals board to add deals.", "ok")
                return redirect(url_for("pipeline", pipeline_id=pid))
        return render_template(
            "pipeline_settings.html", pipelines=catalog(), stage_rows=stage_rows, error=error
        ), (422 if error else 200)

    @app.post("/settings/pipelines/stages/<int:stage_id>")
    def update_pipeline_stage(stage_id):
        auth.admin_required()
        stage = one("SELECT * FROM pipeline_stages WHERE id=? AND workspace_id=?", stage_id, ws())
        if not stage:
            abort(404)
        name = request.form.get("name", "").strip()
        probability = request.form.get("probability", "")
        if (
            not name
            or len(name) > 50
            or name in ("Won", "Lost")
            or not probability.isdigit()
            or not 0 <= int(probability) <= 99
        ):
            abort(422)
        if one(
            "SELECT id FROM pipeline_stages WHERE pipeline_id=? AND name=? AND id<>?",
            stage["pipeline_id"],
            name,
            stage_id,
        ):
            abort(409)
        required = request.form.getlist("required")
        if any(k not in REQUIRED for k in required):
            abort(422)
        db = get_db()
        db.execute(
            "UPDATE pipeline_stages SET name=?,probability=?,required_fields=? WHERE id=? AND workspace_id=?",
            (name, int(probability), json.dumps(required), stage_id, ws()),
        )
        db.execute(
            "UPDATE deals SET stage=?,probability=? WHERE workspace_id=? AND pipeline_id=? AND stage=?",
            (name, int(probability), ws(), stage["pipeline_id"], stage["name"]),
        )
        db.commit()
        flash(
            "Stage updated. Review any saved filters or workflow conditions that use its previous name.", "ok"
        )
        return redirect(url_for("pipeline_settings"))

    @app.post("/deals/<int:deal_id>/pipeline")
    def transfer_deal_pipeline(deal_id):
        from core import get_or_404, log_event
        from events import emit
        from sales import set_stage

        deal = get_or_404("deals", deal_id)
        if deal["stage"] in ("Won", "Lost"):
            abort(422, "Only open deals can move between pipelines.")
        raw = request.form.get("pipeline_id", "")
        pid = None
        if raw:
            pipeline = one(
                "SELECT id FROM sales_pipelines WHERE id=? AND workspace_id=?",
                int(raw) if raw.isdigit() else 0,
                ws(),
            )
            if not pipeline:
                abort(404)
            pid = pipeline[0]
        options = (
            dict((r["name"], r["probability"]) for r in stage_rows(pid)) if pid else dict(DEFAULT_STAGES)
        )
        stage = request.form.get("stage") or next(iter(options))
        if stage not in options:
            abort(422, "Choose a stage in the destination pipeline.")
        candidate = dict(deal)
        candidate["pipeline_id"] = pid
        validate_stage(candidate, stage)
        db = get_db()
        db.execute("UPDATE deals SET pipeline_id=? WHERE id=? AND workspace_id=?", (pid, deal_id, ws()))
        set_stage(candidate, stage)
        log_event(
            "Sales pipeline changed",
            "Deal transferred to a different sales process.",
            deal_id=deal_id,
            company_id=deal["company_id"],
        )
        emit("deal.updated", deal_id)
        db.commit()
        return redirect(url_for("deal", deal_id=deal_id))
