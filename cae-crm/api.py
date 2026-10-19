"""The public API: contacts, companies, deals, tickets and invoices as JSON, for other systems to read and change.

Each business makes its own API keys in Settings > API and webhooks. A key is shown once and stored only as a hash. Read
keys can list and fetch; write keys can also add and update. Keys go in an "Authorization: Bearer <key>" header, or as
the password in HTTP Basic sign-in, which is how Power BI sends them. Each key may make RATE_LIMIT requests a minute.

The Power BI feed (/api/v1/feed/<table>) returns a whole table as CSV (or JSON) with plain column names and amounts in
pounds, ready for Power BI, Excel or any reporting tool."""

import base64
import csv
import hashlib
import io
import json
import re
import secrets
from datetime import date, datetime, timezone

from flask import (Blueprint, Response, current_app, flash, g, jsonify, redirect, render_template, request,
                   url_for)
from werkzeug.exceptions import HTTPException

import auth
import ukfmt
from core import (actor_name, advance_lifecycle, chosen_owner, log_event, now, one, owned, owner_names, rows,
                  scalar, today, workspace, ws)
from db import (LAWFUL_BASES, LEAD_STATUSES, LIFECYCLE_STAGES, OPEN_STAGES, SOURCES, STAGE_PROBABILITY,
                TICKET_CATEGORIES, TICKET_PRIORITIES, TICKET_SOURCES, TICKET_STATUSES, get_db)
from events import emit

bp = Blueprint("api", __name__, url_prefix="/api/v1")
MAX_KEYS = 20
PER_PAGE, MAX_PER_PAGE = 50, 100
FEED_LIMIT = 50_000

# What each object shows, in order. Money is in pence, as stored, so nothing is lost to rounding.
FIELDS = {
    "contacts": ["id", "first_name", "last_name", "email", "phone", "role", "company_id", "lifecycle_stage", "lead_status",
                 "owner", "lawful_basis", "marketing_consent", "consent_date", "created_at"],
    "companies": ["id", "name", "company_no", "vat_no", "industry", "address", "city", "region", "postcode", "website",
                  "phone", "owner", "created_at"],
    "deals": ["id", "title", "company_id", "contact_id", "value", "stage", "probability", "owner", "source", "close_date",
              "closed_at", "created_at"],
    "tickets": ["id", "subject", "description", "status", "priority", "category", "source", "owner", "company_id",
                "contact_id", "created_at", "first_response_due", "resolution_due", "first_responded_at", "closed_at"],
    "invoices": ["id", "number", "company_id", "deal_id", "description", "net", "vat", "issue_date", "due_date",
                 "paid_date", "sent_at", "amount_paid", "credited", "late_interest", "late_compensation"],
    "quotes": ["id", "number", "title", "deal_id", "company_id", "contact_id", "status", "net", "vat", "issue_date",
               "expiry_date", "decided_at", "signer_name"],
}
RENAMED = {"value": "value_pence", "net": "net_pence", "vat": "vat_pence", "amount_paid": "paid_pence",
           "credited": "credited_pence", "late_interest": "late_interest_pence",
           "late_compensation": "late_compensation_pence"}
PAGES = {"contacts": "contact", "companies": "company", "deals": "deal", "tickets": "ticket", "invoices": "invoice",
         "quotes": "quote"}
ARGS = {"contacts": "contact_id", "companies": "company_id", "deals": "deal_id", "tickets": "ticket_id",
        "invoices": "invoice_id", "quotes": "quote_id"}
# Filters each list accepts: query parameter -> column.
FILTERS = {
    "contacts": ["email", "company_id", "owner", "lifecycle_stage", "lead_status"],
    "companies": ["owner", "postcode"],
    "deals": ["stage", "company_id", "contact_id", "owner"],
    "tickets": ["status", "priority", "company_id", "contact_id", "owner"],
    "invoices": ["company_id", "deal_id"],
}
WRITABLE = ("contacts", "companies", "deals", "tickets")


class ApiError(Exception):
    def __init__(self, status, message, fields=None):
        super().__init__(message)
        self.status, self.message, self.fields = status, message, fields


def digest(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def new_key():
    return "cae_" + secrets.token_urlsafe(30)


def presented_key():
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:].strip()
    if header.startswith("Basic "):
        try:
            user, _, password = base64.b64decode(header[6:]).decode().partition(":")
        except (ValueError, UnicodeDecodeError):
            return None
        return (password or user).strip()  # Power BI sends the key as the password; any user name will do
    return None


