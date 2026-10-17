"""Email campaigns to contacts who opted in. PECR: only contacts with recorded marketing consent receive them, every
email identifies the sender and has a one-click unsubscribe (also in the List-Unsubscribe header, as Gmail and Yahoo
require of bulk senders), and an unsubscribe takes effect at once."""

import json
import re
from datetime import datetime, timezone

from flask import abort, current_app, flash, g, jsonify, redirect, render_template, request, url_for
from itsdangerous import BadSignature, URLSafeSerializer
from markupsafe import Markup, escape

import auth
import mail
from core import get_or_404, log_event, now, one, owner_names, rows, wants_json, workspace, ws
from db import LIFECYCLE_STAGES, get_db

MERGE = re.compile(r"\{\{\s*first_name\s*\}\}")


def audience_of(c):
    try:
        a = json.loads(c["audience"] or "{}")
    except ValueError:
        a = {}
    return {"stages": [s for s in a.get("stages", []) if s in LIFECYCLE_STAGES], "owner": a.get("owner", "")}


def eligible(audience, workspace_id=None):
    """Contacts who may receive marketing: opted in, not unsubscribed, email not bouncing."""
    sql = ("SELECT id, email, first_name FROM contacts WHERE workspace_id=? AND marketing_consent=1 AND email IS NOT NULL "
           "AND email <> '' AND unsubscribed_at IS NULL AND email_bounced_at IS NULL")
    args = [workspace_id or ws()]
    if audience["stages"]:
        sql += f" AND lifecycle_stage IN ({','.join('?' * len(audience['stages']))})"
        args += audience["stages"]
    if audience["owner"]:
        sql += " AND owner=?"
        args.append(audience["owner"])
    return rows(sql + " ORDER BY id", *args)


def body_html(text):
    """Turn the plain-text body into simple, safe HTML: paragraphs, '- ' bullet lists, **bold** and [links](https://…)."""
    blocks = []
    for block in re.split(r"\n\s*\n", (text or "").strip()):
        lines = block.strip().splitlines()
        if lines and all(line.lstrip().startswith("- ") for line in lines):
            items = "".join(f"<li>{inline(line.lstrip()[2:])}</li>" for line in lines)
            blocks.append(f'<ul style="margin:0 0 16px;padding-left:22px">{items}</ul>')
        elif lines:
            blocks.append(f'<p style="margin:0 0 16px">{"<br>".join(inline(line) for line in lines)}</p>')
    return Markup("".join(blocks))


def inline(line):
    out = str(escape(line))
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
                 r'<a href="\2" style="color:#0f766e;font-weight:600">\1</a>', out)
    return out


def personalise(text, first_name):
    return MERGE.sub(first_name or "there", text or "")


def unsubscribe_token(recipient_id):
    return URLSafeSerializer(current_app.config["SECRET_KEY"], salt="cae-unsubscribe").dumps(recipient_id)


def render_email(c, business, first_name, unsubscribe_url):
    """(html, text) for one recipient."""
    body = personalise(c["body"], first_name)
    sender_line = ", ".join(p for p in [business["legal_name"] or business["name"], business["address"], business["city"],
                                        business["postcode"]] if p)
    html = render_template("emails/campaign.html", c=c, subject=personalise(c["subject"], first_name), business=business,
                           body=body_html(body),
                           preheader=personalise(c["preheader"] or "", first_name), sender_line=sender_line,
                           unsubscribe_url=unsubscribe_url)
    text = (f"{body}\n\n--\n{sender_line}\nYou're receiving this because you agreed to hear from "
            f"{business['name']} by email.\nUnsubscribe: {unsubscribe_url}\n")
    return html, text


def stats(campaign_id):
    r = one("SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN status IN ('sent','delivered','bounced') THEN 1 ELSE 0 END) AS sent, "
            "SUM(CASE WHEN delivered_at IS NOT NULL THEN 1 ELSE 0 END) AS delivered, "
            "SUM(CASE WHEN opened_at IS NOT NULL THEN 1 ELSE 0 END) AS opened, "
            "SUM(CASE WHEN clicked_at IS NOT NULL THEN 1 ELSE 0 END) AS clicked, "
            "SUM(CASE WHEN bounced_at IS NOT NULL THEN 1 ELSE 0 END) AS bounced, "
            "SUM(CASE WHEN unsubscribed_at IS NOT NULL THEN 1 ELSE 0 END) AS unsubscribed, "
            "SUM(CASE WHEN status='queued' THEN 1 ELSE 0 END) AS queued, "
            "SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed "
            "FROM campaign_recipients WHERE campaign_id=? AND workspace_id=?", campaign_id, ws())
    return {k: int(r[k] or 0) for k in r.keys()}


