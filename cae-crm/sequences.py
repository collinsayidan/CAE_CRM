"""Opt-in follow-up sequences. No step sends without consent rechecked at delivery time."""

import json
from datetime import timedelta
from flask import abort, current_app, flash, g, redirect, render_template, request, url_for
from itsdangerous import BadSignature, URLSafeSerializer
from markupsafe import escape
import auth
import mail
from core import log_event, now, one, rows, workspace, ws
from db import get_db


def stop_for_contact(contact_id, reason):
    get_db().execute(
        "UPDATE sequence_enrollments SET status='stopped',stop_reason=? WHERE workspace_id=? AND contact_id=? AND status IN ('active','sending','failed')",
        (reason, ws(), contact_id),
    )


def stop_for_deal(deal_id):
    d = one("SELECT contact_id FROM deals WHERE workspace_id=? AND id=?", ws(), deal_id)
    if d and d[0]:
        stop_for_contact(d[0], "Deal won")
        get_db().commit()


def signer():
    return URLSafeSerializer(current_app.config["SECRET_KEY"], salt="cae-sequence-unsubscribe")


def deliver(enrollment, contact, step):
    key = f"cae-sequence-{enrollment['id']}-{enrollment['position']}"
    link = url_for("sequence_unsubscribe", token=signer().dumps([ws(), contact["id"]]), _external=True)
    reply = workspace()["reply_to"] or ""
    connection = one(
        "SELECT id,last_sync_at,last_error FROM connections WHERE workspace_id=? AND lower(account)=? AND provider IN ('google','microsoft')",
        ws(),
        reply.lower(),
    )
    if not connection or connection["last_error"]:
        raise mail.MailError(
            "Connect the reply-to mailbox and resolve its sync errors before sending follow-up emails."
        )
    body = step["body"].replace("{{first_name}}", contact["first_name"])
    text = (
        body
        + f"\n\n{workspace()['name']}\nYou agreed to receive email from this business. Unsubscribe: {link}"
    )
    msg = mail.message(
        contact["email"],
        step["subject"],
        "<p>" + str(escape(text)).replace("\n", "<br>") + "</p>",
        text,
        workspace()["name"],
        reply_to=workspace()["reply_to"],
        headers={"List-Unsubscribe": f"<{link}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"},
    )
    if mail.from_demo(msg):
        return
    mail.check_allowance(1)
    if current_app.config.get("MAIL_BACKEND") == "memory":
        sent = current_app.extensions.setdefault("sequence_keys", set())
        if key not in sent:
            mail.send(msg)
            sent.add(key)
    else:
        if not mail.configured():
            raise mail.MailError("Email is not configured.")
        mail._post("/emails", msg, idempotency_key=key)


def run_due(limit=50):
    db = get_db()
    total = 0
    # A crashed delivery has an unknown outcome. Never automatically resend it after the provider's
    # idempotency window; it stays visible for a person to investigate.
    enrollments = rows(
        "SELECT * FROM sequence_enrollments WHERE status='active' AND due_at<=? ORDER BY due_at,id LIMIT ?",
        now().isoformat(timespec="seconds"),
        limit,
    )
    for enrollment in enrollments:
        g.public_workspace = enrollment["workspace_id"]
        g.pop("workspace", None)
        try:
            if not __import__("billing").state(workspace())["can_write"]:
                continue
            if not db.execute(
                "UPDATE sequence_enrollments SET status='sending' WHERE id=? AND status='active' RETURNING id",
                (enrollment["id"],),
            ).fetchone():
                continue
            db.commit()
            c = one("SELECT * FROM contacts WHERE id=? AND workspace_id=?", enrollment["contact_id"], ws())
            if (
                not c
                or not c["marketing_consent"]
                or c["unsubscribed_at"]
                or c["email_bounced_at"]
                or not c["email"]
            ):
                db.execute(
                    "UPDATE sequence_enrollments SET status='stopped',stop_reason='Contact unavailable or no longer eligible for email' WHERE id=?",
                    (enrollment["id"],),
                )
                db.commit()
                continue
            # Any reply logged after enrollment conservatively stops the whole sequence.
            if one(
                "SELECT id FROM engagements WHERE workspace_id=? AND contact_id=? AND kind='email' AND body LIKE 'Received from %' AND occurred_at>=?",
                ws(),
                c["id"],
                enrollment["created_at"],
            ):
                stop_for_contact(c["id"], "Reply received")
                db.commit()
                continue
            steps = json.loads(enrollment["steps"])
            step = steps[enrollment["position"]]
            if step["kind"] == "email":
                deliver(enrollment, c, step)
            else:
                db.insert(
                    "activities",
                    workspace_id=ws(),
                    contact_id=c["id"],
                    company_id=c["company_id"],
                    kind="Task",
                    subject=step["subject"],
                    owner=enrollment["owner"],
                    due_at=now().isoformat(timespec="minutes"),
                    done=0,
                )
            log_event("Follow-up sequence", step["subject"], contact_id=c["id"], company_id=c["company_id"])
            position = enrollment["position"] + 1
            status = "done" if position == len(steps) else "active"
            due = (now() + timedelta(days=steps[position]["days"] if position < len(steps) else 0)).isoformat(
                timespec="seconds"
            )
            db.execute(
                "UPDATE sequence_enrollments SET position=?,status=?,due_at=? WHERE id=? AND status='sending'",
                (position, status, due, enrollment["id"]),
            )
            db.commit()
            total += 1
        except Exception:
            db.rollback()
            current_app.logger.exception("Sequence delivery %s needs review", enrollment["id"])
            db.execute(
                "UPDATE sequence_enrollments SET status='failed',stop_reason='Delivery needs review; automatic retry disabled to prevent duplicate email' WHERE id=?",
                (enrollment["id"],),
            )
            db.commit()
        finally:
            g.pop("public_workspace", None)
            g.pop("workspace", None)
    return total