def custom_out(obj, row):
    if obj not in ("contacts", "companies", "deals", "tickets"):
        return None
    from fields import definitions, values
    saved = values(row)
    return {f["label"]: saved.get(str(f["id"])) for f in definitions(obj)}


def serialise(obj, row):
    out = {}
    for name in FIELDS[obj]:
        value = row[name]
        if name == "marketing_consent":
            value = bool(value)
        out[RENAMED.get(name, name)] = value
    if obj in ("invoices", "quotes"):
        out["gross_pence"] = row["net"] + row["vat"]
    if obj == "invoices":
        from payments import balance
        out["balance_pence"] = balance(row)
        out["status"] = ("Paid" if row["paid_date"] else
                         "Overdue" if row["due_date"] < today().isoformat() else "Due")
    custom = custom_out(obj, row)
    if custom is not None:
        out["custom"] = custom
    if obj != "quotes":
        out["url"] = url_for(PAGES[obj], **{ARGS[obj]: row["id"]}, _external=True)
    return out


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError(400, "Send a JSON object, with the header Content-Type: application/json.")
    return data


def require(condition, message, field=None):
    if not condition:
        raise ApiError(422, message, {field: message} if field else None)


def check_choice(data, field, allowed):
    if field in data and data[field] not in allowed:
        raise ApiError(422, f"{field} must be one of: {', '.join(allowed)}.", {field: "Not one of the allowed values."})


def check_owner(data):
    if data.get("owner") and data["owner"] not in owner_names():
        raise ApiError(422, "owner must be the name of someone on your team.", {"owner": "Not on your team."})


def check_link(data, field, table):
    if data.get(field) is not None and owned(table, data[field]) is None:
        raise ApiError(422, f"{field} isn't one of your {table}.", {field: "Not found."})


def custom_in(obj, data, saved):
    """Apply "custom": {"Label": value} from a request to a record's saved custom values."""
    given = data.get("custom")
    if given is None:
        return saved
    require(isinstance(given, dict), "custom must be an object of field names and values.", "custom")
    from fields import definitions, parse
    by_name = {f["label"].lower(): f for f in definitions(obj)} | {str(f["id"]): f for f in definitions(obj)}
    for name, value in given.items():
        f = by_name.get(str(name).lower())
        require(f is not None, f"There's no custom field called {name}.", "custom")
        raw = ("on" if value else "") if f["field_type"] == "yes_no" else ("" if value is None else str(value))
        parsed, problem = parse(f, raw)
        require(not problem, problem or "", "custom")
        saved[str(f["id"])] = parsed
    return saved


def record(obj, record_id):
    row = one(f"SELECT * FROM {obj} WHERE id=? AND workspace_id=?", record_id, ws())
    if row is None:
        raise ApiError(404, f"No {PAGES[obj]} with id {record_id}.")
    return row


def audit(action, obj, record_id):
    from audit import record as write
    write(ws(), {"id": None, "name": actor_name()}, action, PAGES[obj].capitalize(), record_id)


# --- Writing -------------------------------------------------------------------------------------------------------

def contact_form(data, old=None):
    """The contact as the web form would send it, so the same checks apply."""
    keys = ("first_name", "last_name", "email", "phone", "lawful_basis", "role", "company_id", "lifecycle_stage",
            "lead_status", "owner")
    f = {k: (old[k] if old else None) for k in keys}
    f["marketing_consent"] = bool(old["marketing_consent"]) if old else False
    f.update({k: v for k, v in data.items() if k in f})
    form = {k: ("" if v is None else str(v)) for k, v in f.items()}
    form["marketing_consent"] = "on" if f["marketing_consent"] else ""
    return form


