"""Helpers shared by every page. Anything that reads or writes business data goes through
these so it is always limited to the signed-in user's workspace."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from flask import abort, current_app, g, redirect, request, url_for

from db import LIFECYCLE_STAGES, OPEN_STAGES, get_db

UK_TZ = ZoneInfo("Europe/London")
OPEN_SQL = f"stage IN ({','.join(repr(s) for s in OPEN_STAGES)})"
# Tables whose rows carry a workspace_id, so a form can only point at the caller's own records.
OWNED_TABLES = {"companies", "contacts", "deals", "tickets", "products", "invoices", "activities", "projects",
                "engagements", "line_items", "saved_views", "imports", "users"}


def today():
    return current_app.config["TODAY"] or date.today()


def now():
    """Current UK local time (naive), the clock for tasks and ticket service levels."""
    fixed = current_app.config.get("NOW")
    if not fixed and current_app.config.get("TODAY"):
        fixed = datetime.combine(current_app.config["TODAY"], time(11))  # a pinned date gets a pinned clock
    return fixed or datetime.now(UK_TZ).replace(tzinfo=None, second=0, microsecond=0)


def ws():
    return g.user["workspace_id"]


def workspace():
    if "workspace" not in g:
        g.workspace = get_db().execute("SELECT * FROM workspaces WHERE id=?", (ws(),)).fetchone()
    return g.workspace


def plain(value):
    """PostgreSQL returns AVG and SUMs of BIGINT as Decimal."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


def scalar(sql, *args):
    return plain(get_db().execute(sql, args).fetchone()[0] or 0)


def rows(sql, *args):
    return get_db().execute(sql, args).fetchall()


def one(sql, *args):
    return get_db().execute(sql, args).fetchone()


def get_or_404(table, record_id):
    assert table in OWNED_TABLES
    row = one(f"SELECT * FROM {table} WHERE id=? AND workspace_id=?", record_id, ws())
    if row is None:
        abort(404)
    return row


def owned(table, value):
    """The id from a form field if it names one of this workspace's records, otherwise None."""
    assert table in OWNED_TABLES
    if not str(value or "").isdigit():
        return None
    row = one(f"SELECT id FROM {table} WHERE id=? AND workspace_id=?", int(value), ws())
    return row[0] if row else None


def owner_names():
    """People who can own records: the team, plus anyone already named on a deal."""
    names = {r[0] for r in rows("SELECT name FROM users WHERE workspace_id=?", ws())}
    names |= {r[0] for r in rows("SELECT DISTINCT owner FROM deals WHERE workspace_id=?", ws())}
    return sorted(names)


def chosen_owner(value):
    return value if value in owner_names() else g.user["name"]


def company_options():
    return rows("SELECT id, name FROM companies WHERE workspace_id=? ORDER BY name", ws())


def contact_options():
    return rows("SELECT ct.id, ct.first_name || ' ' || ct.last_name AS name, c.name AS company FROM contacts ct "
                "LEFT JOIN companies c ON c.id=ct.company_id WHERE ct.workspace_id=? ORDER BY ct.first_name, ct.last_name",
                ws())


def log_event(subject, body=None, *, kind="system", outcome=None, author=None, occurred_at=None,
              company_id=None, contact_id=None, deal_id=None, ticket_id=None):
    """Add an entry to the activity timeline of every record it mentions."""
    get_db().insert("engagements", workspace_id=ws(), kind=kind, subject=subject, body=body, outcome=outcome,
                    author=author or ("CAE CRM" if kind == "system" else g.user["name"]),
                    occurred_at=occurred_at or now().isoformat(timespec="minutes"),
                    company_id=company_id, contact_id=contact_id, deal_id=deal_id, ticket_id=ticket_id)


def advance_lifecycle(contact_id, stage, reason):
    """Move a contact forward through the lifecycle, never backward."""
    if not contact_id:
        return
    row = one("SELECT lifecycle_stage, company_id FROM contacts WHERE id=? AND workspace_id=?", contact_id, ws())
    if row is None:
        return
    current = row["lifecycle_stage"] if row["lifecycle_stage"] in LIFECYCLE_STAGES else "Subscriber"
    if LIFECYCLE_STAGES.index(stage) > LIFECYCLE_STAGES.index(current) and current != "Other":
        get_db().execute("UPDATE contacts SET lifecycle_stage=? WHERE id=?", (stage, contact_id))
        log_event(f"Lifecycle stage changed to {stage}", reason, contact_id=contact_id, company_id=row["company_id"])


def wants_json():
    return request.headers.get("X-Requested-With") == "fetch"


def safe_path(target, default):
    return target if target and target.startswith("/") and not target.startswith("//") else url_for(default)


def back(default, **kwargs):
    target = request.form.get("next") or ""
    if target.startswith("/") and not target.startswith("//"):
        return redirect(target)
    return redirect(url_for(default, **kwargs))


def days_until(value):
    from ukfmt import to_date
    days = (to_date(value) - today()).days
    if days == 0:
        return "today"
    if days == 1:
        return "tomorrow"
    if days == -1:
        return "yesterday"
    return f"in {days} days" if days > 0 else f"{-days} days ago"


def relative_time(value):
    """'in 3h', '2 days ago' style wording for a datetime string."""
    if not value:
        return ""
    then = datetime.fromisoformat(str(value))
    delta = then - now()
    minutes = int(delta.total_seconds() // 60)
    future = minutes >= 0
    minutes = abs(minutes)
    if minutes < 60:
        text = f"{minutes}m"
    elif minutes < 60 * 24:
        text = f"{minutes // 60}h"
    else:
        text = f"{minutes // (60 * 24)} days"
    return f"in {text}" if future else f"{text} ago"


def sla_state(due, met_at=None):
    """('met' | 'breached' | 'due' | 'overdue', wording) for a ticket service level."""
    due_dt = datetime.fromisoformat(due)
    if met_at:
        return ("met", "Met") if datetime.fromisoformat(met_at) <= due_dt else ("breached", "Missed")
    if due_dt < now():
        return "overdue", f"Overdue by {relative_time(due).replace(' ago', '')}"
    soon = due_dt - now() <= timedelta(hours=2)
    return ("soon" if soon else "due"), f"Due {relative_time(due)}"
