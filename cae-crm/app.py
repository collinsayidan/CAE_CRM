"""CAE CRM - a UK-standard CRM for businesses, built with Flask (SQLite locally, PostgreSQL in production).

Run:  python app.py   (then open http://127.0.0.1:5000)
      or: flask --app app run
"""

import os
import secrets
from datetime import date, timedelta
from urllib.parse import urlencode

from flask import Flask, abort, g, jsonify, redirect, render_template, request, session, url_for

import api
import assistant
import audit
import auth
import billing
import campaigns
import crm
import dataio
import fields
import files
import documents
import events
import finance
import home
import integrations
import legal
import monitoring
import notifications
import mtd
import quotes
import sales
import service
import settings
import twofactor
import ukfmt
import webforms
import webhooks
import workflows
import xero
from core import days_until, now, relative_time, scalar, today, workspace
from db import close_db, init_db, is_postgres
from ukfmt import money

# Sidebar sections, HubSpot-style: (heading, [(endpoint, label, icon)]).
NAV = [
    (None, [("overview", "Home", "home"), ("tasks", "Tasks", "calendar"), ("reports", "Reports", "trend")]),
    ("CRM", [("contacts", "Contacts", "users"), ("companies", "Companies", "building"),
             ("pipeline", "Deals", "pipeline"), ("tickets", "Tickets", "lifebuoy")]),
    ("Sales and finance", [("quotes", "Quotes", "note"), ("invoices", "Invoices", "pound"),
                           ("products", "Products", "box"), ("projects", "Projects", "flag")]),
    ("Marketing", [("campaigns", "Email", "mail"), ("forms", "Forms", "list")]),
]
# Everything about running the workspace sits behind one Settings link: (endpoint, label, admins only).
SETTINGS_TABS = [("settings", "Business details", True), ("auth.team", "Team", False),
                 ("assistant_settings", "AI assistant", True),
                 ("integrations", "Integrations", False), ("imports", "Import", True), ("billing", "Billing", True),
                 ("custom_fields_page", "Custom fields", True), ("workflows", "Workflows", True),
                 ("developers", "API and webhooks", True), ("vat", "VAT returns", True),
                 ("audit_trail", "Audit trail", True)]
# Which nav item lights up for pages that aren't in the nav themselves.
NAV_PARENT = {"contact": "contacts", "company": "companies", "deal": "pipeline", "ticket": "tickets",
              "invoice": "invoices", "quote": "quotes", "web_form": "forms",
              "campaign": "campaigns"}
# Which settings tab lights up for pages inside one.
SETTINGS_PARENT = {"auth.member": "auth.team", "auth.edit_member": "auth.team", "import_map": "imports",
                   "vat_return": "vat"}
# Pages anyone can reach without signing in.
PUBLIC_ENDPOINTS = {"landing", "favicon", "auth.login", "auth.signup", "auth.setup", "auth.forgot", "auth.reset",
                    "auth.two_factor_check", "static", "auth.verify_email", "auth.accept_invite",
                    "public_form", "public_quote", "accept_quote", "decline_quote", "unsubscribe", "resend_webhook",
                    "stripe_webhook", "cron_sync", "workspace_logo", "public_quote_pdf", "legal", "legal_index"}
TWO_FACTOR_SETUP_ALLOWED = {"auth.two_factor_setup", "auth.logout", "static", "favicon", "auth.verify_email"}
# Forms embedded on other websites can't carry our session's CSRF token; they have their own spam checks.
# Mail apps' one-click unsubscribe and Resend's webhooks post from elsewhere too; the webhook is signed.
CSRF_EXEMPT = {"public_form", "unsubscribe", "resend_webhook", "stripe_webhook"}


