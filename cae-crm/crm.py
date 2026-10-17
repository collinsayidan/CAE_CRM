"""Contacts, companies and deal record pages, the activity timeline, list views and bulk actions."""

import json
from datetime import datetime
from urllib.parse import parse_qsl, urlencode

from flask import Response, abort, flash, g, redirect, render_template, request, url_for

import auth
import ukfmt
from core import (OPEN_SQL, advance_lifecycle, back, chosen_owner, get_or_404, log_event, now, one, owned,
                  owner_names, rows, scalar, today, ws)
from db import (ACTIVITY_KINDS, CALL_OUTCOMES, LAWFUL_BASES, LEAD_STATUSES, LIFECYCLE_STAGES, OPEN_STAGES, SOURCES,
                TICKET_STATUSES, get_db)

PAGE_SIZE = 50
ENGAGEMENT_KINDS = ("note", "call", "email", "meeting")

# How each list page can be searched, filtered and sorted. Filter values always travel as parameters.
LISTS = {
    "contacts": dict(
        select="SELECT ct.*, c.name AS company FROM contacts ct LEFT JOIN companies c ON c.id=ct.company_id",
        scope="ct.workspace_id=?",
        search=["LOWER(ct.first_name || ' ' || ct.last_name)", "LOWER(ct.email)", "LOWER(c.name)"],
        filters={"owner": "ct.owner = ?", "lifecycle": "ct.lifecycle_stage = ?", "lead_status": "ct.lead_status = ?",
                 "company": "ct.company_id = ?", "consent": "ct.marketing_consent = ?"},
        sorts={"name": "LOWER(ct.first_name), LOWER(ct.last_name)", "newest": "ct.created_at DESC, ct.id DESC",
               "company": "LOWER(c.name) NULLS LAST", "lifecycle": "ct.lifecycle_stage"},
    ),
    "companies": dict(
        select=(f"SELECT c.*, (SELECT SUM(value) FROM deals WHERE company_id=c.id AND {OPEN_SQL}) AS pipeline,"
                " (SELECT SUM(value) FROM deals WHERE company_id=c.id AND stage='Won') AS lifetime,"
                " (SELECT COUNT(*) FROM contacts WHERE company_id=c.id) AS contacts,"
                " (SELECT COUNT(*) FROM tickets WHERE company_id=c.id AND status <> 'Closed') AS open_tickets"
                " FROM companies c"),
        scope="c.workspace_id=?",
        search=["LOWER(c.name)", "LOWER(c.city)", "LOWER(c.postcode)", "LOWER(c.industry)"],
        filters={"owner": "c.owner = ?", "region": "c.region = ?", "industry": "c.industry = ?"},
        sorts={"value": "lifetime DESC NULLS LAST, c.name", "name": "LOWER(c.name)", "newest": "c.created_at DESC, c.id DESC",
               "pipeline": "pipeline DESC NULLS LAST"},
    ),
    "deals": dict(
        select="SELECT d.*, c.name AS company FROM deals d JOIN companies c ON c.id=d.company_id",
        scope="d.workspace_id=?",
        search=["LOWER(d.title)", "LOWER(c.name)"],
        filters={"owner": "d.owner = ?", "stage": "d.stage = ?", "source": "d.source = ?", "company": "d.company_id = ?"},
        sorts={"close": "d.close_date", "value": "d.value DESC", "newest": "d.created_at DESC, d.id DESC"},
    ),
    "tickets": dict(
        select=("SELECT t.*, c.name AS company, ct.first_name || ' ' || ct.last_name AS contact FROM tickets t"
                " LEFT JOIN companies c ON c.id=t.company_id LEFT JOIN contacts ct ON ct.id=t.contact_id"),
        scope="t.workspace_id=?",
        search=["LOWER(t.subject)", "LOWER(c.name)"],
        filters={"owner": "t.owner = ?", "status": "t.status = ?", "priority": "t.priority = ?", "category": "t.category = ?"},
        sorts={"due": "t.status='Closed', t.resolution_due", "newest": "t.created_at DESC, t.id DESC",
               "priority": "CASE t.priority WHEN 'Urgent' THEN 0 WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END"},
    ),
}
DEFAULT_SORT = {"contacts": "newest", "companies": "value", "deals": "close", "tickets": "due"}


