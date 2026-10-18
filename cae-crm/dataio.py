"""CSV import and export, and saved list views."""

import csv
import io

from flask import Response, abort, flash, g, redirect, render_template, request, url_for

import auth
import ukfmt
from core import back, get_or_404, log_event, one, owner_names, rows, today, ws
from crm import list_records, normalise_query
from db import LAWFUL_BASES, LEAD_STATUSES, LIFECYCLE_STAGES, get_db

MAX_ROWS = 5000
EXPORT_COLUMNS = {
    "contacts": [("First name", "first_name"), ("Last name", "last_name"), ("Email", "email"), ("Phone", "phone"),
                 ("Job title", "role"), ("Company", "company"), ("Lifecycle stage", "lifecycle_stage"),
                 ("Lead status", "lead_status"), ("Owner", "owner"), ("Lawful basis", "lawful_basis"),
                 ("Marketing consent", "marketing_consent"), ("Consent date", "consent_date"), ("Created", "created_at")],
    "companies": [("Name", "name"), ("Companies House number", "company_no"), ("VAT number", "vat_no"),
                  ("Industry", "industry"), ("Address", "address"), ("Town or city", "city"), ("Postcode", "postcode"),
                  ("Region", "region"), ("Website", "website"), ("Phone", "phone"), ("Owner", "owner"),
                  ("Open pipeline (£)", "pipeline"), ("Lifetime revenue (£)", "lifetime")],
    "deals": [("Deal", "title"), ("Company", "company"), ("Stage", "stage"), ("Amount (£)", "value"),
              ("Probability %", "probability"), ("Close date", "close_date"), ("Owner", "owner"), ("Source", "source"),
              ("Created", "created_at"), ("Closed", "closed_at")],
    "tickets": [("Ticket", "id"), ("Subject", "subject"), ("Status", "status"), ("Priority", "priority"),
                ("Category", "category"), ("Company", "company"), ("Contact", "contact"), ("Owner", "owner"),
                ("Opened", "created_at"), ("First response due", "first_response_due"),
                ("First responded", "first_responded_at"), ("Resolution due", "resolution_due"), ("Closed", "closed_at")],
}
MONEY_FIELDS = {"value", "pipeline", "lifetime"}
# Fields an import can fill, with the column headings that usually hold them.
IMPORT_FIELDS = {
    "contacts": [("first_name", "First name", ["first name", "firstname", "forename", "given name"]),
                 ("last_name", "Last name", ["last name", "lastname", "surname", "family name"]),
                 ("full_name", "Full name (split into first and last)", ["name", "full name", "contact", "contact name"]),
                 ("email", "Email", ["email", "email address", "e-mail"]),
                 ("phone", "Phone", ["phone", "telephone", "mobile", "phone number", "tel"]),
                 ("role", "Job title", ["job title", "title", "role", "position"]),
                 ("company", "Company name", ["company", "company name", "organisation", "organization", "account"]),
                 ("lifecycle_stage", "Lifecycle stage", ["lifecycle stage", "lifecycle", "stage"]),
                 ("lead_status", "Lead status", ["lead status", "status"]),
                 ("owner", "Owner", ["owner", "contact owner", "account manager"]),
                 ("marketing_consent", "Marketing consent (yes/no)", ["marketing consent", "consent", "opted in", "opt in"])],
    "companies": [("name", "Company name", ["name", "company", "company name", "organisation", "organization"]),
                  ("company_no", "Companies House number", ["company number", "companies house number", "company no", "crn"]),
                  ("vat_no", "VAT number", ["vat", "vat number", "vat no", "vat registration"]),
                  ("industry", "Industry", ["industry", "sector"]),
                  ("address", "Address", ["address", "address line 1", "street"]),
                  ("city", "Town or city", ["city", "town", "town or city"]),
                  ("postcode", "Postcode", ["postcode", "post code", "postal code", "zip"]),
                  ("region", "Region", ["region", "county"]),
                  ("website", "Website", ["website", "domain", "url", "web"]),
                  ("phone", "Phone", ["phone", "telephone", "tel"]),
                  ("owner", "Owner", ["owner", "company owner", "account manager"])],
}
YES = {"yes", "y", "true", "1", "opted in", "opt in", "consented"}