def assistant_nav():
    """The sidebar with the AI assistant under Home, Tasks and Reports, for workspaces that have turned it on."""
    (heading, items), *rest = NAV
    return [(heading, items + [("assistant", "Assistant", "sparkle")]), *rest]


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    hosted = bool(os.environ.get("VERCEL"))
    preview = os.environ.get("VERCEL_ENV") == "preview"
    if preview:
        # Preview deployments (one per pull request) must never touch live data, even if DATABASE_URL is shared
        # with them: they run new code, including database changes, before it's been reviewed.
        database_setting, database = "PREVIEW_DATABASE_URL", os.environ.get("PREVIEW_DATABASE_URL")
    else:
        database_setting = "DATABASE_URL"
        database = (os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
                    or os.environ.get("CAE_DATABASE"))
    if not database and not hosted:
        database = os.path.join(app.instance_path, "cae_crm.sqlite3")
    secret = os.environ.get("CAE_SECRET_KEY")
    app.config.update(
        SECRET_KEY=secret or secrets.token_hex(32),
        DATABASE=database,
        # On a host, a missing key or database must stop the app rather than lose accounts and data.
        MISSING_SETTINGS=[name for name, ok in (("CAE_SECRET_KEY", secret), (database_setting, database)) if hosted and not ok],
        # When set, creating a new workspace needs this invite code.
        SIGNUP_CODE=os.environ.get("CAE_SETUP_CODE", ""),
        # Refuse new passwords found in Have I Been Pwned's breach data (set CAE_BREACH_CHECK=0 to turn off).
        BREACH_CHECK=os.environ.get("CAE_BREACH_CHECK", "1") != "0",
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=hosted,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        MAX_CONTENT_LENGTH=6 * 1024 * 1024,  # CSV imports
        # Email through Resend: the API key, the platform's sending address, and the webhook signing secret.
        RESEND_API_KEY=os.environ.get("RESEND_API_KEY", ""),
        MAIL_FROM=os.environ.get("CAE_MAIL_FROM", ""),
        RESEND_WEBHOOK_SECRET=os.environ.get("RESEND_WEBHOOK_SECRET", ""),
        # Billing through Stripe: a price per user a month (STRIPE_PRICE_ID), an optional 20% VAT tax rate, and
        # workspaces that never pay (CAE_BILLING_EXEMPT, comma-separated ids). Without a key, billing is off.
        STRIPE_SECRET_KEY=os.environ.get("STRIPE_SECRET_KEY", ""),
        STRIPE_PRICE_ID=os.environ.get("STRIPE_PRICE_ID", ""),
        STRIPE_WEBHOOK_SECRET=os.environ.get("STRIPE_WEBHOOK_SECRET", ""),
        STRIPE_TAX_RATE_ID=os.environ.get("STRIPE_TAX_RATE_ID", ""),
        SEAT_PRICE=int(os.environ.get("CAE_SEAT_PRICE") or 1500),
        TRIAL_DAYS=int(os.environ.get("CAE_TRIAL_DAYS") or 14),
        BILLING_EXEMPT=os.environ.get("CAE_BILLING_EXEMPT", ""),
        # Integrations: OAuth apps for Gmail, Outlook, Xero and HMRC. Each appears once its id and secret are set.
        **{f"{p}_{k}": os.environ.get(f"{p}_{k}", "") for p in ("GOOGLE", "MICROSOFT", "XERO", "HMRC")
           for k in ("CLIENT_ID", "CLIENT_SECRET")},
        XERO_SCOPES=os.environ.get("XERO_SCOPES", ""),
        XERO_SALES_ACCOUNT=os.environ.get("XERO_SALES_ACCOUNT", "200"),
        HMRC_ENV=os.environ.get("HMRC_ENV", "sandbox"),
        VENDOR_PUBLIC_IP=os.environ.get("CAE_VENDOR_PUBLIC_IP", ""),
        TOKEN_KEY=os.environ.get("CAE_TOKEN_KEY", ""),
        CRON_SECRET=os.environ.get("CRON_SECRET", ""),
        # File attachments in Supabase Storage (a private bucket); without these, files are kept in the database.
        SUPABASE_URL=os.environ.get("SUPABASE_URL", ""),
        SUPABASE_SERVICE_KEY=os.environ.get("SUPABASE_SERVICE_KEY", ""),
        STORAGE_BUCKET=os.environ.get("CAE_STORAGE_BUCKET", "attachments"),
        TODAY=None,  # tests pin the date and time; otherwise the real ones are used
        NOW=None,
    )
    app.config.update(config or {})
    app.config["MONITORING"] = monitoring.start(app)
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
    app.add_template_global(lambda p: money(p, pennies=True), "gbp")  # for public pages, which have no sign-in context
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
            billing=billing.state(w),
            nav=assistant_nav() if assistant.enabled(w) else NAV,
            nav_active=NAV_PARENT.get(request.endpoint, request.endpoint), workspace=w,
            settings_tabs=[t for t in SETTINGS_TABS if (not t[2] or g.user["role"] == "admin")
                           and (t[0] != "billing" or billing.state(w)["enabled"])
                           and (t[0] != "assistant_settings" or assistant.configured())],
            settings_active=SETTINGS_PARENT.get(request.endpoint, request.endpoint),
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
        if request.blueprint == "api":
            return None  # the API signs in with keys (see api.py), not with a session and CSRF token
        if request.method == "POST" and request.endpoint not in CSRF_EXEMPT:
            token = request.form.get("csrf") or request.headers.get("X-CSRF-Token")
            if not token or token != session.get("csrf"):
                abort(400, "Your session expired. Reload the page and try again.")
        if request.endpoint == "static":
            return None
        g.user = auth.load_user()
        if app.config["MONITORING"]:
            monitoring.identify(g.user)
        if (g.user and twofactor.required(g.user) and not g.user["totp_enabled_at"]
                and request.endpoint not in TWO_FACTOR_SETUP_ALLOWED):
            return redirect(url_for("auth.two_factor_setup"))  # admins set up two-factor sign-in before anything else
        if g.user and request.endpoint not in PUBLIC_ENDPOINTS:
            return billing.guard_writes()
        if g.user or request.endpoint in PUBLIC_ENDPOINTS:
            return None
        if request.path.startswith("/api/") or request.headers.get("X-Requested-With") == "fetch":
            return jsonify(error="Sign in to continue."), 401
        if request.path == "/":
            return redirect(url_for("landing"))
        return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))

    @app.get("/favicon.ico")
    def favicon():
        # Browsers ask for this on every page, including public quotes and forms.
        return app.send_static_file("brand/favicon.ico")

    app.register_blueprint(auth.bp)
    events.register(app)  # first, so its after_request hook runs last, once everything else is saved
    for module in (home, crm, sales, service, finance, quotes, webforms, campaigns, billing, integrations, xero, mtd,
                   documents, notifications, files, fields, workflows, webhooks, api, legal, dataio, settings, audit,
                   assistant):
        module.register(app)
    return app


if __name__ == "__main__":
    try:  # local settings from .env, when python-dotenv is installed (requirements-dev.txt)
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    create_app().run(debug=os.environ.get("FLASK_DEBUG") == "1")