def save_contact(data, old=None):
    from crm import validate_contact
    check_choice(data, "lawful_basis", LAWFUL_BASES)
    check_choice(data, "lifecycle_stage", LIFECYCLE_STAGES)
    check_choice(data, "lead_status", LEAD_STATUSES)
    check_owner(data)
    check_link(data, "company_id", "companies")
    clean, errors = validate_contact(contact_form(data, old), old["id"] if old else None)
    if errors:
        raise ApiError(422, next(iter(errors.values())), errors)
    custom = json.dumps(custom_in("contacts", data, json.loads(old["custom"] or "{}") if old else {}))
    db = get_db()
    if old is None:
        contact_id = db.insert("contacts", workspace_id=ws(), **clean, custom=custom, created_at=today().isoformat(),
                               consent_date=today().isoformat() if clean["marketing_consent"] else None)
        log_event("Contact created", f"Added by {actor_name()}", contact_id=contact_id, company_id=clean["company_id"])
        emit("contact.created", contact_id)
        return contact_id
    consent_date = old["consent_date"]
    if clean["marketing_consent"] != old["marketing_consent"]:
        consent_date = today().isoformat() if clean["marketing_consent"] else None
    db.execute("UPDATE contacts SET first_name=?, last_name=?, email=?, phone=?, lawful_basis=?, role=?, company_id=?, "
               "lifecycle_stage=?, lead_status=?, owner=?, marketing_consent=?, consent_date=?, custom=? "
               "WHERE id=? AND workspace_id=?",
               (clean["first_name"], clean["last_name"], clean["email"], clean["phone"], clean["lawful_basis"],
                clean["role"], clean["company_id"], clean["lifecycle_stage"], clean["lead_status"], clean["owner"],
                clean["marketing_consent"], consent_date, custom, old["id"], ws()))
    log_event("Updated through the API", f"By {actor_name()}", contact_id=old["id"], company_id=clean["company_id"])
    emit("contact.updated", old["id"])
    return old["id"]


def save_company(data, old=None):
    from crm import validate_company
    check_owner(data)
    keys = ("name", "company_no", "vat_no", "industry", "address", "city", "region", "postcode", "website", "phone", "owner")
    f = {k: (old[k] if old else None) for k in keys}
    f.update({k: v for k, v in data.items() if k in f})
    clean, errors = validate_company({k: ("" if v is None else str(v)) for k, v in f.items()})
    if errors:
        raise ApiError(422, next(iter(errors.values())), errors)
    custom = json.dumps(custom_in("companies", data, json.loads(old["custom"] or "{}") if old else {}))
    db = get_db()
    if old is None:
        company_id = db.insert("companies", workspace_id=ws(), **clean, custom=custom, created_at=today().isoformat())
        log_event("Company created", f"Added by {actor_name()}", company_id=company_id)
        emit("company.created", company_id)
        return company_id
    db.execute("UPDATE companies SET name=?, company_no=?, vat_no=?, industry=?, address=?, city=?, postcode=?, region=?, "
               "website=?, phone=?, owner=?, custom=? WHERE id=? AND workspace_id=?",
               (clean["name"], clean["company_no"], clean["vat_no"], clean["industry"], clean["address"], clean["city"],
                clean["postcode"], clean["region"], clean["website"], clean["phone"], clean["owner"], custom, old["id"],
                ws()))
    log_event("Updated through the API", f"By {actor_name()}", company_id=old["id"])
    emit("company.updated", old["id"])
    return old["id"]


def pence(data, old_value):
    """A deal's value from value_pence (whole pence) or value (pounds, as a number or text like "£1,250.50")."""
    if "value_pence" in data:
        v = data["value_pence"]
        require(isinstance(v, int) and not isinstance(v, bool) and v >= 0, "value_pence must be a whole number of pence.",
                "value_pence")
        return v
    if "value" in data:
        v = ukfmt.parse_amount(str(data["value"]))
        require(v is not None, "value must be an amount in pounds, like 1250.50.", "value")
        return v
    return old_value


def iso_date(data, field, old_value):
    if field not in data:
        return old_value
    try:
        return date.fromisoformat(str(data[field])).isoformat()
    except ValueError:
        raise ApiError(422, f"{field} must be a date like 2026-12-31.", {field: "Not a date."}) from None


