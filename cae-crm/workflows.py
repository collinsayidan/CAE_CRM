"""Workflow rules: "when this happens, do that", set up by admins without any code.

A rule has a trigger (a contact is added, a form is submitted, a deal reaches a stage, a ticket is opened, a quote is
accepted, an invoice is paid), an optional filter (which stage, which priority, which form) and one action: create a
task, notify someone, assign an owner (a named person, the record's owner, or taking turns round the team) or set the
contact's lifecycle stage. Each run is noted on the record's timeline. Actions never set off further rules, so rules
can't loop."""

import json
from datetime import datetime, time, timedelta

from flask import abort, current_app, flash, g, redirect, render_template, request, url_for

import auth
from core import log_event, now, one, rows, scalar, today, ws
from db import ACTIVITY_KINDS, LIFECYCLE_STAGES, STAGE_PROBABILITY, TICKET_PRIORITIES, get_db

# Trigger -> (description, what it can be narrowed by).
TRIGGERS = {
    "contact.created": ("A contact is added", None),
    "form.submitted": ("A web form is submitted", "form"),
    "deal.stage_changed": ("A deal moves to a stage", "stage"),
    "ticket.created": ("A ticket is opened", "priority"),
    "quote.accepted": ("A quote is accepted", None),
    "invoice.paid": ("An invoice is paid", None),
}
ACTIONS = {"task": "Create a task", "notify": "Notify someone", "owner": "Assign an owner",
           "lifecycle": "Set the contact's lifecycle stage"}
MAX_RULES = 50


def team_names():
    from notifications import team
    return [name for _, name in team()]


def context(evt):
    """The record a rule acts on, with its name, owner, page and timeline links."""
    e, rid = evt["event"], evt["record_id"]
    if e in ("contact.created", "form.submitted"):
        c = one("SELECT * FROM contacts WHERE id=? AND workspace_id=?", rid, ws())
        return c and dict(table="contacts", id=c["id"], name=f"{c['first_name']} {c['last_name']}", owner=c["owner"],
                          contact_id=c["id"], url=url_for("contact", contact_id=c["id"]),
                          links=dict(contact_id=c["id"], company_id=c["company_id"]))
    if e == "quote.accepted":
        q = one("SELECT * FROM quotes WHERE id=? AND workspace_id=?", rid, ws())
        if q is None:
            return None
        if q["deal_id"] is None:
            co = one("SELECT * FROM companies WHERE id=?", q["company_id"])
            return dict(table="companies", id=co["id"], name=co["name"], owner=co["owner"], contact_id=q["contact_id"],
                        url=url_for("company", company_id=co["id"]),
                        links=dict(company_id=co["id"], contact_id=q["contact_id"]))
        rid, e = q["deal_id"], "deal.stage_changed"
    if e == "deal.stage_changed":
        d = one("SELECT * FROM deals WHERE id=? AND workspace_id=?", rid, ws())
        return d and dict(table="deals", id=d["id"], name=d["title"], owner=d["owner"], contact_id=d["contact_id"],
                          url=url_for("deal", deal_id=d["id"]),
                          links=dict(deal_id=d["id"], company_id=d["company_id"], contact_id=d["contact_id"]))
    if e == "ticket.created":
        t = one("SELECT * FROM tickets WHERE id=? AND workspace_id=?", rid, ws())
        return t and dict(table="tickets", id=t["id"], name=f"#{t['id']} {t['subject']}", owner=t["owner"],
                          contact_id=t["contact_id"], url=url_for("ticket", ticket_id=t["id"]),
                          links=dict(ticket_id=t["id"], company_id=t["company_id"], contact_id=t["contact_id"]))
    if e == "invoice.paid":
        i = one("SELECT * FROM invoices WHERE id=? AND workspace_id=?", rid, ws())
        if i is None:
            return None
        co = one("SELECT * FROM companies WHERE id=?", i["company_id"])
        return dict(table="companies", id=co["id"], name=f"{i['number']} for {co['name']}", owner=co["owner"],
                    contact_id=None, url=url_for("invoice", invoice_id=i["id"]),
                    links=dict(company_id=co["id"], deal_id=i["deal_id"]))
    return None


def person(choice, ctx, rule):
    """A team member's name from a rule's choice: a name, "owner" (the record's owner) or "rotate" (taking turns)."""
    names = team_names()
    if choice == "owner":
        return ctx["owner"] if ctx["owner"] in names else None
    if choice == "rotate":
        return sorted(names)[rule["runs"] % len(names)] if names else None
    return choice if choice in names else None