def register(app):
    @app.route("/sequences", methods=["GET", "POST"])
    def sequences_page():
        auth.admin_required()
        if request.method == "POST":
            name = request.form.get("name", "").strip()[:80]
            steps = []
            for i in range(6):
                kind = request.form.get(f"kind_{i}", "")
                if not kind:
                    continue
                days = request.form.get(f"days_{i}", "0")
                subject = request.form.get(f"subject_{i}", "").strip()[:200]
                body = request.form.get(f"body_{i}", "").strip()[:20000]
                if (
                    kind not in ("task", "email")
                    or not days.isdigit()
                    or int(days) > 90
                    or not subject
                    or (kind == "email" and not body)
                ):
                    abort(422)
                steps.append(dict(kind=kind, days=int(days), subject=subject, body=body))
            if not name or not steps:
                abort(422)
            get_db().insert(
                "sequence_plans",
                workspace_id=ws(),
                name=name,
                steps=json.dumps(steps),
                created_at=now().isoformat(),
            )
            get_db().commit()
            flash("Sequence saved. Enroll opted-in contacts below.", "ok")
            return redirect(url_for("sequences_page"))
        return render_template(
            "sequences_page.html",
            plans=rows("SELECT * FROM sequence_plans WHERE workspace_id=? ORDER BY id DESC", ws()),
            contacts=rows(
                "SELECT * FROM contacts WHERE workspace_id=? AND marketing_consent=1 AND unsubscribed_at IS NULL AND email_bounced_at IS NULL ORDER BY first_name LIMIT 500",
                ws(),
            ),
            enrollments=rows(
                "SELECT e.*,p.name,c.first_name,c.last_name FROM sequence_enrollments e JOIN sequence_plans p ON p.id=e.plan_id JOIN contacts c ON c.id=e.contact_id WHERE e.workspace_id=? ORDER BY e.id DESC LIMIT 100",
                ws(),
            ),
        )

    @app.post("/sequences/enroll")
    def sequence_enroll():
        auth.admin_required()
        pid = request.form.get("plan_id")
        cid = request.form.get("contact_id")
        p = one("SELECT * FROM sequence_plans WHERE id=? AND workspace_id=?", pid, ws())
        c = one("SELECT * FROM contacts WHERE id=? AND workspace_id=?", cid, ws())
        if not p or not c:
            abort(404)
        if not c["marketing_consent"] or c["unsubscribed_at"] or c["email_bounced_at"] or not c["email"]:
            abort(422)
        if one("SELECT id FROM sequence_enrollments WHERE plan_id=? AND contact_id=?", pid, cid):
            abort(409, "This contact was already enrolled in this sequence.")
        steps = json.loads(p["steps"])
        if any(s["kind"] == "email" for s in steps):
            reply = workspace()["reply_to"] or ""
            if not one(
                "SELECT id FROM connections WHERE workspace_id=? AND lower(account)=? AND provider IN ('google','microsoft')",
                ws(),
                reply.lower(),
            ):
                abort(
                    422,
                    "Connect the business reply-to mailbox before enrolling contacts in an email sequence.",
                )
        get_db().insert(
            "sequence_enrollments",
            workspace_id=ws(),
            plan_id=p["id"],
            contact_id=c["id"],
            owner=c["owner"] or g.user["name"],
            steps=p["steps"],
            position=0,
            status="active",
            created_at=now().isoformat(timespec="seconds"),
            due_at=(now() + timedelta(days=steps[0]["days"])).isoformat(timespec="seconds"),
        )
        get_db().commit()
        return redirect(url_for("sequences_page"))

    @app.post("/sequences/<int:enrollment_id>/stop")
    def sequence_stop(enrollment_id):
        auth.admin_required()
        if not one("SELECT id FROM sequence_enrollments WHERE id=? AND workspace_id=?", enrollment_id, ws()):
            abort(404)
        get_db().execute(
            "UPDATE sequence_enrollments SET status='stopped',stop_reason='Stopped by administrator' WHERE id=? AND workspace_id=?",
            (enrollment_id, ws()),
        )
        get_db().commit()
        return redirect(url_for("sequences_page"))

    @app.route("/sequence/unsubscribe/<token>", methods=["GET", "POST"])
    def sequence_unsubscribe(token):
        try:
            wid, cid = signer().loads(token)
        except (BadSignature, ValueError, TypeError):
            abort(404)
        if not one("SELECT id FROM contacts WHERE id=? AND workspace_id=?", cid, wid):
            abort(404)
        g.public_workspace = wid
        if request.method == "POST":
            get_db().execute(
                "UPDATE contacts SET unsubscribed_at=? WHERE id=? AND workspace_id=?",
                (now().isoformat(), cid, wid),
            )
            stop_for_contact(cid, "Unsubscribed")
            get_db().commit()
            return render_template("sequence_unsubscribe.html", done=True)
        return render_template("sequence_unsubscribe.html", done=False)