def list_records(obj, args, paginate=True):
    """Rows for a list page from its query-string filters. Returns (rows, total, page, filters)."""
    spec = LISTS[obj]
    where, params = [spec["scope"]], [ws()]
    q = (args.get("q") or "").strip().lower()
    if q:
        where.append("(" + " OR ".join(f"{col} LIKE ?" for col in spec["search"]) + ")")
        params += [f"%{q}%"] * len(spec["search"])
    active = {}
    for key, clause in spec["filters"].items():
        value = (args.get(key) or "").strip()
        if value:
            where.append(clause)
            params.append(int(value) if key in ("company", "consent") and value.isdigit() else value)
            active[key] = value
    if obj == "deals" and args.get("open") == "1":
        where.append(f"d.{OPEN_SQL}")
        active["open"] = "1"
    if obj == "tickets" and args.get("open") == "1":
        where.append("t.status <> 'Closed'")
        active["open"] = "1"
    sort = args.get("sort") if args.get("sort") in spec["sorts"] else DEFAULT_SORT[obj]
    base = f"{spec['select']} WHERE {' AND '.join(where)}"
    total = scalar(f"SELECT COUNT(*) FROM ({base}) AS counted", *params)
    page = max(1, int(args.get("page")) if str(args.get("page", "")).isdigit() else 1)
    sql = f"{base} ORDER BY {spec['sorts'][sort]}"
    if paginate:
        sql += f" LIMIT {PAGE_SIZE} OFFSET {(page - 1) * PAGE_SIZE}"
    return rows(sql, *params), total, page, active | {"q": q, "sort": sort}


def view_tabs(obj):
    """Built-in and saved views, shown as tabs above a list."""
    me = g.user["name"]
    builtin = {
        "contacts": [("All contacts", ""), ("My contacts", urlencode({"owner": me})),
                     ("New leads", urlencode({"lifecycle": "Lead", "lead_status": "New"})),
                     ("Customers", urlencode({"lifecycle": "Customer"}))],
        "companies": [("All companies", ""), ("My companies", urlencode({"owner": me}))],
        "deals": [("All deals", ""), ("My open deals", urlencode({"owner": me, "open": "1"})),
                  ("Won", urlencode({"stage": "Won"}))],
        "tickets": [("All tickets", ""), ("Open", urlencode({"open": "1"})),
                    ("My open tickets", urlencode({"owner": me, "open": "1"})),
                    ("Urgent", urlencode({"priority": "Urgent", "open": "1"}))],
    }[obj]
    saved = rows("SELECT id, name, query FROM saved_views WHERE workspace_id=? AND user_id=? AND object=? ORDER BY id",
                 ws(), g.user["id"], obj)
    current = normalise_query(urlencode(list(request.args.items(multi=True))))
    tabs = [dict(name=name, query=query, id=None, active=normalise_query(query) == current) for name, query in builtin]
    tabs += [dict(name=v["name"], query=v["query"], id=v["id"], active=normalise_query(v["query"]) == current) for v in saved]
    return tabs, current


def normalise_query(query):
    """A query string with paging and layout removed and keys sorted, so equal filters compare equal."""
    return urlencode(sorted((k, v) for k, v in parse_qsl(query) if k not in ("page", "view") and v))


def timeline(column, record_id):
    """Logged activity and tasks for a record, newest first, plus tasks still to do."""
    entries = [dict(e) | {"when": e["occurred_at"]} for e in rows(
        f"SELECT * FROM engagements WHERE workspace_id=? AND {column}=? ORDER BY occurred_at DESC, id DESC LIMIT 200",
        ws(), record_id)]
    tasks = rows(f"SELECT * FROM activities WHERE workspace_id=? AND {column}=? ORDER BY due_at", ws(), record_id)
    upcoming = [t for t in tasks if not t["done"]]
    entries += [{"kind": "task", "subject": t["subject"], "body": None, "outcome": t["kind"], "author": t["owner"],
                 "when": t["due_at"], "id": t["id"], "done": t["done"]} for t in tasks if t["done"]]
    entries.sort(key=lambda e: e["when"], reverse=True)
    return entries, upcoming


