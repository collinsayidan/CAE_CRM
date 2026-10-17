"""Custom fields: a business adds its own fields (text, number, date, dropdown, yes/no) to contacts, companies, deals or
tickets. Values live in each record's `custom` column as JSON, keyed by field id, so removing a field never loses data
from the record itself. They show in the record's About panel and are edited in its Edit window."""

import json
from datetime import date

from flask import flash, g, redirect, render_template, request, session, url_for

import auth
from core import now, rows, ws
from db import get_db

OBJECTS = {"contacts": "Contacts", "companies": "Companies", "deals": "Deals", "tickets": "Tickets"}
TYPES = {"text": "Text", "number": "Number", "date": "Date", "choice": "Dropdown", "yes_no": "Yes or no"}
# Edit pages that also save custom fields: endpoint -> (table, URL argument).
EDITS = {"edit_contact": ("contacts", "contact_id"), "edit_company": ("companies", "company_id"),
         "edit_deal": ("deals", "deal_id"), "edit_ticket": ("tickets", "ticket_id")}
MAX_FIELDS = 30


def definitions(obj):
    key = f"fields_{obj}"
    if key not in g:
        found = rows("SELECT * FROM custom_fields WHERE workspace_id=? AND object=? ORDER BY position, id", ws(), obj)
        setattr(g, key, [dict(f, options=json.loads(f["options"] or "[]")) for f in found])
    return getattr(g, key)


def values(record):
    try:
        return json.loads(record["custom"] or "{}")
    except (ValueError, KeyError, TypeError):
        return {}


def display(field, value):
    if value in (None, ""):
        return None
    if field["field_type"] == "yes_no":
        return "Yes" if value else "No"
    if field["field_type"] == "date":
        try:
            return date.fromisoformat(value).strftime("%d/%m/%Y")
        except ValueError:
            return value
    return value


def parse(field, raw):
    """(value, problem) from a form value."""
    raw = (raw or "").strip()
    kind = field["field_type"]
    if kind == "yes_no":
        return raw == "on", None
    if not raw:
        return None, None
    if kind == "number":
        try:
            number = float(raw.replace(",", "").replace("£", ""))
        except ValueError:
            return None, f"{field['label']} must be a number."
        return int(number) if number.is_integer() else number, None
    if kind == "date":
        try:
            return date.fromisoformat(raw).isoformat(), None
        except ValueError:
            return None, f"{field['label']} must be a date."
    if kind == "choice":
        return (raw, None) if raw in field["options"] else (None, f"Choose one of the options for {field['label']}.")
    return raw[:500], None


def register(app):
    app.add_template_global(definitions, "custom_fields")
    app.add_template_global(values, "custom_values")
    app.add_template_global(display, "custom_display")

    @app.after_request
    def save_custom(response):
        """After a record is edited successfully, save its custom fields from the same form."""
        target = EDITS.get(request.endpoint)
        if (not target or request.method != "POST" or response.status_code >= 400 or not g.get("user")
                or any(c == "error" for c, _ in session.get("_flashes", []))):
            return response
        table, arg = target
        fields = definitions(table)
        if not fields or request.form.get("cf_present") != "1":  # only the full Edit window carries the fields
            return response
        record_id = request.view_args[arg]
        db = get_db()
        row = db.execute(f"SELECT custom FROM {table} WHERE id=? AND workspace_id=?", (record_id, ws())).fetchone()
        if row is None:
            return response
        current = values(row)
        problems = []
        for f in fields:
            value, problem = parse(f, request.form.get(f"cf_{f['id']}"))
            if problem:
                problems.append(problem)
            else:
                current[str(f["id"])] = value
        db.execute(f"UPDATE {table} SET custom=? WHERE id=? AND workspace_id=?", (json.dumps(current), record_id, ws()))
        db.commit()
        if problems:
            flash("Saved, apart from: " + " ".join(problems), "error")
        return response

    @app.route("/custom-fields", methods=["GET", "POST"])
    def custom_fields_page():
        auth.admin_required()
        db = get_db()
        if request.method == "POST":
            f = request.form
            obj, label, kind = f.get("object"), f.get("label", "").strip()[:60], f.get("field_type")
            options = [o.strip()[:60] for o in f.get("options", "").split(",") if o.strip()]
            count = db.execute("SELECT COUNT(*) FROM custom_fields WHERE workspace_id=?", (ws(),)).fetchone()[0]
            if obj not in OBJECTS or kind not in TYPES or not label:
                flash("Field not added. Give it a name, and choose where it goes and what kind it is.", "error")
            elif kind == "choice" and len(options) < 2:
                flash("Field not added. A dropdown needs at least two options, separated by commas.", "error")
            elif count >= MAX_FIELDS:
                flash(f"Field not added. A workspace can have up to {MAX_FIELDS} custom fields.", "error")
            else:
                position = db.execute("SELECT COUNT(*) FROM custom_fields WHERE workspace_id=? AND object=?",
                                      (ws(), obj)).fetchone()[0]
                db.insert("custom_fields", workspace_id=ws(), object=obj, label=label, field_type=kind,
                          options=json.dumps(options if kind == "choice" else []), position=position,
                          created_at=now().isoformat(timespec="minutes"))
                db.commit()
                flash(f"Added {label} to {OBJECTS[obj].lower()}.", "ok")
            return redirect(url_for("custom_fields_page"))
        grouped = {obj: definitions(obj) for obj in OBJECTS}
        return render_template("custom_fields.html", grouped=grouped, objects=OBJECTS, types=TYPES)

    @app.post("/custom-fields/<int:field_id>/delete")
    def delete_custom_field(field_id):
        auth.admin_required()
        db = get_db()
        db.execute("DELETE FROM custom_fields WHERE id=? AND workspace_id=?", (field_id, ws()))
        db.commit()
        flash("Field removed. Values already entered are kept in each record but no longer shown.", "ok")
        return redirect(url_for("custom_fields_page"))
