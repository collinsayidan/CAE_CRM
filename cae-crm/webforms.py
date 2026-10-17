"""Web forms: build a form, share its link or embed it on a website, and every submission becomes a contact
(matched by email) with a follow-up task. Marketing consent is opt-in and recorded with its date, as PECR requires."""

import json
import secrets
from datetime import datetime, timedelta, timezone

from flask import abort, current_app, flash, g, redirect, render_template, request, url_for
from itsdangerous import BadSignature, URLSafeTimedSerializer

import auth
import ukfmt
from core import (advance_lifecycle, get_or_404, log_event, now, one, owner_names, rows, today, workspace, ws)
from db import LIFECYCLE_STAGES, get_db
from quotes import client_ip

# Optional fields a form can ask for, besides name and email which every form has.
FIELDS = [("phone", "Phone"), ("company", "Company"), ("job_title", "Job title"), ("message", "Message")]
FIELD_MODES = ("off", "optional", "required")
DEFAULT_FIELDS = {"phone": "optional", "company": "optional", "job_title": "off", "message": "required"}
FORM_STAGES = ["Subscriber", "Lead", "Marketing qualified lead", "Sales qualified lead"]
DEFAULT_CONSENT = "Keep me updated with news and offers by email. You can unsubscribe at any time."
MIN_SECONDS = 3  # people take longer than this to fill in a form; most bots don't
MAX_PER_IP = 5  # submissions from one address in RATE_WINDOW
RATE_WINDOW = timedelta(minutes=10)


def form_fields(form):
    try:
        saved = json.loads(form["fields"] or "{}")
    except ValueError:
        saved = {}
    return {key: saved.get(key) if saved.get(key) in FIELD_MODES else DEFAULT_FIELDS[key] for key, _ in FIELDS}


def signer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="cae-web-form")


def read_settings(f):
    errors = {}
    data = dict(name=f.get("name", "").strip()[:80], heading=f.get("heading", "").strip()[:120],
                intro=f.get("intro", "").strip()[:600], button_label=f.get("button_label", "").strip()[:40] or "Send",
                thank_you=f.get("thank_you", "").strip()[:600] or "Thanks, we've got your message and will be in touch soon.",
                consent_text=f.get("consent_text", "").strip()[:300] or DEFAULT_CONSENT,
                privacy_url=f.get("privacy_url", "").strip()[:300],
                ask_consent=int(f.get("ask_consent") == "on"), follow_up_task=int(f.get("follow_up_task") == "on"),
                active=int(f.get("active") == "on"))
    if not data["name"]:
        errors["name"] = "Give the form a name, like Website enquiries."
    data["heading"] = data["heading"] or data["name"]
    if data["privacy_url"] and not data["privacy_url"].startswith(("https://", "http://")):
        errors["privacy_url"] = "Enter a full web address starting with https://"
    data["lifecycle_stage"] = f.get("lifecycle_stage") if f.get("lifecycle_stage") in FORM_STAGES else "Lead"
    data["owner"] = f.get("owner") if f.get("owner") in owner_names() else g.user["name"]
    data["fields"] = json.dumps({key: f.get(f"field_{key}") if f.get(f"field_{key}") in FIELD_MODES else "off"
                                 for key, _ in FIELDS})
    return data, errors


def next_working_morning(start):
    d = start + timedelta(days=1)
    while not ukfmt.is_working_day(d):
        d += timedelta(days=1)
    return datetime.combine(d, datetime.min.time()).replace(hour=10)


def public_form_or_404(token):
    form = one("SELECT * FROM web_forms WHERE token=?", token) if token and len(token) < 80 else None
    if form is None:
        abort(404)
    g.public_workspace = form["workspace_id"]
    return form