def validate_company(f):
    errors, data = {}, {}
    data["name"] = f.get("name", "").strip()
    if not data["name"]:
        errors["name"] = "Enter the company name."
    data["postcode"] = ukfmt.normalise_postcode(f.get("postcode"))
    if not data["postcode"]:
        errors["postcode"] = "Enter a valid UK postcode, like EH2 2AN."
    data["company_no"] = ukfmt.normalise_company_no(f.get("company_no"))
    if data["company_no"] is None:
        errors["company_no"] = "Companies House numbers have 8 characters, like 08451236 or SC512345."
    data["vat_no"] = ukfmt.normalise_vat(f.get("vat_no"))
    if data["vat_no"] is None:
        errors["vat_no"] = "UK VAT numbers look like GB123456789."
    data["phone"] = ukfmt.normalise_phone(f.get("phone"))
    if data["phone"] is None:
        errors["phone"] = "Enter a UK number, like 0131 496 0000."
    website = f.get("website", "").strip()
    if website and not website.startswith(("http://", "https://")):
        website = "https://" + website
    data["website"] = website
    for key in ("industry", "address", "city", "region"):
        data[key] = f.get(key, "").strip()
    data["owner"] = chosen_owner(f.get("owner"))
    return data, errors


def validate_contact(f, contact_id=None):
    errors, data = {}, {}
    data["first_name"], data["last_name"] = f.get("first_name", "").strip(), f.get("last_name", "").strip()
    if not data["first_name"] or not data["last_name"]:
        errors["last_name"] = "Enter a first and last name."
    email = f.get("email", "").strip().lower()
    if email and not auth.valid_email(email):
        errors["email"] = "Enter a valid email address."
    elif email and one("SELECT id FROM contacts WHERE workspace_id=? AND email=? AND id <> ?", ws(), email, contact_id or 0):
        errors["email"] = "Someone in your contacts already has this email."
    data["email"] = email
    data["phone"] = ukfmt.normalise_phone(f.get("phone"))
    if data["phone"] is None:
        errors["phone"] = "Enter a UK number, like 0131 496 0000 or +44 7700 900123."
    data["lawful_basis"] = f.get("lawful_basis")
    if data["lawful_basis"] not in LAWFUL_BASES:
        errors["lawful_basis"] = "Choose the UK GDPR lawful basis for holding this person's data."
    data["role"] = f.get("role", "").strip()
    data["company_id"] = owned("companies", f.get("company_id"))
    data["lifecycle_stage"] = f.get("lifecycle_stage") if f.get("lifecycle_stage") in LIFECYCLE_STAGES else "Lead"
    data["lead_status"] = f.get("lead_status") if f.get("lead_status") in LEAD_STATUSES else "New"
    data["owner"] = chosen_owner(f.get("owner"))
    # PECR: electronic marketing needs explicit opt-in, recorded separately from the lawful basis.
    data["marketing_consent"] = int(f.get("marketing_consent") == "on")
    return data, errors


