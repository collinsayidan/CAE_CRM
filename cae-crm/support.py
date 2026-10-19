"""Customer service email: replying to a ticket's contact by email from the ticket, saved replies with placeholders, and
a one-question satisfaction survey when a ticket closes.

Replies go from the business's name on the platform's sending address, with replies coming back to the business's
reply-to address, and are logged on the ticket's timeline as emails. The survey is off until an admin switches it on;
each closed ticket gets at most one, and the rating is recorded when the customer presses a button on the survey page
(not when a link is opened, so email security scanners that open links can't cast votes)."""

import re
import secrets
from datetime import timedelta

from flask import abort, current_app, flash, g, redirect, render_template, request, url_for


import auth
from core import get_or_404, log_event, now, one, rows, workspace, ws
from db import get_db

PLACEHOLDERS = {
    "first_name": "the contact's first name",
    "ticket_number": "the ticket number, like #214",
    "ticket_subject": "the ticket's subject",
    "your_name": "your name",
    "business_name": "your business's name",
}
RATINGS = {"good": "Good", "okay": "Okay", "poor": "Poor"}
MAX_BODY = 10_000


def fill(text, ticket, contact):
    """A saved reply with its placeholders filled in for this ticket."""
    values = {"first_name": (contact["first_name"] if contact else "") or "there", "ticket_number": f"#{ticket['id']}",
              "ticket_subject": ticket["subject"], "your_name": g.user["name"], "business_name": workspace()["name"]}
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: values.get(m.group(1), m.group(0)), text or "")


def saved_replies():
    return rows("SELECT * FROM saved_replies WHERE workspace_id=? ORDER BY LOWER(title)", ws())


def paragraphs(text):
    return [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]


def email_html(business, paragraphs_, footer):
    from documents import logo_url
    return render_template("emails/reply.html", business=business, logo=logo_url(business, external=True),
                           paragraphs=paragraphs_, footer=footer)


# --- Satisfaction survey ----------------------------------------------------------------------------------------------

def maybe_survey(ticket):
    """When a ticket closes: email its contact the survey, if the workspace asks for them. Never twice per ticket."""
    import mail
    import security
    w = workspace()
    if not w["csat_on"] or not mail.configured() or not ticket["contact_id"]:
        return False
    if g.get("user") and security.needs_verification(g.user):
        return False
    contact = one("SELECT * FROM contacts WHERE id=? AND workspace_id=?", ticket["contact_id"], ws())
    if not contact or not contact["email"] or contact["email_bounced_at"]:
        return False
    if one("SELECT 1 FROM ticket_surveys WHERE ticket_id=?", ticket["id"]):
        return False
    token = secrets.token_urlsafe(24)
    db = get_db()
    db.insert("ticket_surveys", workspace_id=ws(), ticket_id=ticket["id"], token=token,
              sent_at=now().isoformat(timespec="minutes"))
    links = {k: url_for("survey", token=token, r=k, _external=True) for k in RATINGS}
    from documents import logo_url
    html = render_template("emails/survey.html", business=w, logo=logo_url(w, external=True), ticket=ticket,
                           first_name=contact["first_name"], links=links, ratings=RATINGS)
    text = (f"Hi {contact['first_name'] or 'there'},\n\nWe've closed your request #{ticket['id']}: {ticket['subject']}.\n"
            "How did we do? Choose one:\n" + "\n".join(f"{label}: {links[k]}" for k, label in RATINGS.items()) +
            f"\n\nThanks,\n{w['name']}\n")
    try:
        mail.send(mail.message(contact["email"], f"How did we do? Request #{ticket['id']}", html, text, w["name"],
                               w["reply_to"]))
    except mail.MailError:
        current_app.logger.warning("Survey for ticket %s not sent", ticket["id"])
        return False
    return True


def satisfaction(days=90):
    """Ratings over the last `days`: counts, the share rated Good, and recent comments."""
    since = (now() - timedelta(days=days)).isoformat(timespec="minutes")
    found = rows("SELECT s.rating, s.comment, s.rated_at, t.id AS ticket_id, t.subject FROM ticket_surveys s "
                 "JOIN tickets t ON t.id=s.ticket_id WHERE s.workspace_id=? AND s.rated_at >= ? ORDER BY s.rated_at DESC",
                 ws(), since)
    counts = {k: sum(1 for r in found if r["rating"] == k) for k in RATINGS}
    total = sum(counts.values())
    sent = one("SELECT COUNT(*) FROM ticket_surveys WHERE workspace_id=? AND sent_at >= ?", ws(), since)[0]
    return dict(counts=counts, total=total, sent=sent, score=round(counts["good"] / total * 100) if total else None,
                comments=[r for r in found if r["comment"]][:5])