def save_deal(data, old=None):
    from sales import set_stage
    check_choice(data, "stage", OPEN_STAGES if old is None else list(STAGE_PROBABILITY))
    check_choice(data, "source", SOURCES)
    check_owner(data)
    check_link(data, "company_id", "companies")
    check_link(data, "contact_id", "contacts")
    title = str(data.get("title", old["title"] if old else "")).strip()
    require(title, "title is required.", "title")
    company_id = owned("companies", data["company_id"]) if "company_id" in data else (old["company_id"] if old else None)
    require(company_id, "company_id is required.", "company_id")
    contact_id = owned("contacts", data.get("contact_id")) if "contact_id" in data else (old["contact_id"] if old else None)
    close_date = iso_date(data, "close_date", old["close_date"] if old else None)
    require(close_date, "close_date is required.", "close_date")
    has_lines = old and scalar("SELECT COUNT(*) FROM line_items WHERE workspace_id=? AND deal_id=?", ws(), old["id"])
    require(not (has_lines and ("value" in data or "value_pence" in data)),
            "This deal's value comes from its line items, so it can't be set directly.", "value_pence")
    value = pence(data, old["value"] if old else 0)
    owner = chosen_owner(data.get("owner", old["owner"] if old else None))
    source = data.get("source", old["source"] if old else SOURCES[0])
    custom = json.dumps(custom_in("deals", data, json.loads(old["custom"] or "{}") if old else {}))
    db = get_db()
    if old is None:
        stage = data.get("stage", "Lead")
        deal_id = db.insert("deals", workspace_id=ws(), company_id=company_id, contact_id=contact_id, title=title,
                            value=value, stage=stage, probability=STAGE_PROBABILITY[stage], owner=owner, source=source,
                            close_date=close_date, custom=custom, created_at=today().isoformat())
        log_event("Deal created", f"{title}, {ukfmt.money(value)}, in {stage}. Added by {actor_name()}.", deal_id=deal_id,
                  company_id=company_id, contact_id=contact_id)
        advance_lifecycle(contact_id, "Opportunity", f"Linked to the deal {title}")
        emit("deal.created", deal_id)
        return deal_id
    db.execute("UPDATE deals SET title=?, company_id=?, contact_id=?, close_date=?, value=?, owner=?, source=?, custom=? "
               "WHERE id=? AND workspace_id=?",
               (title, company_id, contact_id, close_date, value, owner, source, custom, old["id"], ws()))
    log_event("Updated through the API", f"By {actor_name()}", deal_id=old["id"], company_id=company_id,
              contact_id=contact_id)
    if data.get("stage") and data["stage"] != old["stage"]:
        set_stage(record("deals", old["id"]), data["stage"])
    emit("deal.updated", old["id"])
    return old["id"]


def save_ticket(data, old=None):
    from crm import notify_owner
    from service import set_ticket_status, sla_due
    check_choice(data, "priority", TICKET_PRIORITIES)
    check_choice(data, "category", TICKET_CATEGORIES)
    check_choice(data, "source", TICKET_SOURCES)
    check_choice(data, "status", TICKET_STATUSES)
    check_owner(data)
    check_link(data, "company_id", "companies")
    check_link(data, "contact_id", "contacts")
    subject = str(data.get("subject", old["subject"] if old else "")).strip()[:200]
    require(subject, "subject is required.", "subject")
    pick = lambda field, default: data[field] if field in data else (old[field] if old else default)  # noqa: E731
    priority = pick("priority", "Medium")
    contact_id = owned("contacts", data.get("contact_id")) if "contact_id" in data else pick("contact_id", None)
    company_id = owned("companies", data.get("company_id")) if "company_id" in data else pick("company_id", None)
    if contact_id and not company_id:
        company_id = one("SELECT company_id FROM contacts WHERE id=?", contact_id)["company_id"]
    owner = chosen_owner(pick("owner", None))
    description = str(pick("description", "") or "").strip()
    custom = json.dumps(custom_in("tickets", data, json.loads(old["custom"] or "{}") if old else {}))
    db = get_db()
    if old is None:
        opened = now()
        first_due, resolve_due = sla_due(opened, priority)
        ticket_id = db.insert("tickets", workspace_id=ws(), company_id=company_id, contact_id=contact_id, subject=subject,
                              description=description, status="New", priority=priority, category=pick("category", "Other"),
                              source=pick("source", "Email"), owner=owner, created_at=opened.isoformat(timespec="minutes"),
                              first_response_due=first_due, resolution_due=resolve_due, custom=custom)
        log_event("Ticket opened", f"{priority} priority. Opened by {actor_name()}.", ticket_id=ticket_id,
                  company_id=company_id, contact_id=contact_id)
        notify_owner(owner, f"New ticket #{ticket_id} for you: {subject}", f"{priority} priority, from {actor_name()}",
                     url_for("ticket", ticket_id=ticket_id))
        emit("ticket.created", ticket_id, value=priority)
        return ticket_id
    first_due, resolve_due = old["first_response_due"], old["resolution_due"]
    if priority != old["priority"]:
        first_due, resolve_due = sla_due(datetime.fromisoformat(old["created_at"]), priority)
    db.execute("UPDATE tickets SET subject=?, description=?, priority=?, category=?, source=?, owner=?, company_id=?, "
               "contact_id=?, first_response_due=?, resolution_due=?, custom=? WHERE id=? AND workspace_id=?",
               (subject, description, priority, pick("category", "Other"), pick("source", "Email"), owner, company_id,
                contact_id, first_due, resolve_due, custom, old["id"], ws()))
    log_event("Updated through the API", f"By {actor_name()}", ticket_id=old["id"], company_id=company_id,
              contact_id=contact_id)
    if data.get("status") and data["status"] != old["status"]:
        set_ticket_status(old["id"], data["status"])
    emit("ticket.updated", old["id"])
    return old["id"]


