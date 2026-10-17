"""Tickets: a help desk with service levels measured in UK working hours."""

from collections import defaultdict
from datetime import datetime, timedelta

from flask import abort, flash, g, jsonify, redirect, render_template, request, url_for

from core import (back, chosen_owner, get_or_404, log_event, now, one, owned, rows, sla_state, wants_json, ws)
from crm import render_index, timeline
from db import (CALL_OUTCOMES, TICKET_CATEGORIES, TICKET_PRIORITIES, TICKET_SLA_HOURS, TICKET_SOURCES,
                TICKET_STATUSES, get_db)
from ukfmt import add_working_hours


def sla_due(opened, priority):
    first, resolve = TICKET_SLA_HOURS[priority]
    return (add_working_hours(opened, first).isoformat(timespec="minutes"),
            add_working_hours(opened, resolve).isoformat(timespec="minutes"))


def set_ticket_status(ticket_id, status):
    """Change a ticket's status, recording the first response and closure for its service levels."""
    t = get_or_404("tickets", ticket_id)
    if status == t["status"]:
        return t
    stamp = now().isoformat(timespec="minutes")
    first = t["first_responded_at"] or (stamp if status != "New" else None)
    closed = stamp if status == "Closed" else None
    get_db().execute("UPDATE tickets SET status=?, first_responded_at=?, closed_at=? WHERE id=? AND workspace_id=?",
                     (status, first, closed, ticket_id, ws()))
    subject = "Ticket closed" if status == "Closed" else ("Ticket reopened" if t["status"] == "Closed" else f"Status changed to {status}")
    log_event(subject, f"By {g.user['name']}", ticket_id=ticket_id, company_id=t["company_id"], contact_id=t["contact_id"])
    return t


def decorate(ticket):
    """A ticket with its service-level states worked out."""
    first = sla_state(ticket["first_response_due"], ticket["first_responded_at"])
    resolve = sla_state(ticket["resolution_due"], ticket["closed_at"])
    worst = "breached" if "breached" in (first[0], resolve[0]) or "overdue" in (first[0], resolve[0]) else \
        ("soon" if "soon" in (first[0], resolve[0]) else "ok")
    return dict(ticket) | {"sla_first": first, "sla_resolve": resolve, "sla_worst": worst}