def render_index(obj, template, **extra):
    data, total, page, active = list_records(obj, request.args)
    tabs, current = view_tabs(obj)
    return render_template(template, records=data, total=total, page=page, pages=-(-total // PAGE_SIZE) or 1,
                           active=active, tabs=tabs, current_query=current, obj=obj, owners_all=owner_names(), **extra)


def register(app):

    # --- Contacts -----------------------------------------------------------

    @app.route("/contacts")
    def contacts():
        return render_index("contacts", "contacts.html", lead_statuses=LEAD_STATUSES)

    @app.post("/contacts")
    def create_contact():
        data, errors = validate_contact(request.form)
        if errors:
            for message in errors.values():
                flash(f"Contact not added. {message}", "error")
                break
            return back("contacts")
        db = get_db()
        contact_id = db.insert("contacts", workspace_id=ws(), **data, created_at=today().isoformat(),
                               consent_date=today().isoformat() if data["marketing_consent"] else None)
        log_event("Contact created", f"Added by {g.user['name']}", contact_id=contact_id, company_id=data["company_id"])
        db.commit()
        flash(f"Contact added: {data['first_name']} {data['last_name']}.", "ok")
        return redirect(url_for("contact", contact_id=contact_id))

    @app.route("/contacts/<int:contact_id>")
    def contact(contact_id):
        c = get_or_404("contacts", contact_id)
        company = one("SELECT * FROM companies WHERE id=? AND workspace_id=?", c["company_id"], ws()) if c["company_id"] else None
        entries, upcoming = timeline("contact_id", contact_id)
        return render_template(
            "contact.html", c=c, company=company, entries=entries, upcoming=upcoming,
            deals=rows("SELECT d.*, co.name AS company FROM deals d JOIN companies co ON co.id=d.company_id"
                       " WHERE d.workspace_id=? AND d.contact_id=? ORDER BY d.stage IN ('Won','Lost'), d.close_date",
                       ws(), contact_id),
            tickets=rows("SELECT * FROM tickets WHERE workspace_id=? AND contact_id=? ORDER BY status='Closed', id DESC",
                         ws(), contact_id),
            record=dict(contact_id=contact_id, company_id=c["company_id"]), call_outcomes=CALL_OUTCOMES,
            lead_statuses=LEAD_STATUSES)

    @app.post("/contacts/<int:contact_id>/edit")
    def edit_contact(contact_id):
        old = get_or_404("contacts", contact_id)
        data, errors = validate_contact(request.form, contact_id)
        if errors:
            flash("Changes not saved. " + next(iter(errors.values())), "error")
            return redirect(url_for("contact", contact_id=contact_id))
        consent_date = old["consent_date"]
        if data["marketing_consent"] and not old["marketing_consent"]:
            consent_date = today().isoformat()
            log_event("Marketing consent given", contact_id=contact_id)
        elif old["marketing_consent"] and not data["marketing_consent"]:
            consent_date = None
            log_event("Marketing consent withdrawn", contact_id=contact_id)
        if data["lifecycle_stage"] != old["lifecycle_stage"]:
            log_event(f"Lifecycle stage changed to {data['lifecycle_stage']}", f"Changed by {g.user['name']}",
                      contact_id=contact_id, company_id=data["company_id"])
        if data["owner"] != old["owner"]:
            log_event(f"Owner changed to {data['owner']}", contact_id=contact_id)
        db = get_db()
        db.execute("UPDATE contacts SET first_name=?, last_name=?, email=?, phone=?, lawful_basis=?, role=?, company_id=?,"
                   " lifecycle_stage=?, lead_status=?, owner=?, marketing_consent=?, consent_date=? WHERE id=? AND workspace_id=?",
                   (data["first_name"], data["last_name"], data["email"], data["phone"], data["lawful_basis"], data["role"],
                    data["company_id"], data["lifecycle_stage"], data["lead_status"], data["owner"],
                    data["marketing_consent"], consent_date, contact_id, ws()))
        db.commit()
        flash("Contact updated.", "ok")
        return redirect(url_for("contact", contact_id=contact_id))

    @app.route("/contacts/<int:contact_id>/export")
    def export_contact(contact_id):
        """Subject access request: everything held about one person, as JSON."""
        c = get_or_404("contacts", contact_id)
        payload = {
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "controller": dict(one("SELECT name, legal_name, address, city, postcode, company_no FROM workspaces WHERE id=?",
                                   ws())),
            "data_subject": dict(c),
            "activity": [dict(e) for e in rows("SELECT kind, subject, body, outcome, author, occurred_at FROM engagements"
                                               " WHERE workspace_id=? AND contact_id=? ORDER BY occurred_at", ws(), contact_id)],
            "tickets": [dict(t) for t in rows("SELECT subject, status, created_at, closed_at FROM tickets"
                                              " WHERE workspace_id=? AND contact_id=?", ws(), contact_id)],
            "form_submissions": [dict(s, data=json.loads(s["data"])) for s in rows(
                "SELECT f.name AS form, s.data, s.ip, s.created_at FROM form_submissions s JOIN web_forms f ON f.id=s.form_id"
                " WHERE s.workspace_id=? AND s.contact_id=? ORDER BY s.id", ws(), contact_id)],
        }
        return Response(json.dumps(payload, indent=2, default=str), mimetype="application/json",
                        headers={"Content-Disposition": f"attachment; filename=sar-contact-{contact_id}.json"})

    @app.post("/contacts/<int:contact_id>/erase")
    def erase_contact(contact_id):
        """Right to erasure (UK GDPR Art. 17). Admins only, as it can't be undone."""
        auth.admin_required()
        c = get_or_404("contacts", contact_id)
        db = get_db()
        db.execute("DELETE FROM contacts WHERE id=? AND workspace_id=?", (contact_id, ws()))
        from files import delete_for
        delete_for("contact", contact_id)
        if c["company_id"]:
            log_event("A contact's personal data was erased", f"Erased by {g.user['name']}", company_id=c["company_id"])
        db.commit()
        flash("Contact erased. Their personal data and activity have been deleted.", "ok")
        return redirect(url_for("company", company_id=c["company_id"]) if c["company_id"] else url_for("contacts"))

    # --- Companies ----------------------------------------------------------

    @app.route("/companies")
    def companies():
        regions = [r[0] for r in rows("SELECT DISTINCT region FROM companies WHERE workspace_id=? AND region <> ''"
                                      " ORDER BY 1", ws())]
        industries = [r[0] for r in rows("SELECT DISTINCT industry FROM companies WHERE workspace_id=? AND industry <> ''"
                                         " ORDER BY 1", ws())]
        return render_index("companies", "companies.html", region_options=regions, industry_options=industries,
                            customer_form=g.get("customer_form"), customer_errors=g.get("customer_errors"))

    @app.post("/companies")
    def create_company():
        data, errors = validate_company(request.form)
        if errors:
            g.customer_form, g.customer_errors = request.form, errors
            return companies(), 422
        db = get_db()
        company_id = db.insert("companies", workspace_id=ws(), **data, created_at=today().isoformat())
        log_event("Company created", f"Added by {g.user['name']}", company_id=company_id)
        db.commit()
        flash(f"Company added: {data['name']}.", "ok")
        return redirect(url_for("company", company_id=company_id))

    @app.route("/companies/<int:company_id>")
    def company(company_id):
        c = get_or_404("companies", company_id)
        entries, upcoming = timeline("company_id", company_id)
        stats = dict(
            lifetime=scalar("SELECT SUM(value) FROM deals WHERE workspace_id=? AND company_id=? AND stage='Won'", ws(), company_id),
            pipeline=scalar(f"SELECT SUM(value) FROM deals WHERE workspace_id=? AND company_id=? AND {OPEN_SQL}", ws(), company_id),
            outstanding=scalar("SELECT SUM(net + vat) FROM invoices WHERE workspace_id=? AND company_id=? AND paid_date IS NULL",
                               ws(), company_id),
        )
        return render_template(
            "company.html", c=c, stats=stats, entries=entries, upcoming=upcoming,
            contacts=rows("SELECT * FROM contacts WHERE workspace_id=? AND company_id=? ORDER BY last_name", ws(), company_id),
            deals=rows("SELECT * FROM deals WHERE workspace_id=? AND company_id=? ORDER BY stage IN ('Won','Lost'), close_date DESC",
                       ws(), company_id),
            invoices=rows("SELECT * FROM invoices WHERE workspace_id=? AND company_id=? ORDER BY issue_date DESC", ws(), company_id),
            tickets=rows("SELECT * FROM tickets WHERE workspace_id=? AND company_id=? ORDER BY status='Closed', id DESC",
                         ws(), company_id),
            record=dict(company_id=company_id), call_outcomes=CALL_OUTCOMES, lead_statuses=LEAD_STATUSES,
            errors=g.get("contact_errors") or {}, form=g.get("contact_form") or {})

    @app.post("/companies/<int:company_id>/edit")
    def edit_company(company_id):
        old = get_or_404("companies", company_id)
        data, errors = validate_company(request.form)
        if errors:
            flash("Changes not saved. " + next(iter(errors.values())), "error")
            return redirect(url_for("company", company_id=company_id))
        if data["owner"] != old["owner"]:
            log_event(f"Owner changed to {data['owner']}", company_id=company_id)
        db = get_db()
        db.execute("UPDATE companies SET name=?, company_no=?, vat_no=?, industry=?, address=?, city=?, postcode=?, region=?,"
                   " website=?, phone=?, owner=? WHERE id=? AND workspace_id=?",
                   (data["name"], data["company_no"], data["vat_no"], data["industry"], data["address"], data["city"],
                    data["postcode"], data["region"], data["website"], data["phone"], data["owner"], company_id, ws()))
        db.commit()
        flash("Company updated.", "ok")
        return redirect(url_for("company", company_id=company_id))

    @app.post("/companies/<int:company_id>/delete")
    def delete_company(company_id):
        auth.admin_required()
        c = get_or_404("companies", company_id)
        problem = delete_company_records(company_id)
        if problem:
            flash(problem, "error")
            return redirect(url_for("company", company_id=company_id))
        get_db().commit()
        flash(f"Deleted {c['name']}. Its people are kept as contacts without a company.", "ok")
        return redirect(url_for("companies"))

    # Old route from the first release: add a contact from a company page.
    @app.post("/customers/<int:company_id>/contacts")
    def create_contact_for_company(company_id):
        get_or_404("companies", company_id)
        return create_contact()

    # --- Deals --------------------------------------------------------------

    @app.route("/deals/<int:deal_id>")
    def deal(deal_id):
        from quotes import quote_state
        d = get_or_404("deals", deal_id)
        company = one("SELECT * FROM companies WHERE id=? AND workspace_id=?", d["company_id"], ws())
        contact = one("SELECT * FROM contacts WHERE id=? AND workspace_id=?", d["contact_id"], ws()) if d["contact_id"] else None
        lines = rows("SELECT * FROM line_items WHERE workspace_id=? AND deal_id=? ORDER BY id", ws(), deal_id)
        totals = line_totals(lines)
        entries, upcoming = timeline("deal_id", deal_id)
        return render_template(
            "deal.html", d=d, company=company, contact=contact, lines=lines, totals=totals, entries=entries,
            upcoming=upcoming,
            products=rows("SELECT * FROM products WHERE workspace_id=? AND active=1 ORDER BY name", ws()),
            invoices=rows("SELECT * FROM invoices WHERE workspace_id=? AND deal_id=? ORDER BY id DESC", ws(), deal_id),
            quotes=[(q, quote_state(q)) for q in rows("SELECT * FROM quotes WHERE workspace_id=? AND deal_id=? ORDER BY id DESC",
                                                      ws(), deal_id)],
            company_contacts=rows("SELECT id, first_name, last_name FROM contacts WHERE workspace_id=? AND company_id=?"
                                  " ORDER BY first_name", ws(), d["company_id"]),
            record=dict(deal_id=deal_id, company_id=d["company_id"], contact_id=d["contact_id"]),
            call_outcomes=CALL_OUTCOMES, all_stages=OPEN_STAGES + ["Won", "Lost"])

    @app.post("/deals/<int:deal_id>/edit")
    def edit_deal(deal_id):
        old = get_or_404("deals", deal_id)
        f = request.form
        title = f.get("title", "").strip()
        company_id = owned("companies", f.get("company_id")) or old["company_id"]
        contact_id = owned("contacts", f.get("contact_id"))
        try:
            close_date = datetime.strptime(f.get("close_date", ""), "%Y-%m-%d").date().isoformat()
        except ValueError:
            close_date = None
        has_lines = scalar("SELECT COUNT(*) FROM line_items WHERE workspace_id=? AND deal_id=?", ws(), deal_id)
        value = old["value"] if has_lines else ukfmt.parse_money(f.get("value"))
        if not title or not close_date or value is None:
            flash("Changes not saved. A deal needs a name, a value in £ and an expected close date.", "error")
            return redirect(url_for("deal", deal_id=deal_id))
        owner = chosen_owner(f.get("owner"))
        source = f.get("source") if f.get("source") in SOURCES else old["source"]
        for label, before, after in (("Amount", ukfmt.money(old["value"]), ukfmt.money(value)),
                                     ("Close date", ukfmt.uk_date(old["close_date"]), ukfmt.uk_date(close_date)),
                                     ("Owner", old["owner"], owner)):
            if before != after:
                log_event(f"{label} changed to {after}", f"Was {before}", deal_id=deal_id, company_id=company_id,
                          contact_id=contact_id)
        db = get_db()
        db.execute("UPDATE deals SET title=?, company_id=?, contact_id=?, close_date=?, value=?, owner=?, source=?"
                   " WHERE id=? AND workspace_id=?",
                   (title, company_id, contact_id, close_date, value, owner, source, deal_id, ws()))
        if contact_id and old["stage"] in OPEN_STAGES:
            advance_lifecycle(contact_id, "Opportunity", f"Linked to the deal {title}")
        db.commit()
        flash("Deal updated.", "ok")
        return redirect(url_for("deal", deal_id=deal_id))

    @app.post("/deals/<int:deal_id>/delete")
    def delete_deal(deal_id):
        auth.admin_required()
        d = get_or_404("deals", deal_id)
        if scalar("SELECT COUNT(*) FROM invoices WHERE workspace_id=? AND deal_id=?", ws(), deal_id):
            flash("This deal has invoices, which UK law requires you to keep for 6 years, so it can't be deleted.", "error")
            return redirect(url_for("deal", deal_id=deal_id))
        db = get_db()
        db.execute("DELETE FROM deals WHERE id=? AND workspace_id=?", (deal_id, ws()))
        from files import delete_for
        delete_for("deal", deal_id)
        log_event(f"Deal deleted: {d['title']}", f"Deleted by {g.user['name']}", company_id=d["company_id"])
        db.commit()
        flash(f"Deleted the deal {d['title']}.", "ok")
        return redirect(url_for("pipeline"))

    # --- Activity timeline --------------------------------------------------

    @app.post("/engagements")
    def log_engagement():
        f = request.form
        kind = f.get("kind")
        links = resolve_links(f)
        if not any(links.values()):
            abort(400)
        try:
            when = datetime.fromisoformat(f"{f.get('date')}T{f.get('time') or '09:00'}")
        except ValueError:
            when = now()
        if kind == "task":
            subject = f.get("subject", "").strip()
            task_type = f.get("task_type") if f.get("task_type") in ACTIVITY_KINDS else "Task"
            if not subject:
                flash("Task not created. Give it a subject.", "error")
                return back("overview")
            owner = chosen_owner(f.get("owner"))
            get_db().insert("activities", workspace_id=ws(), kind=task_type, subject=subject,
                            owner=owner, due_at=when.isoformat(timespec="minutes"), done=0, **links)
            notify_owner(owner, f"{g.user['name']} gave you a task: {subject}", f"Due {ukfmt.uk_datetime(when.isoformat())}",
                         f.get("next"))
            get_db().commit()
            flash(f"Task created for {ukfmt.uk_datetime(when.isoformat())}.", "ok")
            return back("overview")
        if kind not in ENGAGEMENT_KINDS:
            abort(400)
        body = f.get("body", "").strip()
        subject = f.get("subject", "").strip() or None
        if not body and not subject:
            flash("Nothing logged. Add a few words about what happened.", "error")
            return back("overview")
        outcome = f.get("outcome") if kind == "call" and f.get("outcome") in CALL_OUTCOMES else None
        log_event(subject, body, kind=kind, outcome=outcome, occurred_at=when.isoformat(timespec="minutes"), **links)
        from notifications import mentioned, notify
        notify(mentioned(f"{subject or ''} {body}"), f"{g.user['name']} mentioned you in a {kind}",
               (subject or body)[:200], f.get("next") if (f.get("next") or "").startswith("/") else None)
        if links["ticket_id"] and kind in ("email", "call"):
            # The first email or call on a ticket is its first response.
            get_db().execute("UPDATE tickets SET first_responded_at=? WHERE id=? AND workspace_id=? AND first_responded_at IS NULL",
                             (when.isoformat(timespec="minutes"), links["ticket_id"], ws()))
        get_db().commit()
        flash({"note": "Note added.", "call": "Call logged.", "email": "Email logged.", "meeting": "Meeting logged."}[kind], "ok")
        return back("overview")

    @app.post("/engagements/<int:engagement_id>/delete")
    def delete_engagement(engagement_id):
        e = get_or_404("engagements", engagement_id)
        if e["kind"] == "system" or (e["author"] != g.user["name"] and g.user["role"] != "admin"):
            abort(403)
        get_db().execute("DELETE FROM engagements WHERE id=? AND workspace_id=?", (engagement_id, ws()))
        get_db().commit()
        flash("Removed from the timeline.", "ok")
        return back("overview")

    # --- Bulk actions ---------------------------------------------------------

    @app.post("/bulk/<obj>")
    def bulk(obj):
        table = {"contacts": "contacts", "companies": "companies", "deals": "deals", "tickets": "tickets"}.get(obj)
        if not table:
            abort(404)
        ids = [int(i) for i in request.form.getlist("ids") if i.isdigit()]
        ids = [r[0] for r in rows(f"SELECT id FROM {table} WHERE workspace_id=? AND id IN ({','.join('?' * len(ids))})",
                                  ws(), *ids)] if ids else []
        action, value = request.form.get("action"), request.form.get("value", "")
        if not ids:
            flash("Select at least one record first.", "error")
            return back(obj)
        db = get_db()
        marks = ",".join("?" * len(ids))
        if action == "owner" and value in owner_names():
            db.execute(f"UPDATE {table} SET owner=? WHERE workspace_id=? AND id IN ({marks})", (value, ws(), *ids))
            message = f"{len(ids)} assigned to {value}."
        elif action == "lifecycle" and table == "contacts" and value in LIFECYCLE_STAGES:
            db.execute(f"UPDATE contacts SET lifecycle_stage=? WHERE workspace_id=? AND id IN ({marks})", (value, ws(), *ids))
            for contact_id in ids:
                log_event(f"Lifecycle stage changed to {value}", f"Bulk update by {g.user['name']}", contact_id=contact_id)
            message = f"{len(ids)} moved to {value}."
        elif action == "status" and table == "tickets" and value in TICKET_STATUSES:
            from service import set_ticket_status
            for ticket_id in ids:
                set_ticket_status(ticket_id, value)
            message = f"{len(ids)} set to {value}."
        elif action == "delete":
            auth.admin_required()
            skipped = 0
            for record_id in ids:
                if table == "companies":
                    if delete_company_records(record_id):
                        skipped += 1
                elif table == "deals" and scalar("SELECT COUNT(*) FROM invoices WHERE workspace_id=? AND deal_id=?",
                                                 ws(), record_id):
                    skipped += 1
                else:
                    db.execute(f"DELETE FROM {table} WHERE id=? AND workspace_id=?", (record_id, ws()))
                    from files import RECORDS, delete_for
                    delete_for(next(k for k, v in RECORDS.items() if v == table), record_id)
            message = f"Deleted {len(ids) - skipped}."
            if skipped:
                message += f" Kept {skipped} with invoices, which UK law requires you to keep for 6 years."
        else:
            flash("Choose what to change.", "error")
            return back(obj)
        db.commit()
        flash(message, "ok")
        return back(obj)


def resolve_links(f):
    """Record links for a timeline entry or task, filled out from the record it was logged on."""
    links = dict(company_id=owned("companies", f.get("company_id")), contact_id=owned("contacts", f.get("contact_id")),
                 deal_id=owned("deals", f.get("deal_id")), ticket_id=owned("tickets", f.get("ticket_id")))
    if links["deal_id"]:
        d = one("SELECT company_id, contact_id FROM deals WHERE id=?", links["deal_id"])
        links["company_id"] = links["company_id"] or d["company_id"]
        links["contact_id"] = links["contact_id"] or d["contact_id"]
    if links["ticket_id"]:
        t = one("SELECT company_id, contact_id FROM tickets WHERE id=?", links["ticket_id"])
        links["company_id"] = links["company_id"] or t["company_id"]
        links["contact_id"] = links["contact_id"] or t["contact_id"]
    if links["contact_id"] and not links["company_id"]:
        links["company_id"] = one("SELECT company_id FROM contacts WHERE id=?", links["contact_id"])["company_id"]
    return links


def delete_company_records(company_id):
    """Delete a company, keeping its people as contacts. Returns a reason if it must be kept."""
    if scalar("SELECT COUNT(*) FROM invoices WHERE workspace_id=? AND company_id=?", ws(), company_id):
        return "This company has invoices, which UK law requires you to keep for 6 years, so it can't be deleted."
    db = get_db()
    db.execute("UPDATE contacts SET company_id=NULL WHERE workspace_id=? AND company_id=?", (ws(), company_id))
    # Keep notes that are also on a person's timeline.
    db.execute("UPDATE engagements SET company_id=NULL WHERE workspace_id=? AND company_id=? AND contact_id IS NOT NULL",
               (ws(), company_id))
    db.execute("DELETE FROM companies WHERE id=? AND workspace_id=?", (company_id, ws()))
    from files import delete_for
    delete_for("company", company_id)
    return None


def notify_owner(owner_name, title, body=None, url=None):
    """Tell a team member about something given to them, if the owner is a person on the team."""
    from notifications import notify, user_named
    notify([user_named(owner_name)], title, body, url if (url or "").startswith("/") else None)


def line_totals(lines):
    """Net, VAT and gross for a set of line items, with VAT summarised by rate as UK VAT invoices require."""
    from ukfmt import vat_amount
    net, by_rate = 0, {}
    for li in lines:
        line_net = li["quantity"] * li["unit_price"] * (100 - li["discount_pct"]) // 100
        net += line_net
        by_rate[li["vat_rate"]] = by_rate.get(li["vat_rate"], 0) + line_net
    vat_by_rate = {rate: vat_amount(amount, rate) for rate, amount in by_rate.items()}
    vat = sum(vat_by_rate.values())
    return dict(net=net, vat=vat, gross=net + vat, by_rate=sorted(((r, by_rate[r], vat_by_rate[r]) for r in by_rate),
                                                                  reverse=True))

