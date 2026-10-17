"""Sign-up (a new workspace for a business), sign-in, team management and password changes."""

import hmac
import secrets
from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from db import DEFAULT_MONTHLY_TARGET, get_db

bp = Blueprint("auth", __name__)

MIN_PASSWORD = 10  # NCSC guidance favours length over complexity rules
MAX_FAILED = 5
LOCKOUT = timedelta(minutes=15)
ROLES = ("admin", "member")
# Checked against when the email is unknown, so a miss takes as long as a wrong password.
_DUMMY_HASH = generate_password_hash(secrets.token_hex(16))


def now_utc():
    return datetime.now(timezone.utc)


def password_problem(password, confirm=None):
    if len(password) < MIN_PASSWORD:
        return f"Use at least {MIN_PASSWORD} characters. A few unrelated words works well."
    if confirm is not None and password != confirm:
        return "The two passwords don't match."
    return None


def valid_email(email):
    local, _, domain = email.partition("@")
    return bool(local) and "." in domain and " " not in email


def create_user(db, workspace_id, name, email, password, role="member"):
    user_id = db.insert("users", workspace_id=workspace_id, email=email.strip().lower(), name=name.strip(),
                        password_hash=generate_password_hash(password), role=role, failed_logins=0,
                        created_at=now_utc().isoformat())
    db.commit()
    return user_id


def create_workspace(db, name, today):
    return db.insert("workspaces", name=name.strip(), legal_name=name.strip(), vat_registered=1,
                     monthly_target=DEFAULT_MONTHLY_TARGET, invoice_prefix="INV", payment_terms=30,
                     created_at=today.isoformat())


def load_user():
    user_id = session.get("user_id")
    if user_id is None:
        return None
    return get_db().execute("SELECT id, email, name, role, workspace_id FROM users WHERE id=?", (user_id,)).fetchone()


def start_session(user_id):
    session.clear()  # new session on sign-in, so an old cookie can't be reused
    session.permanent = True
    session["user_id"] = user_id


def admin_required():
    if not g.user or g.user["role"] != "admin":
        abort(403)


def safe_next(target):
    return target if target and target.startswith("/") and not target.startswith("//") else url_for("overview")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.get("user"):
        return redirect(url_for("overview"))
    error, email = None, ""
    if request.method == "POST":
        db = get_db()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        locked = user and user["locked_until"] and datetime.fromisoformat(user["locked_until"]) > now_utc()
        if locked:
            error = "Too many failed attempts. Try again in 15 minutes, or ask an admin to reset your password."
        elif user and check_password_hash(user["password_hash"], password):
            db.execute("UPDATE users SET failed_logins=0, locked_until=NULL WHERE id=?", (user["id"],))
            db.commit()
            start_session(user["id"])
            return redirect(safe_next(request.form.get("next")))
        else:
            if user:
                fails = user["failed_logins"] + 1
                until = (now_utc() + LOCKOUT).isoformat() if fails >= MAX_FAILED else None
                db.execute("UPDATE users SET failed_logins=?, locked_until=? WHERE id=?",
                           (0 if until else fails, until, user["id"]))
                db.commit()
            else:
                check_password_hash(_DUMMY_HASH, password)
            error = "That email and password don't match an account."
    return render_template("auth/login.html", error=error, email=email, next=request.args.get("next", "")), \
        (401 if error else 200)


@bp.post("/logout")
def logout():
    session.clear()
    flash("You're signed out.", "ok")
    return redirect(url_for("auth.login"))


@bp.route("/setup")
def setup():
    """The first release's setup page; sign-up has replaced it."""
    return redirect(url_for("auth.signup"))


@bp.route("/signup", methods=["GET", "POST"])
def signup():
    """Create a workspace for a business, with the person signing up as its first admin."""
    if g.get("user"):
        return redirect(url_for("overview"))
    expected = current_app.config["SIGNUP_CODE"]
    errors, form = {}, request.form
    if request.method == "POST":
        db = get_db()
        if expected and not hmac.compare_digest(form.get("setup_code", ""), expected):
            errors["setup_code"] = "That invite code isn't right."
        if not form.get("business", "").strip():
            errors["business"] = "Enter your business name."
        if not form.get("name", "").strip():
            errors["name"] = "Enter your name."
        email = form.get("email", "").strip().lower()
        if not valid_email(email):
            errors["email"] = "Enter a valid email address."
        elif db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            errors["email"] = "That email already has an account. Sign in instead."
        problem = password_problem(form.get("password", ""), form.get("confirm", ""))
        if problem:
            errors["password"] = problem
        if not errors:
            from core import today
            t = today()
            ws_id = create_workspace(db, form["business"], t)
            user_id = create_user(db, ws_id, form["name"], email, form["password"], "admin")
            if form.get("sample_data") == "on":
                from seed import seed_workspace
                seed_workspace(db, ws_id, t, form["name"].strip(), DEFAULT_MONTHLY_TARGET)
                db.commit()
            start_session(user_id)
            flash(f"Welcome to CAE CRM. {form['business'].strip()} is ready. Add your business details under Settings.", "ok")
            return redirect(url_for("overview"))
    return render_template("auth/signup.html", errors=errors, form=form, code_required=bool(expected)), \
        (422 if errors else 200)