def register(app):

    @app.route("/tickets")
    def tickets():
        if request.args.get("view") == "list":
            return render_index("tickets", "tickets.html", statuses=TICKET_STATUSES, decorate=decorate)
        owner = request.args.get("owner", "")
        sql = ("SELECT t.*, c.name AS company FROM tickets t LEFT JOIN companies c ON c.id=t.company_id"
               " WHERE t.workspace_id=? AND (t.status <> 'Closed' OR t.closed_at >= ?)")
        # The Closed column shows the last 14 days.
        args = [ws(), (now().replace(hour=0, minute=0) - timedelta(days=14)).isoformat(timespec="minutes")]
        if owner:
            sql += " AND t.owner=?"
            args.append(owner)
        columns = defaultdict(list)
        for t in rows(sql + " ORDER BY t.resolution_due", *args):
            columns[t["status"]].append(decorate(t))
        return render_template("tickets_board.html", columns=columns, statuses=TICKET_STATUSES, owner=owner)

    @app.post("/tickets")
    def create_ticket():
        f = request.form
        subject = f.get("subject", "").strip()
        priority = f.get("priority") if f.get("priority") in TICKET_PRIORITIES else "Medium"
        if not subject:
            flash("Ticket not created. Give it a subject.", "error")
            return back("tickets")
        contact_id = owned("contacts", f.get("contact_id"))
        company_id = owned("companies", f.get("company_id"))
        if contact_id and not company_id:
            company_id = one("SELECT company_id FROM contacts WHERE id=?", contact_id)["company_id"]
        opened = now()
        first_due, resolve_due = sla_due(opened, priority)
        db = get_db()
        owner = chosen_owner(f.get("owner"))
        ticket_id = db.insert("tickets", workspace_id=ws(), company_id=company_id, contact_id=contact_id, subject=subject,
                              description=f.get("description", "").strip(), status="New", priority=priority,
                              category=f.get("category") if f.get("category") in TICKET_CATEGORIES else "Other",
                              source=f.get("source") if f.get("source") in TICKET_SOURCES else "Email",
                              owner=owner, created_at=opened.isoformat(timespec="minutes"),
                              first_response_due=first_due, resolution_due=resolve_due)
        log_event("Ticket opened", f"{priority} priority. {f.get('description', '').strip()}".strip(), ticket_id=ticket_id,
                  company_id=company_id, contact_id=contact_id)
        from crm import notify_owner
        notify_owner(owner, f"{g.user['name']} gave you ticket #{ticket_id}: {subject}", f"{priority} priority",
                     url_for("ticket", ticket_id=ticket_id))
        db.commit()
        flash(f"Ticket #{ticket_id} opened. First response due {datetime.fromisoformat(first_due):%a %d %b %H:%M}.", "ok")
        return redirect(url_for("ticket", ticket_id=ticket_id))

    @app.route("/tickets/<int:ticket_id>")
    def ticket(ticket_id):
        t = decorate(get_or_404("tickets", ticket_id))
        company = one("SELECT * FROM companies WHERE id=? AND workspace_id=?", t["company_id"], ws()) if t["company_id"] else None
        contact = one("SELECT * FROM contacts WHERE id=? AND workspace_id=?", t["contact_id"], ws()) if t["contact_id"] else None
        entries, upcoming = timeline("ticket_id", ticket_id)
        return render_template("ticket.html", t=t, company=company, contact=contact, entries=entries, upcoming=upcoming,
                               record=dict(ticket_id=ticket_id, company_id=t["company_id"], contact_id=t["contact_id"]),
                               call_outcomes=CALL_OUTCOMES, statuses=TICKET_STATUSES, sla_hours=TICKET_SLA_HOURS)

    @app.post("/tickets/<int:ticket_id>/edit")
    def edit_ticket(ticket_id):
        t = get_or_404("tickets", ticket_id)
        f = request.form
        subject = f.get("subject", "").strip() or t["subject"]
        priority = f.get("priority") if f.get("priority") in TICKET_PRIORITIES else t["priority"]
        first_due, resolve_due = t["first_response_due"], t["resolution_due"]
        db = get_db()
        if priority != t["priority"]:
            # Service levels follow the priority, still measured from when the ticket was opened.
            first_due, resolve_due = sla_due(datetime.fromisoformat(t["created_at"]), priority)
            log_event(f"Priority changed to {priority}", f"Was {t['priority']}", ticket_id=ticket_id,
                      company_id=t["company_id"], contact_id=t["contact_id"])
        owner = chosen_owner(f.get("owner"))
        if owner != t["owner"]:
            log_event(f"Assigned to {owner}", ticket_id=ticket_id, company_id=t["company_id"])
        db.execute("UPDATE tickets SET subject=?, description=?, priority=?, category=?, source=?, owner=?, company_id=?,"
                   " contact_id=?, first_response_due=?, resolution_due=? WHERE id=? AND workspace_id=?",
                   (subject, f.get("description", t["description"] or "").strip(), priority,
                    f.get("category") if f.get("category") in TICKET_CATEGORIES else t["category"],
                    f.get("source") if f.get("source") in TICKET_SOURCES else t["source"], owner,
                    owned("companies", f.get("company_id")), owned("contacts", f.get("contact_id")),
                    first_due, resolve_due, ticket_id, ws()))
        db.commit()
        flash("Ticket updated.", "ok")
        return redirect(url_for("ticket", ticket_id=ticket_id))

    @app.post("/tickets/<int:ticket_id>/status")
    def ticket_status(ticket_id):
        status = request.form.get("status")
        if status not in TICKET_STATUSES:
            abort(400)
        t = set_ticket_status(ticket_id, status)
        get_db().commit()
        message = f"Ticket #{ticket_id} {'closed' if status == 'Closed' else 'moved to ' + status}."
        if wants_json():
            return jsonify(ok=True, status=status, message=message)
        flash(message, "ok")
        return back("ticket", ticket_id=t["id"])
