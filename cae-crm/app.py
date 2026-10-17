"""CAE CRM - a UK-standard CRM for businesses, built with Flask (SQLite locally, PostgreSQL in production).

Run:  python app.py   (then open http://127.0.0.1:5000)
      or: flask --app app run
"""

import os
import secrets
from datetime import date, timedelta
from urllib.parse import urlencode

from flask import Flask, abort, g, jsonify, redirect, render_template, request, session, url_for

import auth
import crm
import dataio
import finance
import home
import sales
import service
import settings
import ukfmt
from core import days_until, now, relative_time, scalar, today, workspace
from db import close_db, init_db, is_postgres
from ukfmt import money

# Sidebar sections, HubSpot-style: (heading, [(endpoint, label, icon)]).
NAV = [
    (None, [("overview", "Home", "home")]),
    ("CRM", [("contacts", "Contacts", "users"), ("companies", "Companies", "building"),
             ("pipeline", "Deals", "pipeline"), ("tickets", "Tickets", "lifebuoy")]),
    ("Sales", [("tasks", "Tasks", "calendar"), ("products", "Products", "box")]),
    ("Finance", [("invoices", "Invoices", "pound")]),
    ("Delivery", [("projects", "Projects", "flag")]),
    ("Insight", [("reports", "Reports", "trend")]),
    ("Workspace", [("auth.team", "Team", "users")]),
]
# Which nav item lights up for pages that aren't in the nav themselves.
NAV_PARENT = {"contact": "contacts", "company": "companies", "deal": "pipeline", "ticket": "tickets",
              "invoice": "invoices", "import_map": "imports",
              "auth.member": "auth.team", "auth.edit_member": "auth.team"}
# Pages anyone can reach without signing in.
PUBLIC_ENDPOINTS = {"landing", "auth.login", "auth.signup", "auth.setup", "static"}


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    hosted = bool(os.environ.get("VERCEL"))
    database = (os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
                or os.environ.get("CAE_DATABASE"))
    if not database and not hosted:
        database = os.path.join(app.instance_path, "cae_crm.sqlite3")
    secret = os.environ.get("CAE_SECRET_KEY")
    app.config.update(
        SECRET_KEY=secret or secrets.token_hex(32),
        DATABASE=database,
        # On a host, a missing key or database must stop the app rather than lose accounts and data.
        MISSING_SETTINGS=[name for name, ok in (("CAE_SECRET_KEY", secret), ("DATABASE_URL", database)) if hosted and not ok],
        # When set, creating a new workspace needs this invite code.
        SIGNUP_CODE=os.environ.get("CAE_SETUP_CODE", ""),
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=hosted,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        MAX_CONTENT_LENGTH=6 * 1024 * 1024,  # CSV imports
        TODAY=None,  # tests pin the date and time; otherwise the real ones are used
        NOW=None,
    )
    app.config.update(config or {})
    if not app.config["MISSING_SETTINGS"]:
        if not is_postgres(app.config["DATABASE"]):
            os.makedirs(os.path.dirname(os.path.abspath(app.config["DATABASE"])), exist_ok=True)
        init_db(app.config["DATABASE"], app.config["TODAY"] or date.today())
    app.teardown_appcontext(close_db)

    for name in ("money", "money_short", "uk_date", "uk_date_short", "uk_datetime"):
        app.add_template_filter(getattr(ukfmt, name), name)
    app.add_template_filter(lambda n: "".join(w[0] for w in (n or "?").split() if w[0].isalnum())[:2].upper() or "?",
                            "initials")
    app.add_template_filter(lambda n: sum(map(ord, n or "")) * 37 % 360, "hue")
    app.add_template_filter(lambda s: (s or "").lower().replace(" ", "-"), "slug")
    app.add_template_global(auth.team_photo, "team_photo")
    app.add_template_filter(days_until, "days_until")
    app.add_template_filter(relative_time, "relative_time")
    app.add_template_filter(lambda args, page: urlencode({**args, "page": page}), "pager_query")
    app.add_template_filter(lambda s: date.fromisoformat(str(s)[:10]).strftime("%B %Y"), "month_name")

    @app.context_processor
    def inject_globals():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(24)
        base = dict(csrf_token=session["csrf"], current_user=g.get("user"), today=today())
        if not g.get("user"):
            return base  # public pages need no CRM data
        t, w = today(), workspace()
        hour = now().hour
        return base | dict(
            nav=NAV, nav_active=NAV_PARENT.get(request.endpoint, request.endpoint), workspace=w,
            pennies=lambda p: money(p, pennies=True),
            greeting="Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening",
            first_name=g.user["name"].split()[0],
            counts=dict(
                pipeline=scalar("SELECT COUNT(*) FROM deals WHERE workspace_id=? AND stage NOT IN ('Won','Lost')", w["id"]),
                tickets=scalar("SELECT COUNT(*) FROM tickets WHERE workspace_id=? AND status <> 'Closed'", w["id"]),
                tasks=scalar("SELECT COUNT(*) FROM activities WHERE workspace_id=? AND done=0 AND substr(due_at,1,10) <= ?",
                             w["id"], t.isoformat()),
                invoices=scalar("SELECT COUNT(*) FROM invoices WHERE workspace_id=? AND paid_date IS NULL AND due_date < ?",
                                w["id"], t.isoformat()),
            ),
            count_titles={"pipeline": "Open deals", "tickets": "Open tickets", "tasks": "Due today or overdue",
                          "invoices": "Overdue invoices"},
            alert_counts={"invoices", "tasks"},
            **home.quick_create_choices(),
        )

    @app.before_request
    def guard():
        missing = app.config["MISSING_SETTINGS"]
        if missing and request.endpoint != "static":
            return render_template("auth/settings_needed.html", missing=missing), 503
        if request.method == "POST":
            token = request.form.get("csrf") or request.headers.get("X-CSRF-Token")
            if not token or token != session.get("csrf"):
                abort(400, "Your session expired. Reload the page and try again.")
        if request.endpoint == "static":
            return None
        g.user = auth.load_user()
        if g.user or request.endpoint in PUBLIC_ENDPOINTS:
            return None
        if request.path.startswith("/api/") or request.headers.get("X-Requested-With") == "fetch":
            return jsonify(error="Sign in to continue."), 401
        if request.path == "/":
            return redirect(url_for("landing"))
        return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))

    app.register_blueprint(auth.bp)
    for module in (home, crm, sales, service, finance, dataio, settings):
        module.register(app)
    return app


if __name__ == "__main__":
    try:  # local settings from .env, when python-dotenv is installed (requirements-dev.txt)
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    create_app().run(debug=os.environ.get("FLASK_DEBUG") == "1")