SAVERS = {"contacts": save_contact, "companies": save_company, "deals": save_deal, "tickets": save_ticket}


# --- The Power BI feed ------------------------------------------------------------------------------------------------

FEEDS = {
    "contacts": ("SELECT ct.id, ct.first_name, ct.last_name, ct.email, ct.phone, ct.role AS job_title, ct.company_id, "
                 "c.name AS company, ct.lifecycle_stage, ct.lead_status, ct.owner, ct.lawful_basis, ct.marketing_consent, "
                 "ct.created_at, ct.custom FROM contacts ct LEFT JOIN companies c ON c.id=ct.company_id "
                 "WHERE ct.workspace_id=? ORDER BY ct.id"),
    "companies": ("SELECT id, name, company_no, vat_no, industry, city, region, postcode, website, owner, created_at, custom "
                  "FROM companies WHERE workspace_id=? ORDER BY id"),
    "deals": ("SELECT d.id, d.title, d.company_id, c.name AS company, d.contact_id, d.value, d.stage, d.probability, "
              "d.owner, d.source, d.close_date, d.closed_at, d.created_at, d.custom FROM deals d "
              "JOIN companies c ON c.id=d.company_id WHERE d.workspace_id=? ORDER BY d.id"),
    "tickets": ("SELECT t.id, t.subject, t.status, t.priority, t.category, t.source, t.owner, t.company_id, "
                "c.name AS company, t.contact_id, t.created_at, t.first_response_due, t.resolution_due, "
                "t.first_responded_at, t.closed_at, t.custom FROM tickets t LEFT JOIN companies c ON c.id=t.company_id "
                "WHERE t.workspace_id=? ORDER BY t.id"),
    "invoices": ("SELECT i.id, i.number, i.company_id, c.name AS company, i.deal_id, i.description, i.net, i.vat, "
                 "i.issue_date, i.due_date, i.paid_date FROM invoices i JOIN companies c ON c.id=i.company_id "
                 "WHERE i.workspace_id=? ORDER BY i.id"),
    "tasks": ("SELECT id, kind, subject, owner, due_at, done, company_id, contact_id, deal_id, ticket_id "
              "FROM activities WHERE workspace_id=? ORDER BY id"),
}


def feed_rows(name):
    """(columns, rows) for reporting: pounds rather than pence, yes/no as true/false, custom fields as columns."""
    obj = name if name in ("contacts", "companies", "deals", "tickets") else None
    from fields import definitions, display, values
    extra = definitions(obj) if obj else []
    cursor = get_db().execute(FEEDS[name] + f" LIMIT {FEED_LIMIT}", (ws(),))
    names = [d[0] for d in cursor.description]
    columns = [f"{n}_gbp" if n in ("value", "net", "vat") else n for n in names if n != "custom"]
    columns += {"deals": ["weighted_value_gbp"], "invoices": ["gross_gbp", "status"]}.get(name, [])
    columns += [f["label"] for f in extra]
    out = []
    for row in cursor.fetchall():
        item = {}
        for key in names:
            value = row[key]
            if key == "custom":
                continue
            if key in ("value", "net", "vat"):
                item[f"{key}_gbp"] = value / 100
                continue
            if key in ("marketing_consent", "done"):
                value = bool(value)
            item[key] = value
        if name == "deals":
            item["weighted_value_gbp"] = round(row["value"] * row["probability"] / 10000, 2)
        if name == "invoices":
            item["gross_gbp"] = (row["net"] + row["vat"]) / 100
            item["status"] = "Paid" if row["paid_date"] else "Overdue" if row["due_date"] < today().isoformat() else "Due"
        if extra:
            saved = values(row)
            for f in extra:
                value = saved.get(str(f["id"]))
                item[f["label"]] = value if f["field_type"] in ("number", "yes_no") else display(f, value)
        out.append(item)
    return columns, out


