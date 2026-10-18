"""What the AI assistant can look up and suggest. Every lookup is limited to the signed-in user's workspace through the
helpers in core.py, and returns plain data for the model. Suggestions change nothing: they come back to the person as a
form with a Confirm button, which posts to the same page a person would use (see assistant.py).

Admin-only areas (the audit trail, API keys, billing, bank details) have no tools, so the assistant can't reach them."""

import json
from datetime import date, timedelta

from flask import g

import fields
import tags
from core import OPEN_SQL, now, one, owned, owner_names, rows, scalar, today, ws
from db import ACTIVITY_KINDS, OPEN_STAGES, STAGE_PROBABILITY, TICKET_PRIORITIES, TICKET_STATUSES
from ukfmt import money

LIMIT = 25  # rows per list, so one answer can't pull in the whole database

# Records the assistant can open, and how to link to them: kind -> (table, page endpoint, URL argument).
KINDS = {
    "contact": ("contacts", "contact", "contact_id"),
    "company": ("companies", "company", "company_id"),
    "deal": ("deals", "deal", "deal_id"),
    "ticket": ("tickets", "ticket", "ticket_id"),
    "quote": ("quotes", "quote", "quote_id"),
    "invoice": ("invoices", "invoice", "invoice_id"),
}
LINK_FIELDS = {"company_id": "company", "contact_id": "contact", "deal_id": "deal", "ticket_id": "ticket"}