def stamp():
    return now().isoformat(timespec="minutes")


def register(app):

    @app.route("/email")
    def campaigns():
        data = rows("SELECT * FROM email_campaigns WHERE workspace_id=? ORDER BY id DESC", ws())
        report = {c["id"]: stats(c["id"]) for c in data if c["status"] != "Draft"}
        reachable = len(eligible({"stages": [], "owner": ""}))
        return render_template("email.html", campaigns=data, report=report, reachable=reachable,
                               configured=mail.configured())

    @app.post("/email")
    def create_campaign():
        db = get_db()
        cid = db.insert("email_campaigns", workspace_id=ws(), name=request.form.get("name", "").strip()[:80] or "Untitled campaign",
                        subject="", preheader="", body="Hi {{first_name}},\n\n", audience=json.dumps({"stages": [], "owner": ""}),
                        status="Draft", created_by=g.user["name"], created_at=stamp())
        db.commit()
        return redirect(url_for("campaign", campaign_id=cid))

    @app.route("/email/<int:campaign_id>", methods=["GET", "POST"])
    def campaign(campaign_id):
        c = get_or_404("email_campaigns", campaign_id)
        errors = {}
        if request.method == "POST":
            if c["status"] != "Draft":
                abort(409)
            f = request.form
            stages = [s for s in f.getlist("stages") if s in LIFECYCLE_STAGES]
            owner = f.get("owner") if f.get("owner") in owner_names() else ""
            values = dict(name=f.get("name", "").strip()[:80] or "Untitled campaign", subject=f.get("subject", "").strip()[:150],
                          preheader=f.get("preheader", "").strip()[:150], body=f.get("body", "")[:20000],
                          audience=json.dumps({"stages": stages, "owner": owner}))
            db = get_db()
            db.execute(f"UPDATE email_campaigns SET {', '.join(f'{k}=?' for k in values)} WHERE id=? AND workspace_id=?",
                       (*values.values(), campaign_id, ws()))
            db.commit()
            if wants_json():
                return jsonify(ok=True, audience=len(eligible(audience_of(dict(values)))))
            flash("Draft saved.", "ok")
            return redirect(url_for("campaign", campaign_id=campaign_id))
        audience = audience_of(c)
        context = dict(c=c, audience=audience, stages=LIFECYCLE_STAGES, owners=owner_names(), configured=mail.configured(),
                       errors=errors, business=workspace())
        if c["status"] == "Draft":
            context["count"] = len(eligible(audience))
        else:
            context["stats"] = stats(campaign_id)
            context["recipients"] = rows("SELECT * FROM campaign_recipients WHERE campaign_id=? AND workspace_id=? "
                                         "ORDER BY id LIMIT 200", campaign_id, ws())
        return render_template("campaign.html", **context)

    @app.get("/email/<int:campaign_id>/preview")
    def campaign_preview(campaign_id):
        c = get_or_404("email_campaigns", campaign_id)
        html, _ = render_email(c, workspace(), g.user["name"].split()[0], "#unsubscribe")
        return html

    @app.post("/email/<int:campaign_id>/test")
    def campaign_test(campaign_id):
        c = get_or_404("email_campaigns", campaign_id)
        if not c["subject"].strip() or not c["body"].strip():
            flash("Add a subject and a message before sending a test.", "error")
            return redirect(url_for("campaign", campaign_id=campaign_id))
        w = workspace()
        html, text = render_email(c, w, g.user["name"].split()[0], url_for("campaigns", _external=True))
        try:
            mail.send(mail.message(g.user["email"], f"[Test] {c['subject']}", html, text, w["name"], w["reply_to"]))
            flash(f"Test sent to {g.user['email']}.", "ok")
        except mail.MailError as e:
            flash(f"Test not sent. {e}", "error")
        return redirect(url_for("campaign", campaign_id=campaign_id))

    @app.post("/email/<int:campaign_id>/start")
    def campaign_start(campaign_id):
        auth.admin_required()
        c = get_or_404("email_campaigns", campaign_id)
        if c["status"] != "Draft":
            return redirect(url_for("campaign", campaign_id=campaign_id))
        problem = None
        if not mail.configured():
            problem = "Email isn't set up yet."
        elif not c["subject"].strip() or not c["body"].strip():
            problem = "Add a subject and a message first."
        people = eligible(audience_of(c))
        if not problem and not people:
            problem = "Nobody in this audience has agreed to marketing emails."
        if problem:
            flash(f"Not sent. {problem}", "error")
            return redirect(url_for("campaign", campaign_id=campaign_id))
        db = get_db()
        for p in people:
            db.insert("campaign_recipients", workspace_id=ws(), campaign_id=campaign_id, contact_id=p["id"],
                      email=p["email"], first_name=p["first_name"], status="queued")
        db.execute("UPDATE email_campaigns SET status='Sending', started_at=?, recipients=? WHERE id=? AND workspace_id=?",
                   (stamp(), len(people), campaign_id, ws()))
        db.commit()
        return redirect(url_for("campaign", campaign_id=campaign_id, deliver=1))

    @app.post("/email/<int:campaign_id>/deliver")
    def campaign_deliver(campaign_id):
        """Send the next batch. The page calls this until nothing is left, so no request runs long on a serverless host."""
        auth.admin_required()
        c = get_or_404("email_campaigns", campaign_id)
        db = get_db()
        if request.form.get("retry") == "1":
            db.execute("UPDATE campaign_recipients SET status='queued', error=NULL WHERE campaign_id=? AND workspace_id=? "
                       "AND status='failed'", (campaign_id, ws()))
            db.execute("UPDATE email_campaigns SET status='Sending' WHERE id=? AND workspace_id=?", (campaign_id, ws()))
            db.commit()
            c = get_or_404("email_campaigns", campaign_id)
        error = None
        if c["status"] == "Sending":
            batch = rows("SELECT * FROM campaign_recipients WHERE campaign_id=? AND workspace_id=? AND status='queued' "
                         "ORDER BY id LIMIT ?", campaign_id, ws(), mail.BATCH_SIZE)
            ids = [r["id"] for r in batch]
            if ids:
                marks = ",".join("?" * len(ids))
                # Claim the batch first, so a double click can't send anyone the same email twice.
                claimed = db.execute(f"UPDATE campaign_recipients SET status='sending' WHERE id IN ({marks}) AND status='queued'",
                                     ids).rowcount
                db.commit()
                if claimed == len(ids):
                    w = workspace()
                    msgs = []
                    for r in batch:
                        link = url_for("unsubscribe", token=unsubscribe_token(r["id"]), _external=True)
                        html, text = render_email(c, w, r["first_name"], link)
                        msgs.append(mail.message(r["email"], personalise(c["subject"], r["first_name"]), html, text, w["name"],
                                                 w["reply_to"], headers={"List-Unsubscribe": f"<{link}>",
                                                                         "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"},
                                                 tags={"campaign": campaign_id}))
                    try:
                        provider_ids = mail.send_batch(msgs)
                        for r, pid in zip(batch, provider_ids):
                            db.execute("UPDATE campaign_recipients SET status='sent', provider_id=?, sent_at=? WHERE id=?",
                                       (pid, stamp(), r["id"]))
                    except mail.MailError as e:
                        error = str(e)
                        db.execute(f"UPDATE campaign_recipients SET status='failed', error=? WHERE id IN ({marks})",
                                   (error[:300], *ids))
                    db.commit()
            remaining = one("SELECT COUNT(*) FROM campaign_recipients WHERE campaign_id=? AND status IN ('queued','sending')",
                            campaign_id)[0]
            if not remaining:
                failed = one("SELECT COUNT(*) FROM campaign_recipients WHERE campaign_id=? AND status='failed'", campaign_id)[0]
                db.execute("UPDATE email_campaigns SET status=?, sent_at=? WHERE id=?",
                           ("Sent" if not failed else "Sending", stamp(), campaign_id))
                db.commit()
        s = stats(campaign_id)
        if wants_json():
            return jsonify(remaining=s["queued"], sent=s["sent"], failed=s["failed"], error=error)
        if error:
            flash(f"Some emails weren't sent. {error}", "error")
        return redirect(url_for("campaign", campaign_id=campaign_id))

    @app.post("/email/<int:campaign_id>/duplicate")
    def campaign_duplicate(campaign_id):
        c = get_or_404("email_campaigns", campaign_id)
        db = get_db()
        new_id = db.insert("email_campaigns", workspace_id=ws(), name=f"Copy of {c['name']}"[:80], subject=c["subject"],
                           preheader=c["preheader"], body=c["body"], audience=c["audience"], status="Draft",
                           created_by=g.user["name"], created_at=stamp())
        db.commit()
        return redirect(url_for("campaign", campaign_id=new_id))

    @app.post("/email/<int:campaign_id>/delete")
    def campaign_delete(campaign_id):
        c = get_or_404("email_campaigns", campaign_id)
        if c["status"] != "Draft":
            flash("Sent campaigns are kept as a record of who was emailed and when.", "error")
            return redirect(url_for("campaign", campaign_id=campaign_id))
        get_db().execute("DELETE FROM email_campaigns WHERE id=? AND workspace_id=?", (campaign_id, ws()))
        get_db().commit()
        flash("Draft deleted.", "ok")
        return redirect(url_for("campaigns"))

    # --- Public: unsubscribe and Resend's delivery reports ------------------------

    @app.route("/u/<token>", methods=["GET", "POST"])
    def unsubscribe(token):
        try:
            recipient_id = URLSafeSerializer(current_app.config["SECRET_KEY"], salt="cae-unsubscribe").loads(token)
        except BadSignature:
            abort(404)
        r = one("SELECT * FROM campaign_recipients WHERE id=?", recipient_id)
        if r is None:
            abort(404)
        g.public_workspace = r["workspace_id"]
        done = bool(r["unsubscribed_at"])
        if request.method == "POST" and not done:
            db = get_db()
            when = stamp()
            db.execute("UPDATE campaign_recipients SET unsubscribed_at=? WHERE id=?", (when, recipient_id))
            if r["contact_id"]:
                db.execute("UPDATE contacts SET marketing_consent=0, unsubscribed_at=? WHERE id=?", (when, r["contact_id"]))
                log_event("Unsubscribed from marketing emails", "Using the link in an email campaign.",
                          contact_id=r["contact_id"])
            db.commit()
            done = True
            if request.form.get("List-Unsubscribe") == "One-Click":
                return "", 204  # a mail app's one-click request wants no page back
        return render_template("public/unsubscribe.html", done=done, business=workspace(), embed=False, email=r["email"])

    @app.post("/webhooks/resend")
    def resend_webhook():
        body = request.get_data()
        if not mail.verify_webhook(body, request.headers, current_app.config.get("RESEND_WEBHOOK_SECRET")):
            abort(401)
        event = json.loads(body or b"{}")
        kind, data = event.get("type", ""), event.get("data") or {}
        r = one("SELECT * FROM campaign_recipients WHERE provider_id=?", data.get("email_id") or "-")
        if r is None:
            return "", 204  # not a campaign email (a quote or a test), nothing to record
        when = (event.get("created_at") or datetime.now(timezone.utc).isoformat())[:16]
        db = get_db()
        column = {"email.delivered": "delivered_at", "email.opened": "opened_at", "email.clicked": "clicked_at",
                  "email.bounced": "bounced_at"}.get(kind)
        if column:
            db.execute(f"UPDATE campaign_recipients SET {column}=COALESCE({column}, ?) WHERE id=?", (when, r["id"]))
        if kind == "email.bounced":
            db.execute("UPDATE campaign_recipients SET status='bounced' WHERE id=?", (r["id"],))
            if r["contact_id"]:
                db.execute("UPDATE contacts SET email_bounced_at=? WHERE id=?", (when, r["contact_id"]))
        if kind == "email.complained" and r["contact_id"]:
            # A spam complaint means they don't want our email: treat it as an unsubscribe.
            db.execute("UPDATE contacts SET marketing_consent=0, unsubscribed_at=? WHERE id=?", (when, r["contact_id"]))
            db.execute("UPDATE campaign_recipients SET unsubscribed_at=COALESCE(unsubscribed_at, ?) WHERE id=?", (when, r["id"]))
        db.commit()
        return "", 204
