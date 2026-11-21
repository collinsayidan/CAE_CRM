"""Customer portal: explicit membership, email proof, single-use links and revocable sessions."""

import hashlib
import secrets
from datetime import timedelta
from flask import abort, current_app, flash, g, redirect, render_template, request, session, url_for
from markupsafe import escape
import auth
import mail
from core import now, one, rows, ws
from db import get_db


def site(token):
    row = one("SELECT * FROM portal_sites WHERE token=?", token)
    if not row:
        abort(404)
    g.public_workspace = row["workspace_id"]
    g.pop("workspace", None)
    return row


def identity(token):
    s = site(token)
    saved = session.get("customer_portal") or {}
    if saved.get("workspace_id") != s["workspace_id"] or saved.get("expires", "") <= now().isoformat(
        timespec="seconds"
    ):
        abort(401, "Your customer session expired. Request a new sign-in link.")
    member = one(
        "SELECT m.*,c.company_id,c.first_name,c.email FROM portal_members m JOIN contacts c ON c.id=m.contact_id AND c.workspace_id=m.workspace_id WHERE m.workspace_id=? AND m.contact_id=? AND m.active=1",
        s["workspace_id"],
        saved.get("contact_id"),
    )
    if not member or saved.get("email") != member["email"]:
        session.pop("customer_portal", None)
        abort(403)
    return s, member


def available_records(member):
    cid = member["contact_id"]
    company = member["company_id"] if member["company_access"] else None
    quotes = rows(
        "SELECT id,number,status,net,vat,token FROM quotes WHERE workspace_id=? AND status<>'Draft' AND (contact_id=? OR company_id=?) ORDER BY id DESC",
        ws(),
        cid,
        company,
    )
    tickets = rows(
        "SELECT id,subject,status,priority,created_at FROM tickets WHERE workspace_id=? AND (contact_id=? OR company_id=?) ORDER BY id DESC",
        ws(),
        cid,
        company,
    )
    invoices = (
        rows(
            "SELECT number,net,vat,due_date,paid_date,pay_token FROM invoices WHERE workspace_id=? AND company_id=? ORDER BY id DESC",
            ws(),
            company,
        )
        if company
        else []
    )
    projects = (
        rows(
            "SELECT name,status,progress,due_date FROM projects WHERE workspace_id=? AND company_id=? ORDER BY id DESC",
            ws(),
            company,
        )
        if company
        else []
    )
    return dict(quotes=quotes, tickets=tickets, invoices=invoices, projects=projects)