def act(rule, ctx):
    """Do what a rule says. Returns a note for the timeline, or None if there was nothing to do."""
    s = json.loads(rule["settings"])
    db = get_db()
    if rule["action"] == "task":
        who = person(s.get("person"), ctx, rule) or (ctx["owner"] if ctx["owner"] in team_names() else rule["created_by"])
        due = datetime.combine(today() + timedelta(days=int(s.get("days", 0))), time(9))
        subject = f"{s['subject']}: {ctx['name']}"[:200]
        db.insert("activities", workspace_id=ws(), kind=s.get("kind", "Task"), subject=subject, owner=who,
                  due_at=due.isoformat(timespec="minutes"), done=0,
                  **{k: ctx["links"].get(k) for k in ("company_id", "contact_id", "deal_id", "ticket_id")})
        from crm import notify_owner
        notify_owner(who, f"New task: {subject}", f"From the workflow {rule['name']}", url_for("tasks"))
        return f"Task for {who}: {subject}, due {due:%d/%m/%Y}."
    if rule["action"] == "notify":
        who = person(s.get("person"), ctx, rule)
        if not who:
            return None
        from notifications import notify, user_named
        notify([user_named(who)], f"{rule['name']}: {ctx['name']}", s.get("message") or None, ctx["url"])
        return f"Told {who}."
    if rule["action"] == "owner":
        who = person(s.get("person"), ctx, rule)
        if not who or who == ctx["owner"]:
            return None
        db.execute(f"UPDATE {ctx['table']} SET owner=? WHERE id=? AND workspace_id=?", (who, ctx["id"], ws()))
        from crm import notify_owner
        notify_owner(who, f"{ctx['name']} is now yours", f"Assigned by the workflow {rule['name']}", ctx["url"])
        return f"Assigned to {who}."
    if rule["action"] == "lifecycle":
        if not ctx["contact_id"]:
            return None
        db.execute("UPDATE contacts SET lifecycle_stage=? WHERE id=? AND workspace_id=?",
                   (s["stage"], ctx["contact_id"], ws()))
        return f"Lifecycle stage set to {s['stage']}."
    return None


def run(evt):
    """Run the workspace's rules for something that just happened."""
    if evt["event"] not in TRIGGERS:
        return
    rules = rows("SELECT * FROM workflow_rules WHERE workspace_id=? AND on_event=? AND active=1 ORDER BY id",
                 ws(), evt["event"])
    rules = [r for r in rules if not r["on_value"] or r["on_value"] == str(evt["value"])]
    if not rules:
        return
    ctx = context(evt)
    if ctx is None:
        return
    db = get_db()
    for rule in rules:
        try:
            note = act(rule, ctx)
        except Exception:
            current_app.logger.exception("Workflow rule %s failed", rule["id"])
            continue
        if note:
            log_event(f"Workflow: {rule['name']}", note, **ctx["links"])
        db.execute("UPDATE workflow_rules SET runs=runs+1, last_run_at=? WHERE id=?",
                   (now().isoformat(timespec="minutes"), rule["id"]))
    db.commit()


def read_rule(f):
    """(columns, problem) from the add-a-rule form."""
    name = f.get("name", "").strip()[:80]
    event, action = f.get("on_event"), f.get("action")
    if not name or event not in TRIGGERS or action not in ACTIONS:
        return None, "Give the rule a name, and choose when it runs and what it does."
    narrow = TRIGGERS[event][1]
    value = (f.get(f"on_{narrow}") or "").strip() if narrow else ""
    if narrow == "stage" and value and value not in STAGE_PROBABILITY:
        return None, "Choose a stage."
    if narrow == "priority" and value and value not in TICKET_PRIORITIES:
        return None, "Choose a priority."
    if narrow == "form" and value and not one("SELECT 1 FROM web_forms WHERE id=? AND workspace_id=?",
                                              int(value) if value.isdigit() else 0, ws()):
        return None, "Choose one of your forms."
    people = team_names()
    who = f.get(f"{action}_person", "owner")
    settings = {}
    if action == "task":
        days = f.get("task_days", "0").strip()
        if not f.get("task_subject", "").strip() or not days.isdigit() or int(days) > 90:
            return None, "A task needs a subject and a due date up to 90 days away."
        if who not in people + ["owner", "rotate"]:
            return None, "Choose who the task is for."
        settings = dict(subject=f["task_subject"].strip()[:120], days=int(days), person=who,
                        kind=f.get("task_kind") if f.get("task_kind") in ACTIVITY_KINDS else "Task")
    elif action == "notify":
        if who not in people + ["owner"]:
            return None, "Choose who to notify."
        settings = dict(person=who, message=f.get("notify_message", "").strip()[:200])
    elif action == "owner":
        if who not in people + ["rotate"]:
            return None, "Choose who to assign."
        settings = dict(person=who)
    elif action == "lifecycle":
        if f.get("lifecycle_stage") not in LIFECYCLE_STAGES:
            return None, "Choose a lifecycle stage."
        settings = dict(stage=f["lifecycle_stage"])
    return dict(name=name, on_event=event, on_value=value or None, action=action, settings=json.dumps(settings)), None