def csv_safe(value):
    """Stop spreadsheet apps treating a cell as a formula (CSV injection)."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def guess(field_synonyms, header):
    h = header.strip().lower().replace("_", " ")
    for field, _, synonyms in field_synonyms:
        if h in synonyms or h == field.replace("_", " "):
            return field
    return ""


def read_csv(raw):
    for encoding in ("utf-8-sig", "cp1252"):  # Excel in the UK often saves as Windows-1252
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def import_contacts(data, mapping, options):
    db = get_db()
    created = updated = 0
    errors = []
    owners = owner_names()
    company_cache = {r["name"].lower(): r["id"] for r in rows("SELECT id, name FROM companies WHERE workspace_id=?", ws())}
    for n, row in enumerate(data, start=2):  # row 1 is the headings
        v = {field: (row.get(col) or "").strip() for col, field in mapping.items() if field}
        first, last = v.get("first_name", ""), v.get("last_name", "")
        if v.get("full_name") and not (first or last):
            first, _, last = v["full_name"].partition(" ")
        if not first or not last:
            errors.append((n, "Needs a first and last name."))
            continue
        email = v.get("email", "").lower()
        if email and not auth.valid_email(email):
            errors.append((n, f"“{email}” isn't a valid email address."))
            continue
        phone = ukfmt.normalise_phone(v.get("phone"))
        if phone is None:
            phone = v.get("phone", "")  # keep it as written rather than lose it
        company_id = None
        if v.get("company"):
            key = v["company"].lower()
            if key not in company_cache:
                company_cache[key] = db.insert("companies", workspace_id=ws(), name=v["company"], company_no="", vat_no="",
                                               industry="", address="", city="", postcode="", region="", website="",
                                               phone="", owner=g.user["name"], created_at=today().isoformat())
            company_id = company_cache[key]
        stage = next((s for s in LIFECYCLE_STAGES if s.lower() == v.get("lifecycle_stage", "").lower()), options["lifecycle"])
        status = next((s for s in LEAD_STATUSES if s.lower() == v.get("lead_status", "").lower()), "New")
        owner = v.get("owner") if v.get("owner") in owners else g.user["name"]
        consent = int(v.get("marketing_consent", "").lower() in YES)
        existing = one("SELECT id FROM contacts WHERE workspace_id=? AND email=?", ws(), email) if email else None
        if existing:
            if options["duplicates"] != "update":
                errors.append((n, f"{email} is already in your contacts, so it was skipped."))
                continue
            db.execute("UPDATE contacts SET first_name=?, last_name=?, phone=COALESCE(NULLIF(?, ''), phone),"
                       " role=COALESCE(NULLIF(?, ''), role), company_id=COALESCE(?, company_id) WHERE id=?",
                       (first, last, phone, v.get("role", ""), company_id, existing["id"]))
            updated += 1
            continue
        contact_id = db.insert("contacts", workspace_id=ws(), company_id=company_id, first_name=first, last_name=last,
                               role=v.get("role", ""), email=email, phone=phone, lawful_basis=options["lawful_basis"],
                               marketing_consent=consent, consent_date=today().isoformat() if consent else None,
                               lifecycle_stage=stage, lead_status=status, owner=owner, created_at=today().isoformat())
        log_event("Contact imported", f"From {options['filename']}", contact_id=contact_id, company_id=company_id)
        created += 1
    return created, updated, errors


def import_companies(data, mapping, options):
    db = get_db()
    created = updated = 0
    errors = []
    owners = owner_names()
    for n, row in enumerate(data, start=2):
        v = {field: (row.get(col) or "").strip() for col, field in mapping.items() if field}
        name = v.get("name", "")
        if not name:
            errors.append((n, "Needs a company name."))
            continue
        postcode = ukfmt.normalise_postcode(v.get("postcode")) if v.get("postcode") else ""
        if postcode is None:
            errors.append((n, f"“{v['postcode']}” isn't a valid UK postcode."))
            continue
        company_no = ukfmt.normalise_company_no(v.get("company_no")) or ""
        vat_no = ukfmt.normalise_vat(v.get("vat_no")) or ""
        website = v.get("website", "")
        if website and not website.startswith(("http://", "https://")):
            website = "https://" + website
        values = dict(name=name, company_no=company_no, vat_no=vat_no, industry=v.get("industry", ""),
                      address=v.get("address", ""), city=v.get("city", ""), postcode=postcode, region=v.get("region", ""),
                      website=website, phone=ukfmt.normalise_phone(v.get("phone")) or v.get("phone", ""),
                      owner=v.get("owner") if v.get("owner") in owners else g.user["name"])
        existing = None
        if company_no:
            existing = one("SELECT id FROM companies WHERE workspace_id=? AND company_no=?", ws(), company_no)
        existing = existing or one("SELECT id FROM companies WHERE workspace_id=? AND LOWER(name)=?", ws(), name.lower())
        if existing:
            if options["duplicates"] != "update":
                errors.append((n, f"{name} is already in your companies, so it was skipped."))
                continue
            sets = ", ".join(f"{k}=COALESCE(NULLIF(?, ''), {k})" for k in values)
            db.execute(f"UPDATE companies SET {sets} WHERE id=?", (*values.values(), existing["id"]))
            updated += 1
            continue
        company_id = db.insert("companies", workspace_id=ws(), **values, created_at=today().isoformat())
        log_event("Company imported", f"From {options['filename']}", company_id=company_id)
        created += 1
    return created, updated, errors


def register(app):

    @app.route("/export/<obj>")
    def export(obj):
        auth.admin_required()  # a bulk copy of personal data
        if obj not in EXPORT_COLUMNS:
            abort(404)
        data, _, _, _ = list_records(obj, request.args, paginate=False)
        out = io.StringIO()
        writer = csv.writer(out)
        from fields import definitions, display
        extra = definitions(obj) if obj in ("contacts", "companies", "deals", "tickets") else []
        custom = {r["id"]: r["custom"] for r in rows(f"SELECT id, custom FROM {obj} WHERE workspace_id=?", ws())} if extra else {}
        import tags
        tagged = {"contacts": "contact", "companies": "company"}.get(obj)
        tag_map = tags.tags_for(tagged, [r["id"] for r in data]) if tagged else {}
        writer.writerow([label for label, _ in EXPORT_COLUMNS[obj]] + [f["label"] for f in extra]
                        + (["Tags"] if tagged else []))
        for r in data:
            line = []
            for _, key in EXPORT_COLUMNS[obj]:
                value = r[key]
                if key in MONEY_FIELDS:
                    value = f"{(value or 0) / 100:.2f}"
                elif key == "marketing_consent":
                    value = "Yes" if value else "No"
                line.append(csv_safe(value))
            if extra:
                import json
                saved = json.loads(custom.get(r["id"]) or "{}")
                line += [csv_safe(display(f, saved.get(str(f["id"]))) or "") for f in extra]
            if tagged:
                line.append(csv_safe(", ".join(tag_map.get(r["id"], []))))
            writer.writerow(line)
        filename = f"cae-{obj}-{today().isoformat()}.csv"
        return Response("﻿" + out.getvalue(), mimetype="text/csv",  # BOM so Excel reads £ and accents
                        headers={"Content-Disposition": f"attachment; filename={filename}"})

    @app.route("/import", methods=["GET", "POST"])
    def imports():
        auth.admin_required()
        if request.method == "POST":
            obj = request.form.get("object")
            upload = request.files.get("file")
            if obj not in IMPORT_FIELDS or not upload or not upload.filename:
                flash("Choose what you're importing and a CSV file.", "error")
                return redirect(url_for("imports"))
            text = read_csv(upload.read())
            if text is None:
                flash("That file couldn't be read. Save it as CSV (UTF-8) from your spreadsheet and try again.", "error")
                return redirect(url_for("imports"))
            data = list(csv.reader(io.StringIO(text)))
            if len(data) < 2 or not any(data[0]):
                flash("That file has no rows to import. The first row should be column headings.", "error")
                return redirect(url_for("imports"))
            if len(data) - 1 > MAX_ROWS:
                flash(f"That file has {len(data) - 1:,} rows. Import up to {MAX_ROWS:,} at a time.", "error")
                return redirect(url_for("imports"))
            db = get_db()
            db.execute("DELETE FROM imports WHERE workspace_id=? AND user_id=?", (ws(), g.user["id"]))
            import_id = db.insert("imports", workspace_id=ws(), user_id=g.user["id"], object=obj,
                                  filename=upload.filename[:120], content=text, created_at=today().isoformat())
            db.commit()
            return redirect(url_for("import_map", import_id=import_id))
        return render_template("import.html", step="upload")

    @app.route("/import/<int:import_id>", methods=["GET", "POST"])
    def import_map(import_id):
        auth.admin_required()
        imp = get_or_404("imports", import_id)
        if imp["user_id"] != g.user["id"]:
            abort(404)
        reader = csv.DictReader(io.StringIO(imp["content"]))
        headers = [h for h in (reader.fieldnames or []) if h is not None]
        data = list(reader)
        fields = IMPORT_FIELDS[imp["object"]]
        if request.method == "POST":
            mapping = {h: request.form.get(f"map_{i}", "") for i, h in enumerate(headers)}
            mapped = set(mapping.values())
            needed = {"contacts": [{"first_name", "last_name"}, {"full_name"}], "companies": [{"name"}]}[imp["object"]]
            if not any(req <= mapped for req in needed):
                flash("Match a column to the name fields first." if imp["object"] == "contacts"
                      else "Match a column to Company name first.", "error")
                return redirect(url_for("import_map", import_id=import_id))
            options = dict(duplicates=request.form.get("duplicates", "skip"), filename=imp["filename"],
                           lawful_basis=request.form.get("lawful_basis") if request.form.get("lawful_basis") in LAWFUL_BASES
                           else "Legitimate interests",
                           lifecycle=request.form.get("lifecycle") if request.form.get("lifecycle") in LIFECYCLE_STAGES else "Lead")
            run = import_contacts if imp["object"] == "contacts" else import_companies
            created, updated, errors = run(data, mapping, options)
            db = get_db()
            db.execute("DELETE FROM imports WHERE id=?", (import_id,))
            db.commit()
            return render_template("import.html", step="done", obj=imp["object"], created=created, updated=updated,
                                   errors=errors, filename=imp["filename"], total=len(data))
        columns = [dict(index=i, header=h, guess=guess(fields, h), samples=[r.get(h, "") for r in data[:3]])
                   for i, h in enumerate(headers)]
        return render_template("import.html", step="map", imp=imp, columns=columns, fields=fields, rows_count=len(data),
                               lawful_bases=LAWFUL_BASES, lifecycle_stages=LIFECYCLE_STAGES)

    @app.post("/views")
    def save_view():
        obj = request.form.get("object")
        name = request.form.get("name", "").strip()[:40]
        query = normalise_query(request.form.get("query", ""))
        if obj not in ("contacts", "companies", "deals", "tickets") or not name or not query:
            flash("Filter the list first, then give the view a name.", "error")
            return back(obj if obj in ("contacts", "companies", "tickets") else "pipeline")
        db = get_db()
        db.insert("saved_views", workspace_id=ws(), user_id=g.user["id"], object=obj, name=name, query=query)
        db.commit()
        flash(f"View saved: {name}.", "ok")
        target = {"deals": url_for("pipeline", view="list"), "tickets": url_for("tickets", view="list")}.get(obj, url_for(obj))
        sep = "&" if "?" in target else "?"
        return redirect(f"{target}{sep}{query}")

    @app.post("/views/<int:view_id>/delete")
    def delete_view(view_id):
        v = get_or_404("saved_views", view_id)
        if v["user_id"] != g.user["id"]:
            abort(404)
        get_db().execute("DELETE FROM saved_views WHERE id=?", (view_id,))
        get_db().commit()
        flash(f"View removed: {v['name']}.", "ok")
        return back("contacts")