def _schema(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


_ID = {"type": "integer", "description": "The record's number, from a search or list."}
_LINKS = {name: {"type": "integer", "description": f"The {kind}'s number, to link it to."}
          for name, kind in LINK_FIELDS.items()}

TOOLS = [
    {"name": "search_records",
     "description": "Find contacts, companies, deals, tickets, quotes and invoices by name, email, title, number, "
                    "city or postcode. Use it to turn a name the person mentions into a record number.",
     "input_schema": _schema({"query": {"type": "string", "description": "At least 2 characters."}}, ["query"])},
    {"name": "get_record",
     "description": "Everything about one record: its details, custom fields, linked records, open tasks and its "
                    "recent activity timeline (notes, calls, emails, meetings).",
     "input_schema": _schema({"kind": {"type": "string", "enum": list(KINDS)}, "id": _ID}, ["kind", "id"])},
    {"name": "list_deals",
     "description": "Deals, largest first, with totals. Closing dates are YYYY-MM-DD.",
     "input_schema": _schema({
         "stage": {"type": "string", "enum": [*OPEN_STAGES, "Won", "Lost", "open"],
                   "description": "A stage, or 'open' for every stage except Won and Lost."},
         "owner": {"type": "string", "description": "A team member's name."},
         "company_id": _LINKS["company_id"],
         "closing_from": {"type": "string"}, "closing_to": {"type": "string"},
     })},
    {"name": "list_tickets",
     "description": "Support tickets, newest first, with whether each is past its service level.",
     "input_schema": _schema({
         "status": {"type": "string", "enum": [*TICKET_STATUSES, "open"],
                    "description": "A status, or 'open' for everything not Closed."},
         "priority": {"type": "string", "enum": TICKET_PRIORITIES},
         "owner": {"type": "string"}, "company_id": _LINKS["company_id"],
     })},
    {"name": "list_invoices",
     "description": "Invoices, with totals in pounds including VAT.",
     "input_schema": _schema({
         "status": {"type": "string", "enum": ["unpaid", "overdue", "paid", "all"]},
         "company_id": _LINKS["company_id"],
     })},
    {"name": "list_quotes",
     "description": "Quotes and where each stands (draft, sent, accepted, declined).",
     "input_schema": _schema({"status": {"type": "string"}, "company_id": _LINKS["company_id"]})},
    {"name": "list_tasks",
     "description": "Tasks (calls, meetings, emails and to-dos). By default, open tasks due up to 7 days from today, "
                    "including overdue ones.",
     "input_schema": _schema({
         "owner": {"type": "string", "description": "A team member's name. Use the person's own name for 'my tasks'."},
         "due_to": {"type": "string", "description": "YYYY-MM-DD, latest due date to include."},
         "include_done": {"type": "boolean"},
     })},
    {"name": "workspace_summary",
     "description": "Headline numbers: open pipeline by stage, won this month against the target, open and overdue "
                    "tickets, unpaid and overdue invoices, tasks due, and the team's names.",
     "input_schema": _schema({})},
    {"name": "suggest_task",
     "description": "Suggest a task for the person to confirm. Nothing is created until they press Confirm.",
     "input_schema": _schema({
         "subject": {"type": "string"},
         "kind": {"type": "string", "enum": ACTIVITY_KINDS},
         "due_date": {"type": "string", "description": "YYYY-MM-DD"},
         "due_time": {"type": "string", "description": "HH:MM, 24-hour UK time. Default 09:00."},
         "owner": {"type": "string", "description": "A team member's name. Default: the person asking."},
         **_LINKS,
     }, ["subject", "kind", "due_date"])},
    {"name": "suggest_note",
     "description": "Suggest a note for a record's timeline, for the person to confirm. Link at least one record. "
                    "Nothing is saved until they press Confirm.",
     "input_schema": _schema({"body": {"type": "string"}, "subject": {"type": "string"}, **_LINKS}, ["body"])},
    {"name": "suggest_deal_stage",
     "description": "Suggest moving a deal to another stage, for the person to confirm. Nothing changes until they "
                    "press Confirm.",
     "input_schema": _schema({"deal_id": _ID, "stage": {"type": "string", "enum": list(STAGE_PROBABILITY)}},
                             ["deal_id", "stage"])},
]
SUGGESTIONS = {"suggest_task", "suggest_note", "suggest_deal_stage"}


class ToolError(Exception):
    """A tool couldn't do what was asked. The message goes back to the model."""


def _date(value, name):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        raise ToolError(f"{name} must be a date like 2026-10-31.") from None


def _owned(kind, value):
    table = KINDS[kind][0]
    record_id = owned(table, value)
    if record_id is None:
        raise ToolError(f"There's no {kind} number {value} in this workspace.")
    return record_id


def _gbp(pence):
    return money(pence or 0)


def _person(r, prefix=""):
    first, last = r[f"{prefix}first_name"], r[f"{prefix}last_name"]
    return f"{first} {last}".strip() if first or last else None


def _custom(obj, record):
    values = fields.values(record)
    out = {}
    for f in fields.definitions(obj):
        shown = fields.display(f, values.get(str(f["id"])))
        if shown is not None:
            out[f["label"]] = shown
    return out


def _timeline(link, record_id):
    found = rows(f"SELECT kind, subject, body, outcome, author, occurred_at FROM engagements "
                 f"WHERE workspace_id=? AND {link}=? ORDER BY occurred_at DESC, id DESC LIMIT 15", ws(), record_id)
    return [{k: r[k] for k in ("kind", "subject", "body", "outcome", "author", "occurred_at") if r[k]} for r in found]


def _open_tasks(link, record_id):
    found = rows(f"SELECT id, kind, subject, owner, due_at FROM activities WHERE workspace_id=? AND {link}=? AND done=0 "
                 f"ORDER BY due_at LIMIT 10", ws(), record_id)
    return [dict(r) for r in found]


# --- Lookups --------------------------------------------------------------------------------------------------------

def search_records(query):
    q = str(query or "").strip().lower()
    if len(q) < 2:
        raise ToolError("Search for at least 2 characters.")
    like = f"%{q}%"
    out = []
    for r in rows("SELECT ct.id, ct.first_name, ct.last_name, ct.email, c.name AS company FROM contacts ct "
                  "LEFT JOIN companies c ON c.id=ct.company_id WHERE ct.workspace_id=? AND "
                  "(LOWER(ct.first_name || ' ' || ct.last_name) LIKE ? OR LOWER(ct.email) LIKE ?) "
                  "ORDER BY ct.first_name LIMIT 8", ws(), like, like):
        out.append(dict(kind="contact", id=r["id"], name=_person(r), email=r["email"], company=r["company"]))
    for r in rows("SELECT id, name, city, postcode FROM companies WHERE workspace_id=? AND (LOWER(name) LIKE ? "
                  "OR LOWER(city) LIKE ? OR LOWER(postcode) LIKE ?) ORDER BY name LIMIT 8", ws(), like, like, like):
        out.append(dict(kind="company", id=r["id"], name=r["name"], city=r["city"], postcode=r["postcode"]))
    for r in rows("SELECT d.id, d.title, d.stage, d.value, c.name AS company FROM deals d JOIN companies c ON "
                  "c.id=d.company_id WHERE d.workspace_id=? AND (LOWER(d.title) LIKE ? OR LOWER(c.name) LIKE ?) "
                  "ORDER BY d.value DESC LIMIT 8", ws(), like, like):
        out.append(dict(kind="deal", id=r["id"], title=r["title"], stage=r["stage"], value=_gbp(r["value"]),
                        company=r["company"]))
    for r in rows("SELECT id, subject, status, priority FROM tickets WHERE workspace_id=? AND LOWER(subject) LIKE ? "
                  "ORDER BY id DESC LIMIT 8", ws(), like):
        out.append(dict(kind="ticket", id=r["id"], subject=r["subject"], status=r["status"], priority=r["priority"]))
    for r in rows("SELECT q.id, q.number, q.title, q.status, c.name AS company FROM quotes q JOIN companies c ON "
                  "c.id=q.company_id WHERE q.workspace_id=? AND (LOWER(q.number) LIKE ? OR LOWER(q.title) LIKE ?) "
                  "ORDER BY q.id DESC LIMIT 8", ws(), like, like):
        out.append(dict(kind="quote", id=r["id"], number=r["number"], title=r["title"], status=r["status"],
                        company=r["company"]))
    for r in rows("SELECT i.id, i.number, i.description, i.paid_date, c.name AS company FROM invoices i JOIN companies c "
                  "ON c.id=i.company_id WHERE i.workspace_id=? AND (LOWER(i.number) LIKE ? OR LOWER(i.description) LIKE ?) "
                  "ORDER BY i.id DESC LIMIT 8", ws(), like, like):
        out.append(dict(kind="invoice", id=r["id"], number=r["number"], description=r["description"],
                        paid=bool(r["paid_date"]), company=r["company"]))
    return {"results": out} if out else {"results": [], "note": "Nothing matched."}


def get_record(kind, id):
    if kind not in KINDS:
        raise ToolError("Unknown kind of record.")
    record_id = _owned(kind, id)
    return globals()[f"_get_{kind}"](record_id)


def _get_contact(record_id):
    r = one("SELECT ct.*, c.name AS company FROM contacts ct LEFT JOIN companies c ON c.id=ct.company_id "
            "WHERE ct.id=? AND ct.workspace_id=?", record_id, ws())
    return {
        "kind": "contact", "id": r["id"], "name": _person(r), "job_title": r["role"], "email": r["email"],
        "phone": r["phone"], "company": {"id": r["company_id"], "name": r["company"]} if r["company_id"] else None,
        "owner": r["owner"], "lifecycle_stage": r["lifecycle_stage"], "lead_status": r["lead_status"],
        "lawful_basis": r["lawful_basis"], "marketing_consent": bool(r["marketing_consent"]),
        "unsubscribed": bool(r["unsubscribed_at"]), "added": r["created_at"], "custom_fields": _custom("contacts", r),
        "tags": [t["name"] for t in tags.tags_of("contact", record_id)],
        "deals": [dict(d, value=_gbp(d["value"])) for d in rows(
            "SELECT id, title, stage, value FROM deals WHERE workspace_id=? AND contact_id=? ORDER BY id DESC LIMIT 10",
            ws(), record_id)],
        "tickets": [dict(t) for t in rows("SELECT id, subject, status FROM tickets WHERE workspace_id=? AND contact_id=? "
                                          "ORDER BY id DESC LIMIT 10", ws(), record_id)],
        "open_tasks": _open_tasks("contact_id", record_id), "timeline": _timeline("contact_id", record_id),
    }


def _get_company(record_id):
    r = one("SELECT * FROM companies WHERE id=? AND workspace_id=?", record_id, ws())
    return {
        "kind": "company", "id": r["id"], "name": r["name"], "industry": r["industry"], "website": r["website"],
        "phone": r["phone"], "address": ", ".join(filter(None, [r["address"], r["city"], r["postcode"]])),
        "region": r["region"], "company_number": r["company_no"], "vat_number": r["vat_no"], "owner": r["owner"],
        "added": r["created_at"], "custom_fields": _custom("companies", r),
        "tags": [t["name"] for t in tags.tags_of("company", record_id)],
        "contacts": [dict(id=c["id"], name=_person(c), job_title=c["role"], email=c["email"]) for c in rows(
            "SELECT id, first_name, last_name, role, email FROM contacts WHERE workspace_id=? AND company_id=? "
            "ORDER BY first_name LIMIT 20", ws(), record_id)],
        "deals": [dict(d, value=_gbp(d["value"])) for d in rows(
            "SELECT id, title, stage, value, close_date FROM deals WHERE workspace_id=? AND company_id=? "
            "ORDER BY id DESC LIMIT 10", ws(), record_id)],
        "tickets": [dict(t) for t in rows("SELECT id, subject, status, priority FROM tickets WHERE workspace_id=? AND "
                                          "company_id=? ORDER BY id DESC LIMIT 10", ws(), record_id)],
        "unpaid_invoices": [dict(number=i["number"], id=i["id"], total=_gbp(i["net"] + i["vat"]), due=i["due_date"])
                            for i in rows("SELECT id, number, net, vat, due_date FROM invoices WHERE workspace_id=? AND "
                                          "company_id=? AND paid_date IS NULL ORDER BY due_date", ws(), record_id)],
        "open_tasks": _open_tasks("company_id", record_id), "timeline": _timeline("company_id", record_id),
    }


def _get_deal(record_id):
    r = one("SELECT d.*, c.name AS company, ct.first_name, ct.last_name FROM deals d JOIN companies c ON c.id=d.company_id "
            "LEFT JOIN contacts ct ON ct.id=d.contact_id WHERE d.id=? AND d.workspace_id=?", record_id, ws())
    return {
        "kind": "deal", "id": r["id"], "title": r["title"], "value": _gbp(r["value"]), "stage": r["stage"],
        "probability_percent": r["probability"], "owner": r["owner"], "source": r["source"],
        "close_date": r["close_date"], "closed_on": r["closed_at"], "added": r["created_at"],
        "won_or_lost_because": r["outcome_reason"], "outcome_note": r["outcome_note"],
        "company": {"id": r["company_id"], "name": r["company"]},
        "contact": {"id": r["contact_id"], "name": _person(r)} if r["contact_id"] else None,
        "custom_fields": _custom("deals", r),
        "line_items": [dict(name=li["name"], quantity=li["quantity"], unit_price=_gbp(li["unit_price"]),
                            discount_percent=li["discount_pct"], vat_rate=li["vat_rate"])
                       for li in rows("SELECT * FROM line_items WHERE workspace_id=? AND deal_id=? ORDER BY id",
                                      ws(), record_id)],
        "quotes": [dict(q) for q in rows("SELECT id, number, status FROM quotes WHERE workspace_id=? AND deal_id=? "
                                         "ORDER BY id DESC", ws(), record_id)],
        "open_tasks": _open_tasks("deal_id", record_id), "timeline": _timeline("deal_id", record_id),
    }


def _get_ticket(record_id):
    from core import sla_state
    r = one("SELECT t.*, c.name AS company, ct.first_name, ct.last_name FROM tickets t LEFT JOIN companies c ON "
            "c.id=t.company_id LEFT JOIN contacts ct ON ct.id=t.contact_id WHERE t.id=? AND t.workspace_id=?",
            record_id, ws())
    return {
        "kind": "ticket", "id": r["id"], "subject": r["subject"], "description": r["description"],
        "status": r["status"], "priority": r["priority"], "category": r["category"], "source": r["source"],
        "owner": r["owner"], "opened": r["created_at"], "closed": r["closed_at"],
        "first_response": sla_state(r["first_response_due"], r["first_responded_at"])[1],
        "resolution": sla_state(r["resolution_due"], r["closed_at"])[1],
        "company": {"id": r["company_id"], "name": r["company"]} if r["company_id"] else None,
        "contact": {"id": r["contact_id"], "name": _person(r)} if r["contact_id"] else None,
        "custom_fields": _custom("tickets", r),
        "open_tasks": _open_tasks("ticket_id", record_id), "timeline": _timeline("ticket_id", record_id),
    }


def _get_quote(record_id):
    r = one("SELECT q.*, c.name AS company FROM quotes q JOIN companies c ON c.id=q.company_id "
            "WHERE q.id=? AND q.workspace_id=?", record_id, ws())
    return {
        "kind": "quote", "id": r["id"], "number": r["number"], "title": r["title"], "status": r["status"],
        "net": _gbp(r["net"]), "vat": _gbp(r["vat"]), "total": _gbp(r["net"] + r["vat"]), "issued": r["issue_date"],
        "expires": r["expiry_date"], "sent": r["sent_at"], "viewed": r["viewed_at"], "decided": r["decided_at"],
        "decline_reason": r["decline_reason"], "terms": r["terms"], "created_by": r["created_by"],
        "company": {"id": r["company_id"], "name": r["company"]}, "deal_id": r["deal_id"],
        "lines": [dict(description=li["description"], quantity=li["quantity"], unit_price=_gbp(li["unit_price"]),
                       discount_percent=li["discount_pct"], vat_rate=li["vat_rate"])
                  for li in rows("SELECT * FROM quote_lines WHERE workspace_id=? AND quote_id=? ORDER BY id",
                                 ws(), record_id)],
    }


def _get_invoice(record_id):
    r = one("SELECT i.*, c.name AS company FROM invoices i JOIN companies c ON c.id=i.company_id "
            "WHERE i.id=? AND i.workspace_id=?", record_id, ws())
    overdue = not r["paid_date"] and r["due_date"] < today().isoformat()
    return {
        "kind": "invoice", "id": r["id"], "number": r["number"], "description": r["description"],
        "net": _gbp(r["net"]), "vat": _gbp(r["vat"]), "total": _gbp(r["net"] + r["vat"]), "vat_rate": r["vat_rate"],
        "issued": r["issue_date"], "due": r["due_date"], "paid": r["paid_date"], "overdue": overdue,
        "emailed": r["sent_at"], "company": {"id": r["company_id"], "name": r["company"]}, "deal_id": r["deal_id"],
    }


def list_deals(stage=None, owner=None, company_id=None, closing_from=None, closing_to=None):
    sql = ("SELECT d.id, d.title, d.value, d.stage, d.owner, d.close_date, c.name AS company FROM deals d "
           "JOIN companies c ON c.id=d.company_id WHERE d.workspace_id=?")
    args = [ws()]
    if stage == "open":
        sql += " AND d." + OPEN_SQL
    elif stage:
        sql += " AND d.stage=?"
        args.append(stage)
    if owner:
        sql += " AND d.owner=?"
        args.append(owner)
    if company_id:
        sql += " AND d.company_id=?"
        args.append(_owned("company", company_id))
    for value, op, name in ((closing_from, ">=", "closing_from"), (closing_to, "<=", "closing_to")):
        if value:
            sql += f" AND d.close_date {op} ?"
            args.append(_date(value, name))
    found = rows(sql + " ORDER BY d.value DESC", *args)
    return {"count": len(found), "total_value": _gbp(sum(d["value"] for d in found)),
            "deals": [dict(d, value=_gbp(d["value"])) for d in found[:LIMIT]],
            **({"note": f"Showing the largest {LIMIT}."} if len(found) > LIMIT else {})}


def list_tickets(status=None, priority=None, owner=None, company_id=None):
    from core import sla_state
    sql = ("SELECT t.id, t.subject, t.status, t.priority, t.owner, t.created_at, t.resolution_due, t.closed_at, "
           "c.name AS company FROM tickets t LEFT JOIN companies c ON c.id=t.company_id WHERE t.workspace_id=?")
    args = [ws()]
    if status == "open":
        sql += " AND t.status <> 'Closed'"
    elif status:
        sql += " AND t.status=?"
        args.append(status)
    for column, value in (("priority", priority), ("owner", owner)):
        if value:
            sql += f" AND t.{column}=?"
            args.append(value)
    if company_id:
        sql += " AND t.company_id=?"
        args.append(_owned("company", company_id))
    found = rows(sql + " ORDER BY t.id DESC", *args)
    out = [dict(id=t["id"], subject=t["subject"], status=t["status"], priority=t["priority"], owner=t["owner"],
                company=t["company"], opened=t["created_at"], resolution=sla_state(t["resolution_due"], t["closed_at"])[1])
           for t in found[:LIMIT]]
    return {"count": len(found), "tickets": out, **({"note": f"Showing the newest {LIMIT}."} if len(found) > LIMIT else {})}


def list_invoices(status="unpaid", company_id=None):
    sql = ("SELECT i.id, i.number, i.description, i.net, i.vat, i.issue_date, i.due_date, i.paid_date, c.name AS company "
           "FROM invoices i JOIN companies c ON c.id=i.company_id WHERE i.workspace_id=?")
    args = [ws()]
    if status in (None, "unpaid"):
        sql += " AND i.paid_date IS NULL"
    elif status == "overdue":
        sql += " AND i.paid_date IS NULL AND i.due_date < ?"
        args.append(today().isoformat())
    elif status == "paid":
        sql += " AND i.paid_date IS NOT NULL"
    if company_id:
        sql += " AND i.company_id=?"
        args.append(_owned("company", company_id))
    found = rows(sql + " ORDER BY i.due_date", *args)
    out = [dict(id=i["id"], number=i["number"], company=i["company"], description=i["description"],
                total=_gbp(i["net"] + i["vat"]), issued=i["issue_date"], due=i["due_date"], paid=i["paid_date"])
           for i in found[:LIMIT]]
    return {"count": len(found), "total_including_vat": _gbp(sum(i["net"] + i["vat"] for i in found)), "invoices": out,
            **({"note": f"Showing the first {LIMIT} by due date."} if len(found) > LIMIT else {})}


def list_quotes(status=None, company_id=None):
    sql = ("SELECT q.id, q.number, q.title, q.status, q.net, q.vat, q.issue_date, q.expiry_date, c.name AS company "
           "FROM quotes q JOIN companies c ON c.id=q.company_id WHERE q.workspace_id=?")
    args = [ws()]
    if status:
        sql += " AND LOWER(q.status)=?"
        args.append(str(status).lower())
    if company_id:
        sql += " AND q.company_id=?"
        args.append(_owned("company", company_id))
    found = rows(sql + " ORDER BY q.id DESC", *args)
    out = [dict(id=q["id"], number=q["number"], title=q["title"], status=q["status"], company=q["company"],
                total=_gbp(q["net"] + q["vat"]), issued=q["issue_date"], expires=q["expiry_date"]) for q in found[:LIMIT]]
    return {"count": len(found), "quotes": out, **({"note": f"Showing the newest {LIMIT}."} if len(found) > LIMIT else {})}


def list_tasks(owner=None, due_to=None, include_done=False):
    due_to = _date(due_to, "due_to") or (today() + timedelta(days=7)).isoformat()
    sql = ("SELECT a.id, a.kind, a.subject, a.owner, a.due_at, a.done, c.name AS company, d.title AS deal FROM activities a "
           "LEFT JOIN companies c ON c.id=a.company_id LEFT JOIN deals d ON d.id=a.deal_id "
           "WHERE a.workspace_id=? AND substr(a.due_at, 1, 10) <= ?")
    args = [ws(), due_to]
    if not include_done:
        sql += " AND a.done=0"
    if owner:
        sql += " AND a.owner=?"
        args.append(owner)
    found = rows(sql + " ORDER BY a.due_at", *args)
    now_text = now().isoformat(timespec="minutes")
    out = [dict(t, done=bool(t["done"]), overdue=not t["done"] and t["due_at"] < now_text) for t in found[:LIMIT]]
    return {"count": len(found), "tasks": out, **({"note": f"Showing the first {LIMIT}."} if len(found) > LIMIT else {})}


def workspace_summary():
    t = today()
    month_start = t.replace(day=1).isoformat()
    stages = [dict(stage=s, deals=r["n"], value=_gbp(r["v"])) for s in OPEN_STAGES
              for r in [one("SELECT COUNT(*) AS n, COALESCE(SUM(value), 0) AS v FROM deals WHERE workspace_id=? AND stage=?",
                            ws(), s)]]
    w = one("SELECT name, monthly_target FROM workspaces WHERE id=?", ws())
    team = rows("SELECT name, role, job_title FROM users WHERE workspace_id=? ORDER BY name", ws())
    return {
        "business": w["name"], "today": t.isoformat(),
        "open_pipeline": stages,
        "won_this_month": _gbp(scalar("SELECT SUM(value) FROM deals WHERE workspace_id=? AND stage='Won' AND closed_at >= ?",
                                      ws(), month_start)),
        "monthly_target": _gbp(w["monthly_target"]),
        "open_tickets": scalar("SELECT COUNT(*) FROM tickets WHERE workspace_id=? AND status <> 'Closed'", ws()),
        "unpaid_invoices": _gbp(scalar("SELECT SUM(net + vat) FROM invoices WHERE workspace_id=? AND paid_date IS NULL", ws())),
        "overdue_invoices": _gbp(scalar("SELECT SUM(net + vat) FROM invoices WHERE workspace_id=? AND paid_date IS NULL "
                                        "AND due_date < ?", ws(), t.isoformat())),
        "tasks_due_today_or_overdue": scalar("SELECT COUNT(*) FROM activities WHERE workspace_id=? AND done=0 AND "
                                             "substr(due_at, 1, 10) <= ?", ws(), t.isoformat()),
        "team": [dict(name=u["name"], role=u["role"], job_title=u["job_title"]) for u in team],
    }


# --- Suggestions ----------------------------------------------------------------------------------------------------

def _links(args, need_one=False):
    links = {name: _owned(kind, args[name]) for name, kind in LINK_FIELDS.items() if args.get(name)}
    if need_one and not links:
        raise ToolError("Link the note to a contact, company, deal or ticket.")
    return links


def check_suggestion(name, args):
    """Validate a suggestion and return it tidied up, ready to show as a form. Raises ToolError."""
    if name == "suggest_task":
        subject = str(args.get("subject") or "").strip()
        if not subject:
            raise ToolError("A task needs a subject.")
        if args.get("kind") not in ACTIVITY_KINDS:
            raise ToolError(f"kind must be one of {', '.join(ACTIVITY_KINDS)}.")
        due_time = str(args.get("due_time") or "09:00")
        if len(due_time) != 5 or due_time[2] != ":" or not (due_time[:2] + due_time[3:]).isdigit():
            raise ToolError("due_time must look like 14:30.")
        owner = args.get("owner") or g.user["name"]
        if owner not in owner_names():
            raise ToolError(f"{owner} isn't on the team. Choose from: {', '.join(owner_names())}.")
        return dict(subject=subject[:200], kind=args["kind"], due_date=_date(args.get("due_date"), "due_date"),
                    due_time=due_time, owner=owner, **_links(args))
    if name == "suggest_note":
        body = str(args.get("body") or "").strip()
        if not body:
            raise ToolError("A note needs some text.")
        return dict(body=body[:5000], subject=str(args.get("subject") or "").strip()[:200], **_links(args, need_one=True))
    if name == "suggest_deal_stage":
        if args.get("stage") not in STAGE_PROBABILITY:
            raise ToolError("Unknown stage.")
        return dict(deal_id=_owned("deal", args.get("deal_id")), stage=args["stage"])
    raise ToolError("Unknown suggestion.")


LOOKUPS = {f.__name__: f for f in (search_records, get_record, list_deals, list_tickets, list_invoices, list_quotes,
                                   list_tasks, workspace_summary)}


def run(name, args):
    """Run one tool. Returns (result for the model as text, is_error)."""
    try:
        if name in SUGGESTIONS:
            check_suggestion(name, args)
            return ("Shown to the person as a suggestion with a Confirm button. Nothing has changed yet; it only "
                    "happens if they press Confirm, and they can edit it first."), False
        if name not in LOOKUPS:
            raise ToolError(f"There's no tool called {name}.")
        return json.dumps(LOOKUPS[name](**args), default=str, ensure_ascii=False), False
    except ToolError as e:
        return str(e), True
    except TypeError:
        return "Those inputs don't fit this tool. Check its description.", True


def record_name(kind, record_id):
    """A record's display name for a suggestion card, or None if it isn't in this workspace."""
    sql = {
        "contact": "SELECT first_name || ' ' || last_name FROM contacts WHERE id=? AND workspace_id=?",
        "company": "SELECT name FROM companies WHERE id=? AND workspace_id=?",
        "deal": "SELECT title FROM deals WHERE id=? AND workspace_id=?",
        "ticket": "SELECT subject FROM tickets WHERE id=? AND workspace_id=?",
    }[kind]
    found = one(sql, record_id, ws())
    return found[0] if found else None
