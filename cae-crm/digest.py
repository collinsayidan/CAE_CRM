"""The daily summary email: each working morning, what needs each person's attention. Their overdue tasks and tasks due
today, their tickets close to or past a service level, their deals that have gone quiet, and (for admins) overdue
invoices. It's only sent when there's something to report, and one click turns it off (or Profile and password).

The daily job calls send_all(). A working morning follows the workspace's bank holidays."""

import time

from flask import current_app, flash, g, redirect, render_template, request, url_for

from core import one, rows, sla_state, today
from db import OPEN_STAGES, get_db
from ukfmt import money

SALT = "cae-daily-summary-off"
PLATFORM = {"id": None, "name": "CAE CRM", "logo_updated": None}  # emails and pages from CAE CRM itself
LIMIT = 8  # items per section


def _signer():
    from itsdangerous import URLSafeSerializer
    return URLSafeSerializer(current_app.config["SECRET_KEY"], salt=SALT)


def off_link(user_id):
    return url_for("summary_off", token=_signer().dumps({"u": user_id}), _external=True)


def gather(user, workspace_id):
    """What this person should know about this morning. Empty sections are left out."""
    t = today()
    sections = []
    tasks = rows("SELECT id, kind, subject, due_at FROM activities WHERE workspace_id=? AND owner=? AND done=0 AND "
                 "substr(due_at, 1, 10) <= ? ORDER BY due_at", workspace_id, user["name"], t.isoformat())
    if tasks:
        sections.append(dict(title="Your tasks", link=url_for("tasks", mine="1", _external=True), items=[
            dict(text=f"{a['kind']}: {a['subject']}",
                 note="overdue" if a["due_at"][:10] < t.isoformat() else f"today {a['due_at'][11:16]}".strip(),
                 bad=a["due_at"][:10] < t.isoformat()) for a in tasks[:LIMIT]], more=len(tasks) - LIMIT))
    tickets = []
    for tk in rows("SELECT * FROM tickets WHERE workspace_id=? AND owner=? AND status <> 'Closed' ORDER BY resolution_due",
                   workspace_id, user["name"]):
        first = sla_state(tk["first_response_due"], tk["first_responded_at"])
        resolve = sla_state(tk["resolution_due"], tk["closed_at"])
        worst = next((s for s in (first, resolve) if s[0] == "overdue"), None) or \
            next((s for s in (first, resolve) if s[0] == "soon"), None)
        if worst:
            tickets.append(dict(text=f"#{tk['id']} {tk['subject']}", note=worst[1], bad=worst[0] == "overdue",
                                url=url_for("ticket", ticket_id=tk["id"], _external=True)))
    if tickets:
        sections.append(dict(title="Tickets needing a reply", link=url_for("tickets", owner=user["name"], open="1", _external=True),
                             items=tickets[:LIMIT], more=len(tickets) - LIMIT))
    from sales import quiet_ids
    quiet = quiet_ids(workspace_id)
    deals = [d for d in rows(f"SELECT id, title, value FROM deals WHERE workspace_id=? AND owner=? AND stage IN "
                             f"({','.join('?' * len(OPEN_STAGES))}) ORDER BY value DESC", workspace_id, user["name"],
                             *OPEN_STAGES) if d["id"] in quiet]
    if deals:
        sections.append(dict(title="Your deals that have gone quiet", link=url_for("pipeline", view="list", quiet="1",
                                                                                   owner=user["name"], _external=True),
                             items=[dict(text=d["title"], note=money(d["value"]),
                                         url=url_for("deal", deal_id=d["id"], _external=True)) for d in deals[:LIMIT]],
                             more=len(deals) - LIMIT))
    if user["role"] == "admin":
        overdue = rows("SELECT i.id, i.number, i.net, i.vat, i.due_date, c.name AS company FROM invoices i JOIN companies c "
                       "ON c.id=i.company_id WHERE i.workspace_id=? AND i.paid_date IS NULL AND i.due_date < ? "
                       "ORDER BY i.due_date", workspace_id, t.isoformat())
        if overdue:
            sections.append(dict(title=f"Overdue invoices, {money(sum(i['net'] + i['vat'] for i in overdue))} in all",
                                 link=url_for("invoices", _external=True),
                                 items=[dict(text=f"{i['number']} {i['company']}", note=money(i["net"] + i["vat"]), bad=True,
                                             url=url_for("invoice", invoice_id=i["id"], _external=True))
                                        for i in overdue[:LIMIT]], more=len(overdue) - LIMIT))
    return sections