def feed_safe(value):
    """Keep spreadsheet apps from running a cell as a formula, without spoiling numbers and phone numbers."""
    if not isinstance(value, str) or not value:
        return value
    if value[0] in "=@\t\r" or (value[0] in "+-" and re.search(r"[^\d\s().+-]", value)):
        return "'" + value
    return value


# --- Routes -------------------------------------------------------------------------------------------------------

def error(status, message, fields=None, headers=None):
    payload = {"error": message}
    if fields:
        payload["fields"] = fields
    resp = jsonify(payload)
    resp.status_code = status
    for k, v in (headers or {}).items():
        resp.headers[k] = v
    return resp


@bp.before_request
def authenticate():
    g.user = None
    raw = presented_key()
    key = one("SELECT * FROM api_keys WHERE key_hash=?", digest(raw)) if raw else None
    if key is None:
        return error(401, "Send a valid API key as 'Authorization: Bearer <key>'. Admins make keys in Settings > API "
                          "and webhooks.", headers={"WWW-Authenticate": 'Basic realm="CAE CRM API"'})
    clock = datetime.now(timezone.utc)
    minute = clock.strftime("%Y-%m-%dT%H:%M")
    count = key["window_count"] + 1 if key["window_start"] == minute else 1
    limit = current_app.config.get("API_RATE_LIMIT", 120)
    if count > limit:
        return error(429, f"Too many requests. Each key can make {limit} a minute.",
                     headers={"Retry-After": str(60 - clock.second)})
    db = get_db()
    db.execute("UPDATE api_keys SET window_start=?, window_count=?, last_used_at=? WHERE id=?",
               (minute, count, now().isoformat(timespec="minutes"), key["id"]))
    db.commit()
    g.api_key, g.public_workspace = key, key["workspace_id"]
    if request.method in ("POST", "PATCH", "PUT", "DELETE"):
        if key["access"] != "write":
            return error(403, "This key can only read. Make a key with write access to add or change records.")
        import billing
        if not billing.state(workspace())["can_write"]:
            return error(402, "This workspace is read-only until someone subscribes. An admin can do this under Billing.")
    return None


@bp.errorhandler(ApiError)
def api_error(e):
    get_db().rollback()
    return error(e.status, e.message, e.fields)


@bp.errorhandler(HTTPException)
def http_error(e):
    return error(e.code, e.description if e.code != 404 else "Not found.")


@bp.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.get("/")
def index():
    w = workspace()
    return jsonify(workspace=w["name"], key=g.api_key["name"], access=g.api_key["access"], objects=list(FILTERS),
                   writable=list(WRITABLE), feeds=list(FEEDS),
                   rate_limit_per_minute=current_app.config.get("API_RATE_LIMIT", 120))


@bp.get("/<obj>")
def list_records(obj):
    if obj not in FILTERS:
        raise ApiError(404, f"There's no {obj} here. Try contacts, companies, deals, tickets or invoices.")
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(MAX_PER_PAGE, max(1, int(request.args.get("per_page", PER_PAGE))))
    except ValueError:
        raise ApiError(400, "page and per_page must be whole numbers.") from None
    where, args = ["workspace_id=?"], [ws()]
    for name in FILTERS[obj]:
        given = request.args.get(name)
        if not given:
            continue
        if name.endswith("_id"):
            if not given.isdigit():
                raise ApiError(400, f"{name} must be a number.")
            given = int(given)
        where.append(f"{name}=?")
        args.append(given.lower() if name == "email" else given)
    since = request.args.get("created_since")
    if since:
        try:
            date.fromisoformat(since)
        except ValueError:
            raise ApiError(400, "created_since must be a date like 2026-10-01.") from None
        where.append(("issue_date" if obj == "invoices" else "created_at") + " >= ?")
        args.append(since)
    sql = " AND ".join(where)
    total = scalar(f"SELECT COUNT(*) FROM {obj} WHERE {sql}", *args)
    found = rows(f"SELECT * FROM {obj} WHERE {sql} ORDER BY id LIMIT {per_page} OFFSET {(page - 1) * per_page}", *args)
    return jsonify(data=[serialise(obj, r) for r in found], page=page, per_page=per_page, total=total,
                   has_more=page * per_page < total)