def describe(rule):
    """A rule in plain words, for the list."""
    s = json.loads(rule["settings"])
    value = rule["on_value"]
    if rule["on_event"] == "deal.stage_changed" and value:
        when = f"a deal moves to {value}"
    elif rule["on_event"] == "ticket.created" and value:
        when = f"{'an' if value == 'Urgent' else 'a'} {value.lower()} priority ticket is opened"
    elif rule["on_event"] == "form.submitted" and value:
        form = one("SELECT name FROM web_forms WHERE id=?", int(value))
        when = f"someone fills in the form {form['name']}" if form else "someone fills in a form that's since been removed"
    else:
        when = TRIGGERS[rule["on_event"]][0].lower()
    whom = {"owner": "the record's owner", "rotate": "the team, taking turns"}.get(s.get("person"), s.get("person"))
    if rule["action"] == "task":
        then = f"create a {s['kind'].lower()} “{s['subject']}” for {whom}, due "
        then += "the same day" if not s["days"] else f"{s['days']} day{'s' if s['days'] != 1 else ''} later"
    elif rule["action"] == "notify":
        then = f"notify {whom}"
    elif rule["action"] == "owner":
        then = f"assign it to {whom}"
    else:
        then = f"set the contact's lifecycle stage to {s['stage']}"
    return f"When {when}, {then}."


def register(app):
    app.add_template_global(describe, "describe_rule")

    @app.route("/workflows", methods=["GET", "POST"])
    def workflows():
        auth.admin_required()
        if request.method == "POST":
            data, problem = read_rule(request.form)
            if problem:
                flash(f"Rule not added. {problem}", "error")
            elif scalar("SELECT COUNT(*) FROM workflow_rules WHERE workspace_id=?", ws()) >= MAX_RULES:
                flash(f"Rule not added. A workspace can have up to {MAX_RULES} rules.", "error")
            else:
                db = get_db()
                db.insert("workflow_rules", workspace_id=ws(), **data, active=1, runs=0, created_by=g.user["name"],
                          created_at=now().isoformat(timespec="minutes"))
                db.commit()
                flash(f"Rule added: {data['name']}. It runs from now on.", "ok")
            return redirect(url_for("workflows"))
        from db import OPEN_STAGES
        return render_template("workflows.html", rules=rows("SELECT * FROM workflow_rules WHERE workspace_id=? ORDER BY id", ws()),
                               triggers=TRIGGERS, actions=ACTIONS, people=team_names(),
                               stages=OPEN_STAGES + ["Won", "Lost"], priorities=TICKET_PRIORITIES,
                               forms=rows("SELECT id, name FROM web_forms WHERE workspace_id=? ORDER BY name", ws()),
                               kinds=ACTIVITY_KINDS, lifecycle_stages=LIFECYCLE_STAGES)

    def rule_or_404(rule_id):
        rule = one("SELECT * FROM workflow_rules WHERE id=? AND workspace_id=?", rule_id, ws())
        if rule is None:
            abort(404)
        return rule

    @app.post("/workflows/<int:rule_id>/toggle")
    def toggle_workflow(rule_id):
        auth.admin_required()
        rule = rule_or_404(rule_id)
        db = get_db()
        db.execute("UPDATE workflow_rules SET active=? WHERE id=?", (0 if rule["active"] else 1, rule_id))
        db.commit()
        flash(f"{rule['name']} {'paused' if rule['active'] else 'turned back on'}.", "ok")
        return redirect(url_for("workflows"))

    @app.post("/workflows/<int:rule_id>/delete")
    def delete_workflow(rule_id):
        auth.admin_required()
        rule = rule_or_404(rule_id)
        db = get_db()
        db.execute("DELETE FROM workflow_rules WHERE id=? AND workspace_id=?", (rule_id, ws()))
        db.commit()
        flash(f"Rule removed: {rule['name']}.", "ok")
        return redirect(url_for("workflows"))