def register(app):
    @app.route("/settings/portal", methods=["GET", "POST"])
    def portal_settings():
        auth.admin_required()
        db = get_db()
        s = one("SELECT * FROM portal_sites WHERE workspace_id=?", ws())
        if request.method == "POST":
            if not s:
                db.insert("portal_sites", workspace_id=ws(), token=secrets.token_urlsafe(24))
                db.commit()
                return redirect(url_for("portal_settings"))
            cid = request.form.get("contact_id")
            if not one("SELECT id FROM contacts WHERE id=? AND workspace_id=?", cid, ws()):
                abort(404)
            company = int(request.form.get("company_access") == "on")
            active = int(request.form.get("active") == "on")
            old = one("SELECT id FROM portal_members WHERE contact_id=? AND workspace_id=?", cid, ws())
            if old:
                db.execute(
                    "UPDATE portal_members SET active=?,company_access=? WHERE id=?",
                    (active, company, old[0]),
                )
            else:
                db.insert(
                    "portal_members",
                    workspace_id=ws(),
                    contact_id=int(cid),
                    company_access=company,
                    active=active,
                )
            db.commit()
            flash(
                "Customer access updated. Company access includes all that company's invoices, quotes, projects and tickets.",
                "ok",
            )
            return redirect(url_for("portal_settings"))
        return render_template(
            "portal_settings.html",
            site=s,
            contacts=rows(
                "SELECT id,first_name,last_name,email FROM contacts WHERE workspace_id=? AND email IS NOT NULL ORDER BY first_name",
                ws(),
            ),
            members=rows(
                "SELECT m.*,c.first_name,c.last_name FROM portal_members m JOIN contacts c ON c.id=m.contact_id WHERE m.workspace_id=? ORDER BY m.id",
                ws(),
            ),
        )

    @app.route("/portal/<token>", methods=["GET", "POST"])
    def public_portal_login(token):
        s = site(token)
        sent = False
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()[:254]
            from quotes import client_ip

            key = hashlib.sha256((str(s["workspace_id"]) + "|" + client_ip()).encode()).hexdigest()
            cutoff = (now() - timedelta(hours=1)).isoformat(timespec="seconds")
            if (
                one(
                    "SELECT COUNT(*) FROM portal_attempts WHERE workspace_id=? AND fingerprint=? AND created_at>?",
                    ws(),
                    key,
                    cutoff,
                )[0]
                >= 5
            ):
                abort(429, "Please wait before requesting another sign-in link.")
            db = get_db()
            db.insert(
                "portal_attempts",
                workspace_id=ws(),
                fingerprint=key,
                created_at=now().isoformat(timespec="seconds"),
            )
            db.commit()
            c = one(
                "SELECT c.* FROM contacts c JOIN portal_members m ON m.contact_id=c.id AND m.workspace_id=c.workspace_id WHERE c.workspace_id=? AND lower(c.email)=? AND m.active=1",
                ws(),
                email,
            )
            if c and not one("SELECT demo_until FROM workspaces WHERE id=?", ws())[0] and mail.configured():
                raw = secrets.token_urlsafe(32)
                digest = hashlib.sha256(raw.encode()).hexdigest()
                db.insert(
                    "portal_links",
                    workspace_id=ws(),
                    contact_id=c["id"],
                    token_hash=digest,
                    expires_at=(now() + timedelta(minutes=15)).isoformat(timespec="seconds"),
                    created_at=now().isoformat(timespec="seconds"),
                )
                db.commit()
                link = url_for("public_portal_access", token=token, secret=raw, _external=True)
                text = f"Sign in to your customer portal: {link}\nThis link expires in 15 minutes. If you didn't request it, ignore this email."
                try:
                    mail.send(
                        mail.message(
                            email,
                            "Your customer portal sign-in link",
                            "<p>" + str(escape(text)) + "</p>",
                            text,
                            "CAE CRM",
                        )
                    )
                except mail.MailError:
                    current_app.logger.warning("Customer portal sign-in email was not delivered")
            sent = True
        return render_template("portal_login.html", sent=sent)

    @app.route("/portal/<token>/access/<secret>", methods=["GET", "POST"])
    def public_portal_access(token, secret):
        site(token)
        digest = hashlib.sha256(secret.encode()).hexdigest()
        link = one(
            "SELECT l.* FROM portal_links l JOIN portal_members m ON m.contact_id=l.contact_id AND m.workspace_id=l.workspace_id WHERE l.workspace_id=? AND l.token_hash=? AND l.used_at IS NULL AND l.expires_at>? AND m.active=1",
            ws(),
            digest,
            now().isoformat(timespec="seconds"),
        )
        if not link:
            abort(410, "This sign-in link expired or has already been used.")
        if request.method == "POST":
            db = get_db()
            if not db.execute(
                "UPDATE portal_links SET used_at=? WHERE id=? AND used_at IS NULL RETURNING id",
                (now().isoformat(timespec="seconds"), link["id"]),
            ).fetchone():
                abort(410)
            db.commit()
            session["customer_portal"] = dict(
                workspace_id=ws(),
                contact_id=link["contact_id"],
                email=one(
                    "SELECT email FROM contacts WHERE id=? AND workspace_id=?", link["contact_id"], ws()
                )[0],
                expires=(now() + timedelta(hours=8)).isoformat(timespec="seconds"),
            )
            return redirect(url_for("public_portal_home", token=token))
        return render_template("portal_access.html")

    @app.get("/portal/<token>/home")
    def public_portal_home(token):
        s, member = identity(token)
        return render_template("portal_home.html", site=s, member=member, **available_records(member))

    @app.post("/portal/<token>/logout")
    def public_portal_logout(token):
        site(token)
        session.pop("customer_portal", None)
        return redirect(url_for("public_portal_login", token=token))
