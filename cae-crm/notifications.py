"""Notifications for the team: being @mentioned in a note, being given a task or ticket, a quote being accepted or
declined, and a new web form enquiry. Shown under the bell in the top bar; nothing is emailed.

Also the getting-started checklist on Home, which guides a new workspace through its first setup."""

import re

from flask import abort, g, redirect, render_template, request, url_for
from markupsafe import Markup, escape

from core import now, one, rows, ws
from db import get_db

KEEP = 200  # notifications kept per person; older ones are tidied away


def team(workspace_id=None):
    """Everyone in the workspace, cached for the request: [(id, name)]."""
    key = f"team_{workspace_id or ws()}"
    if key not in g:
        setattr(g, key, [(r["id"], r["name"]) for r in rows("SELECT id, name FROM users WHERE workspace_id=? ORDER BY name",
                                                             workspace_id or ws())])
    return getattr(g, key)


def user_named(name, workspace_id=None):
    return next((uid for uid, n in team(workspace_id) if n == name), None)


def mentioned(text, workspace_id=None):
    """Team members @mentioned in some text, by full name or by a first name only one person has."""
    text = text or ""
    found = []
    people = team(workspace_id)
    firsts = {}
    for uid, name in people:
        firsts.setdefault(name.split()[0].lower(), []).append(uid)
    for uid, name in people:
        full = re.search(rf"@{re.escape(name)}\b", text, re.IGNORECASE)
        first = name.split()[0]
        short = len(firsts[first.lower()]) == 1 and re.search(rf"@{re.escape(first)}\b", text, re.IGNORECASE)
        if full or short:
            found.append(uid)
    return found


def notify(user_ids, title, body=None, url=None, workspace_id=None):
    """Tell people about something. The person who did it isn't told about their own action."""
    actor = g.user["id"] if g.get("user") else None
    db = get_db()
    for uid in dict.fromkeys(u for u in user_ids if u and u != actor):
        db.insert("notifications", workspace_id=workspace_id or ws(), user_id=uid, title=title[:200],
                  body=(body or "")[:300] or None, url=url if url and url.startswith("/") else None,
                  created_at=now().isoformat(timespec="minutes"))


def highlight_mentions(text):
    """Timeline text, escaped, with @mentions of team members picked out."""
    out = str(escape(text or ""))
    if "@" not in out or not g.get("user"):
        return Markup(out)
    for _, name in sorted(team(), key=lambda p: -len(p[1])):
        out = re.sub(rf"@({re.escape(str(escape(name)))})\b", r'<mark class="mention">@\1</mark>', out, flags=re.IGNORECASE)
    return Markup(out)


def checklist(w, user):
    """Getting started, for admins of a new workspace: (label, done, link)."""
    counts = one("SELECT (SELECT COUNT(*) FROM users WHERE workspace_id=?) AS users, "
                 "(SELECT COUNT(*) FROM contacts WHERE workspace_id=?) AS contacts, "
                 "(SELECT COUNT(*) FROM deals WHERE workspace_id=?) AS deals", w["id"], w["id"], w["id"])
    import mail
    return [
        ("Add your business details", bool(w["address"] and w["postcode"]), url_for("settings")),
        ("Upload your logo", bool(w["logo_updated"]), url_for("settings")),
        ("Invite your team", counts["users"] > 1, url_for("auth.team")),
        ("Add or import your contacts", counts["contacts"] > 0, url_for("imports")),
        ("Create your first deal", counts["deals"] > 0, url_for("pipeline")),
        ("Turn on two-factor sign-in", bool(user["totp_enabled_at"]), url_for("auth.account")),
        ("Set where replies go", bool(w["reply_to"]) or not mail.configured(), url_for("settings")),
    ]


def register(app):
    app.add_template_filter(highlight_mentions, "mentions")

    @app.context_processor
    def bell():
        if not g.get("user") or not request.endpoint or request.endpoint.startswith(("public_", "auth.login")):
            return {}
        latest = rows("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 6", g.user["id"])
        unread = one("SELECT COUNT(*) FROM notifications WHERE user_id=? AND read_at IS NULL", g.user["id"])[0]
        return {"bell": {"latest": latest, "unread": unread}, "team_names": [n for _, n in team(g.user["workspace_id"])]}

    @app.get("/notifications")
    def notifications():
        items = rows("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 100", g.user["id"])
        return render_template("notifications.html", items=items)

    @app.get("/notifications/<int:notification_id>")
    def open_notification(notification_id):
        n = one("SELECT * FROM notifications WHERE id=? AND user_id=?", notification_id, g.user["id"])
        if n is None:
            abort(404)
        db = get_db()
        if not n["read_at"]:
            db.execute("UPDATE notifications SET read_at=? WHERE id=?", (now().isoformat(timespec="minutes"), n["id"]))
            db.commit()
        return redirect(n["url"] or url_for("notifications"))

    @app.post("/notifications/read")
    def read_notifications():
        db = get_db()
        db.execute("UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL",
                   (now().isoformat(timespec="minutes"), g.user["id"]))
        old = rows("SELECT id FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT -1 OFFSET ?", g.user["id"], KEEP) \
            if not db.postgres else rows("SELECT id FROM notifications WHERE user_id=? ORDER BY id DESC OFFSET ?",
                                        g.user["id"], KEEP)
        for r in old:
            db.execute("DELETE FROM notifications WHERE id=?", (r["id"],))
        db.commit()
        return redirect(request.form.get("next") if (request.form.get("next") or "").startswith("/") else url_for("notifications"))

    @app.post("/getting-started/dismiss")
    def dismiss_checklist():
        import auth
        auth.admin_required()
        get_db().execute("UPDATE workspaces SET onboarding_done=1 WHERE id=?", (ws(),))
        get_db().commit()
        return redirect(url_for("overview"))