def register(app):

    @app.route("/forms")
    def forms():
        data = rows("SELECT f.*, (SELECT COUNT(*) FROM form_submissions s WHERE s.form_id=f.id) AS submissions, "
                    "(SELECT MAX(created_at) FROM form_submissions s WHERE s.form_id=f.id) AS last_at "
                    "FROM web_forms f WHERE f.workspace_id=? ORDER BY f.name", ws())
        return render_template("forms.html", forms=data)

    @app.post("/forms")
    def create_form():
        auth.admin_required()
        name = request.form.get("name", "").strip()[:80] or "Website enquiries"
        db = get_db()
        form_id = db.insert("web_forms", workspace_id=ws(), name=name, token=secrets.token_urlsafe(16),
                            heading="Get in touch", intro="Tell us a little about what you need and we'll reply "
                            "within one working day.", fields=json.dumps(DEFAULT_FIELDS), button_label="Send",
                            thank_you="Thanks, we've got your message and will be in touch within one working day.",
                            lifecycle_stage="Lead", owner=g.user["name"], ask_consent=1, consent_text=DEFAULT_CONSENT,
                            privacy_url="", follow_up_task=1, active=1, created_at=today().isoformat())
        db.commit()
        flash(f"Form created: {name}. Adjust it below, then share the link or embed it on your website.", "ok")
        return redirect(url_for("web_form", form_id=form_id))

    @app.route("/forms/<int:form_id>", methods=["GET", "POST"])
    def web_form(form_id):
        form = get_or_404("web_forms", form_id)
        errors, values = {}, form
        if request.method == "POST":
            auth.admin_required()
            data, errors = read_settings(request.form)
            if not errors:
                db = get_db()
                db.execute(f"UPDATE web_forms SET {', '.join(f'{k}=?' for k in data)} WHERE id=? AND workspace_id=?",
                           (*data.values(), form_id, ws()))
                db.commit()
                flash("Form saved. Changes show on your website straight away.", "ok")
                return redirect(url_for("web_form", form_id=form_id))
            values = request.form
        submissions = rows("SELECT s.id, s.created_at, s.data, s.contact_id, c.first_name, c.last_name FROM form_submissions s "
                           "LEFT JOIN contacts c ON c.id=s.contact_id WHERE s.form_id=? AND s.workspace_id=? "
                           "ORDER BY s.id DESC LIMIT 25", form_id, ws())
        parsed = [(s, json.loads(s["data"])) for s in submissions]
        public_url = url_for("public_form", token=form["token"], _external=True)
        modes = ({k: request.form.get(f"field_{k}", "off") for k, _ in FIELDS} if errors else form_fields(form))
        return render_template("form.html", form=form, values=values, errors=errors, fields=FIELDS, modes=modes,
                               field_modes=FIELD_MODES, stages=FORM_STAGES, owners=owner_names(), submissions=parsed, public_url=public_url,
                               total=one("SELECT COUNT(*) FROM form_submissions WHERE form_id=?", form_id)[0]), \
            (422 if errors else 200)

    @app.post("/forms/<int:form_id>/delete")
    def delete_form(form_id):
        auth.admin_required()
        form = get_or_404("web_forms", form_id)
        db = get_db()
        db.execute("DELETE FROM web_forms WHERE id=? AND workspace_id=?", (form_id, ws()))
        db.commit()
        flash(f"Form deleted: {form['name']}. Contacts it created are kept.", "ok")
        return redirect(url_for("forms"))

    # --- What visitors see ------------------------------------------------------

    @app.route("/f/<token>", methods=["GET", "POST"])
    def public_form(token):
        form = public_form_or_404(token)
        fields = form_fields(form)
        embed = request.args.get("embed") == "1"
        errors, values, done = {}, {}, False
        if not form["active"]:
            return render_template("public/form.html", form=form, fields=fields, closed=True, embed=embed, values={},
                                   errors={}, business=workspace()), 410
        if request.method == "POST":
            values = request.form
            errors = check_submission(form, fields, values)
            if not errors:
                save_submission(form, fields, values)
                done = True
        return render_template("public/form.html", form=form, fields=fields, values=values, errors=errors, done=done,
                               embed=embed, labels=dict(FIELDS), stamp=signer().dumps(form["id"]),
                               business=workspace()), (422 if errors else 200)

    def check_submission(form, fields, f):
        errors = {}
        try:
            form_id, issued = signer().loads(f.get("stamp", ""), max_age=86400, return_timestamp=True)
            too_fast = (datetime.now(timezone.utc) - issued).total_seconds() < current_app.config.get(
                "FORM_MIN_SECONDS", MIN_SECONDS)
            suspicious = too_fast or form_id != form["id"]
        except BadSignature:  # tampered with, or over a day old
            suspicious = True
        if f.get("website") or suspicious:
            # A bot filled the hidden field, skipped the page, or replayed an old one. Say little.
            errors["form"] = "Sorry, we couldn't send that. Please wait a moment and try again."
            return errors
        since = (now() - RATE_WINDOW).isoformat(timespec="minutes")
        if one("SELECT COUNT(*) FROM form_submissions WHERE workspace_id=? AND ip=? AND created_at >= ?",
               form["workspace_id"], client_ip(), since)[0] >= MAX_PER_IP:
            errors["form"] = "We've had several messages from you just now. Please try again in a few minutes."
            return errors
        if not f.get("first_name", "").strip() or not f.get("last_name", "").strip():
            errors["name"] = "Enter your first and last name."
        if not auth.valid_email(f.get("email", "").strip().lower()):
            errors["email"] = "Enter an email address, like name@example.co.uk."
        for key, label in FIELDS:
            if fields[key] == "required" and not f.get(key, "").strip():
                errors[key] = f"Enter your {label.lower()}."
        if fields["phone"] != "off" and f.get("phone", "").strip() and ukfmt.normalise_phone(f.get("phone")) is None:
            errors["phone"] = "Enter a UK phone number, like 0131 496 0000 or 07700 900123."
        if len(f.get("message", "")) > 3000:
            errors["message"] = "Keep your message under 3,000 characters."
        return errors

    def save_submission(form, fields, f):
        db = get_db()
        t = today()
        first, last = f["first_name"].strip()[:60], f["last_name"].strip()[:60]
        email = f["email"].strip().lower()[:200]
        phone = ukfmt.normalise_phone(f.get("phone")) if fields["phone"] != "off" else ""
        job = f.get("job_title", "").strip()[:80] if fields["job_title"] != "off" else ""
        company_name = f.get("company", "").strip()[:120] if fields["company"] != "off" else ""
        message = f.get("message", "").strip() if fields["message"] != "off" else ""
        consent = bool(form["ask_consent"] and f.get("marketing_consent") == "on")
        company_id = None
        if company_name:
            found = one("SELECT id FROM companies WHERE workspace_id=? AND lower(name)=lower(?)", ws(), company_name)
            company_id = found["id"] if found else db.insert(
                "companies", workspace_id=ws(), name=company_name, owner=form["owner"], created_at=t.isoformat())
        contact = one("SELECT * FROM contacts WHERE workspace_id=? AND email=?", ws(), email)
        if contact:
            contact_id = contact["id"]
            db.execute("UPDATE contacts SET phone=COALESCE(NULLIF(phone, ''), ?), role=COALESCE(NULLIF(role, ''), ?), "
                       "company_id=COALESCE(company_id, ?) WHERE id=?", (phone or "", job, company_id, contact_id))
            if consent and not contact["marketing_consent"]:
                db.execute("UPDATE contacts SET marketing_consent=1, consent_date=? WHERE id=?", (t.isoformat(), contact_id))
            if form["lifecycle_stage"] in LIFECYCLE_STAGES:
                advance_lifecycle(contact_id, form["lifecycle_stage"], f"Submitted the form {form['name']}")
        else:
            # Replying to someone who asked us to is a legitimate interest; marketing needs their separate opt-in.
            contact_id = db.insert("contacts", workspace_id=ws(), company_id=company_id, first_name=first, last_name=last,
                                   role=job, email=email, phone=phone or "", lawful_basis="Legitimate interests",
                                   marketing_consent=int(consent), consent_date=t.isoformat() if consent else None,
                                   lifecycle_stage=form["lifecycle_stage"], lead_status="New", owner=form["owner"],
                                   created_at=t.isoformat())
        record = {"first_name": first, "last_name": last, "email": email, "phone": phone, "company": company_name,
                  "job_title": job, "message": message, "marketing_consent": consent,
                  "consent_wording": form["consent_text"] if consent else None,
                  "page": (request.referrer or "")[:300]}
        db.insert("form_submissions", workspace_id=ws(), form_id=form["id"], contact_id=contact_id,
                  data=json.dumps(record), ip=client_ip(), created_at=now().isoformat(timespec="minutes"))
        contact_company = one("SELECT company_id FROM contacts WHERE id=?", contact_id)["company_id"]
        body = message or "No message."
        if consent:
            body += f"\n\nOpted in to marketing emails: \"{form['consent_text']}\""
        log_event(f"Submitted the form: {form['name']}", body, contact_id=contact_id, company_id=contact_company)
        if form["follow_up_task"]:
            db.insert("activities", workspace_id=ws(), company_id=contact_company, contact_id=contact_id, kind="Email",
                      subject=f"Reply to {first} {last} ({form['name']})", owner=form["owner"],
                      due_at=next_working_morning(t).isoformat(timespec="minutes"), done=0)
        db.commit()