def register(app):
    app.add_template_global(saved_replies, "saved_replies")

    # --- Replying to a ticket ------------------------------------------------------------------------------------------

    @app.post("/tickets/<int:ticket_id>/reply")
    def ticket_reply(ticket_id):
        import mail
        from service import set_ticket_status
        t = get_or_404("tickets", ticket_id)
        back = redirect(url_for("ticket", ticket_id=ticket_id) + "#reply")
        contact = one("SELECT * FROM contacts WHERE id=? AND workspace_id=?", t["contact_id"], ws()) if t["contact_id"] else None
        body = (request.form.get("body") or "").strip()[:MAX_BODY]
        subject = (request.form.get("subject") or "").strip()[:200] or f"Re: [#{t['id']}] {t['subject']}"
        if not contact or not contact["email"]:
            flash("Reply not sent. The ticket needs a contact with an email address.", "error")
            return back
        if not body:
            flash("Reply not sent. Write a message first.", "error")
            return back
        if not mail.configured():
            flash("Reply not sent. Email isn't set up for CAE CRM yet.", "error")
            return back
        w = workspace()
        footer = f"You're getting this because you contacted {w['name']} about request #{t['id']}. Reply to this email to answer."
        try:
            mail.send(mail.message(contact["email"], subject, email_html(w, paragraphs(body), footer),
                                   f"{body}\n\n--\n{footer}\n", w["name"], w["reply_to"],
                                   headers={"X-CAE-Ticket": str(t["id"])}))
        except mail.MailError as e:
            flash(f"Reply not sent. {e}", "error")
            return back
        log_event(subject, body, kind="email", outcome=None, ticket_id=t["id"], contact_id=contact["id"],
                  company_id=t["company_id"])
        if t["status"] in ("New", "Waiting on us"):
            set_ticket_status(t["id"], "Waiting on contact")  # also records the first response
        elif not t["first_responded_at"]:
            get_db().execute("UPDATE tickets SET first_responded_at=? WHERE id=?", (now().isoformat(timespec="minutes"), t["id"]))
        get_db().commit()
        flash(f"Reply sent to {contact['email']}.", "ok")
        return redirect(url_for("ticket", ticket_id=ticket_id))

    # --- Saved replies -------------------------------------------------------------------------------------------------

    @app.route("/settings/saved-replies", methods=["GET", "POST"])
    def saved_replies_page():
        auth.admin_required()
        db = get_db()
        if request.method == "POST":
            f = request.form
            reply_id = f.get("reply_id", "")
            existing = one("SELECT * FROM saved_replies WHERE id=? AND workspace_id=?", int(reply_id), ws()) \
                if reply_id.isdigit() else None
            if reply_id and existing is None:
                abort(404)
            if f.get("action") == "delete" and existing:
                db.execute("DELETE FROM saved_replies WHERE id=?", (existing["id"],))
                flash(f"Deleted the saved reply {existing['title']}.", "ok")
            else:
                title, body = f.get("title", "").strip()[:80], f.get("body", "").strip()[:MAX_BODY]
                if not title or not body:
                    flash("A saved reply needs a name and some text.", "error")
                    return redirect(url_for("saved_replies_page"))
                if existing:
                    db.execute("UPDATE saved_replies SET title=?, body=? WHERE id=?", (title, body, existing["id"]))
                    flash(f"Saved {title}.", "ok")
                else:
                    db.insert("saved_replies", workspace_id=ws(), title=title, body=body, created_by=g.user["name"],
                              created_at=now().isoformat(timespec="minutes"))
                    flash(f"Added {title}. It's ready to use on any ticket.", "ok")
            db.commit()
            return redirect(url_for("saved_replies_page"))
        editing = request.args.get("edit", "")
        edit = one("SELECT * FROM saved_replies WHERE id=? AND workspace_id=?", int(editing), ws()) if editing.isdigit() else None
        return render_template("saved_replies.html", replies=saved_replies(), edit=edit, placeholders=PLACEHOLDERS)

    # --- The survey's public pages -------------------------------------------------------------------------------------

    def survey_or_404(token):
        s = one("SELECT * FROM ticket_surveys WHERE token=?", token) if token and len(token) < 80 else None
        if s is None:
            abort(404)
        g.public_workspace = s["workspace_id"]
        return s

    @app.route("/survey/<token>", methods=["GET", "POST"])
    def survey(token):
        s = survey_or_404(token)
        t = one("SELECT * FROM tickets WHERE id=?", s["ticket_id"])
        w = workspace()
        if request.method == "POST" and not s["rated_at"]:
            rating = request.form.get("rating")
            if rating in RATINGS:
                comment = (request.form.get("comment") or "").strip()[:1000] or None
                get_db().execute("UPDATE ticket_surveys SET rating=?, comment=?, rated_at=? WHERE id=?",
                                 (rating, comment, now().isoformat(timespec="minutes"), s["id"]))
                if t:
                    log_event(f"Customer rated our support: {RATINGS[rating]}", comment, ticket_id=t["id"],
                              contact_id=t["contact_id"], company_id=t["company_id"])
                get_db().commit()
                s = one("SELECT * FROM ticket_surveys WHERE id=?", s["id"])
        from documents import logo_url
        return render_template("public/survey.html", s=s, t=t, business=w, logo=logo_url(w), ratings=RATINGS,
                               chosen=request.args.get("r") if request.args.get("r") in RATINGS else None)