@bp.route("/account", methods=["GET", "POST"])
def account():
    errors = {}
    if request.method == "POST":
        db = get_db()
        row = db.execute("SELECT password_hash FROM users WHERE id=?", (g.user["id"],)).fetchone()
        if not check_password_hash(row["password_hash"], request.form.get("current", "")):
            errors["current"] = "That isn't your current password."
        problem = password_problem(request.form.get("password", ""), request.form.get("confirm", ""))
        if problem:
            errors["password"] = problem
        if not errors:
            db.execute("UPDATE users SET password_hash=? WHERE id=?",
                       (generate_password_hash(request.form["password"]), g.user["id"]))
            db.commit()
            flash("Password changed.", "ok")
            return redirect(url_for("auth.account"))
    return render_template("auth/account.html", errors=errors), (422 if errors else 200)


@bp.route("/team", methods=["GET", "POST"])
def team():
    admin_required()
    db = get_db()
    errors, form = {}, {}
    if request.method == "POST":
        form = request.form
        email = form.get("email", "").strip().lower()
        if not form.get("name", "").strip():
            errors["name"] = "Enter their name."
        if not valid_email(email):
            errors["email"] = "Enter a valid email address."
        elif db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            errors["email"] = "That email already has a CAE CRM account."
        problem = password_problem(form.get("password", ""))
        if problem:
            errors["password"] = problem
        if not errors:
            create_user(db, g.user["workspace_id"], form["name"], email, form["password"],
                        form.get("role") if form.get("role") in ROLES else "member")
            flash(f"{form['name'].strip()} can now sign in. Share their temporary password with them directly.", "ok")
            return redirect(url_for("auth.team"))
    users = db.execute("SELECT id, name, email, role, locked_until, created_at FROM users WHERE workspace_id=? ORDER BY name",
                       (g.user["workspace_id"],)).fetchall()
    return render_template("auth/team.html", users=users, errors=errors, form=form, roles=ROLES,
                           now=now_utc().isoformat()), (422 if errors else 200)


def _team_member(user_id):
    row = get_db().execute("SELECT id FROM users WHERE id=? AND workspace_id=?", (user_id, g.user["workspace_id"])).fetchone()
    if row is None:
        abort(404)


@bp.post("/team/<int:user_id>/password")
def reset_password(user_id):
    admin_required()
    _team_member(user_id)
    problem = password_problem(request.form.get("password", ""))
    if problem:
        flash(f"Password not reset. {problem}", "error")
        return redirect(url_for("auth.team"))
    db = get_db()
    db.execute("UPDATE users SET password_hash=?, failed_logins=0, locked_until=NULL WHERE id=?",
               (generate_password_hash(request.form["password"]), user_id))
    db.commit()
    flash("Password reset and account unlocked.", "ok")
    return redirect(url_for("auth.team"))


@bp.post("/team/<int:user_id>/role")
def change_role(user_id):
    admin_required()
    _team_member(user_id)
    role = request.form.get("role")
    if role not in ROLES or user_id == g.user["id"]:
        flash("You can't change your own role.", "error")
        return redirect(url_for("auth.team"))
    db = get_db()
    db.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
    db.commit()
    flash("Role updated.", "ok")
    return redirect(url_for("auth.team"))


@bp.post("/team/<int:user_id>/remove")
def remove_user(user_id):
    admin_required()
    _team_member(user_id)
    if user_id == g.user["id"]:
        flash("You can't remove your own account.", "error")
        return redirect(url_for("auth.team"))
    db = get_db()
    db.execute("DELETE FROM saved_views WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM imports WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM users WHERE id=?", (user_id,))
    db.commit()
    flash("Team member removed. Their deals and activities keep their name.", "ok")
    return redirect(url_for("auth.team"))