def send_all(budget=25):
    """For the daily job: send each person their summary, once a day, on the workspace's working days."""
    import mail
    import ukholidays
    from ukfmt import is_working_day
    if not mail.configured():
        return 0
    started, sent, day = time.monotonic(), 0, today().isoformat()
    db = get_db()
    for w in rows("SELECT * FROM workspaces"):
        if not is_working_day(today(), ukholidays.for_region(w["bank_holiday_region"])):
            continue
        g.public_workspace = w["id"]
        g.pop("workspace", None)
        try:
            for user in rows("SELECT * FROM users WHERE workspace_id=? AND COALESCE(summary_off, 0)=0 AND "
                             "(summary_sent_on IS NULL OR summary_sent_on <> ?) AND email_verified_at IS NOT NULL",
                             w["id"], day):
                if time.monotonic() - started > budget:
                    return sent
                sections = gather(user, w["id"])
                db.execute("UPDATE users SET summary_sent_on=? WHERE id=?", (day, user["id"]))
                db.commit()
                if not sections:
                    continue
                link = off_link(user["id"])
                html = render_template("emails/summary.html", business=PLATFORM, user=user, workspace=w,
                                       sections=sections, off_link=link, home=url_for("overview", _external=True))
                text = f"Good morning {user['name'].split()[0]},\n\nHere's what needs you today in {w['name']}:\n\n" + \
                    "\n\n".join(s["title"] + ":\n" + "\n".join(f"- {i['text']} ({i['note']})" for i in s["items"])
                                for s in sections) + f"\n\nTurn these emails off: {link}\n"
                try:
                    mail.send(mail.message(user["email"], f"Your day in {w['name']}", html, text, "CAE CRM",
                                           headers={"List-Unsubscribe": f"<{link}>",
                                                    "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}))
                    sent += 1
                except mail.MailError:
                    current_app.logger.warning("Daily summary not sent to user %s", user["id"])
        finally:
            g.pop("public_workspace", None)
            g.pop("workspace", None)
    return sent


def register(app):

    @app.route("/summary/off/<token>", methods=["GET", "POST"])
    def summary_off(token):
        """Stop the daily summary from a link in the email, without signing in. A POST turns it off: the page's button,
        or a mail app's one-click unsubscribe."""
        from itsdangerous import BadSignature
        try:
            data = _signer().loads(token)
        except BadSignature:
            data = None
        user = one("SELECT id, email, summary_off FROM users WHERE id=?", data["u"]) if data else None
        if user is None:
            return render_template("public/summary_off.html", user=None, done=False, business=PLATFORM), 404
        done = bool(user["summary_off"])
        if request.method == "POST":
            get_db().execute("UPDATE users SET summary_off=1 WHERE id=?", (user["id"],))
            get_db().commit()
            done = True
        return render_template("public/summary_off.html", user=user, done=done, token=token, business=PLATFORM)

    @app.post("/account/summary")
    def account_summary():
        on = request.form.get("summary") == "on"
        get_db().execute("UPDATE users SET summary_off=? WHERE id=?", (0 if on else 1, g.user["id"]))
        get_db().commit()
        flash("You'll get a summary each working morning when there's something to report." if on
              else "Daily summary emails are off.", "ok")
        return redirect(url_for("auth.account") + "#summary")