@bp.get("/<obj>/<int:record_id>")
def get_record(obj, record_id):
    if obj not in FILTERS:
        raise ApiError(404, "Not found.")
    return jsonify(serialise(obj, record(obj, record_id)))


@bp.post("/<obj>")
def create_record(obj):
    if obj not in WRITABLE:
        raise ApiError(405 if obj in FILTERS else 404, f"{obj.capitalize()} can't be added through the API.")
    record_id = SAVERS[obj](body())
    get_db().commit()
    audit(f"Added a {PAGES[obj]} through the API", obj, record_id)
    resp = jsonify(serialise(obj, record(obj, record_id)))
    resp.status_code = 201
    resp.headers["Location"] = url_for("api.get_record", obj=obj, record_id=record_id, _external=True)
    return resp


@bp.patch("/<obj>/<int:record_id>")
def update_record(obj, record_id):
    if obj not in WRITABLE:
        raise ApiError(405 if obj in FILTERS else 404, f"{obj.capitalize()} can't be changed through the API.")
    old = record(obj, record_id)
    SAVERS[obj](body(), old)
    get_db().commit()
    audit(f"Changed a {PAGES[obj]} through the API", obj, record_id)
    return jsonify(serialise(obj, record(obj, record_id)))


@bp.get("/feed/<name>")
def feed(name):
    if name not in FEEDS:
        raise ApiError(404, f"There's no {name} feed. Try: {', '.join(FEEDS)}.")
    columns, data = feed_rows(name)
    if request.args.get("format") == "json":
        return jsonify(data)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(columns)
    for item in data:
        writer.writerow([feed_safe(item.get(c)) for c in columns])
    return Response("﻿" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'inline; filename="{name}.csv"'})


# --- Settings page: keys --------------------------------------------------------------------------------------------

def register(app):
    app.register_blueprint(bp)

    @app.errorhandler(404)
    @app.errorhandler(405)
    def api_not_found(e):
        if request.path.startswith("/api/v1/"):
            return error(e.code, "Not found." if e.code == 404 else "That method isn't allowed here.")
        return e

    def developers_page(new_key=None):
        import webhooks
        hooks = rows("SELECT * FROM webhooks WHERE workspace_id=? ORDER BY id", ws())
        recent = {h["id"]: rows("SELECT id, event, status, attempts, response_code, last_error, created_at "
                                "FROM webhook_deliveries WHERE webhook_id=? ORDER BY id DESC LIMIT 8", h["id"])
                  for h in hooks}
        return render_template("developers.html", keys=rows("SELECT * FROM api_keys WHERE workspace_id=? ORDER BY id", ws()),
                               hooks=hooks, recent=recent, events=webhooks.EVENT_CHOICES, feeds=list(FEEDS),
                               new_key=new_key, base=url_for("api.index", _external=True))

    @app.get("/settings/api")
    def developers():
        auth.admin_required()
        return developers_page()

    @app.post("/settings/api/keys")
    def create_api_key():
        auth.admin_required()
        name = request.form.get("name", "").strip()[:60]
        access = request.form.get("access")
        if not name or access not in ("read", "write"):
            flash("Key not made. Give it a name and choose what it can do.", "error")
            return redirect(url_for("developers"))
        if scalar("SELECT COUNT(*) FROM api_keys WHERE workspace_id=?", ws()) >= MAX_KEYS:
            flash(f"Key not made. A workspace can have up to {MAX_KEYS} keys; revoke one you no longer use.", "error")
            return redirect(url_for("developers"))
        raw = new_key()
        db = get_db()
        db.insert("api_keys", workspace_id=ws(), name=name, prefix=raw[:10], key_hash=digest(raw), access=access,
                  created_by=g.user["name"], created_at=now().isoformat(timespec="minutes"))
        db.commit()
        # Shown once, on this response only: only its hash is stored, so it can't be read back later.
        resp = developers_page(new_key=dict(name=name, raw=raw))
        return resp, 200, {"Cache-Control": "no-store"}

    @app.post("/settings/api/keys/<int:key_id>/revoke")
    def revoke_api_key(key_id):
        auth.admin_required()
        db = get_db()
        db.execute("DELETE FROM api_keys WHERE id=? AND workspace_id=?", (key_id, ws()))
        db.commit()
        flash("Key revoked. Anything using it will stop working straight away.", "ok")
        return redirect(url_for("developers"))
