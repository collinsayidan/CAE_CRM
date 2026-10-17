"""Sign-in, first-run setup, team management and password changes."""

import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db

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


def create_user(db, name, email, password, role="member"):
    db.execute(
        "INSERT INTO users (email, name, password_hash, role, created_at) VALUES (?,?,?,?,?)",
        (email.strip().lower(), name.strip(), generate_password_hash(password), role, now_utc().isoformat()))
    db.commit()


def user_count():
    return get_db().execute("SELECT COUNT(*) FROM users").fetchone()[0]


def load_user():
    user_id = session.get("user_id")
    if user_id is None:
        return None
    return get_db().execute("SELECT id, email, name, role FROM users WHERE id=?", (user_id,)).fetchone()


def start_session(user):
    session.clear()  # new session on sign-in, so an old cookie can't be reused
    session.permanent = True
    session["user_id"] = user["id"]


def admin_required():
    if not g.user or g.user["role"] != "admin":
        abort(403)


def safe_next(target):
    return target if target and target.startswith("/") and not target.startswith("//") else url_for("overview")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.get("user"):
        return redirect(url_for("overview"))
    if not user_count():
        return redirect(url_for("auth.setup"))
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
            start_session(user)
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


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    """Create the first admin account. Closed for good once any account exists."""
    if user_count():
        return redirect(url_for("auth.login"))
    code_required = bool(os.environ.get("VERCEL") or os.environ.get("CAE_SETUP_CODE"))
    expected = os.environ.get("CAE_SETUP_CODE", "")
    errors, form = {}, request.form
    if request.method == "POST":
        if code_required and not (expected and hmac.compare_digest(form.get("setup_code", ""), expected)):
            errors["setup_code"] = "That setup code isn't right. It's the CAE_SETUP_CODE value in your hosting settings."
        if not form.get("name", "").strip():
            errors["name"] = "Enter your name."
        if "@" not in form.get("email", ""):
            errors["email"] = "Enter a valid email address."
        problem = password_problem(form.get("password", ""), form.get("confirm", ""))
        if problem:
            errors["password"] = problem
        if not errors:
            db = get_db()
            create_user(db, form["name"], form["email"], form["password"], "admin")
            start_session(db.execute("SELECT * FROM users WHERE email=?", (form["email"].strip().lower(),)).fetchone())
            flash("Your admin account is ready. Add your team from the Team page.", "ok")
            return redirect(url_for("overview"))
    return render_template("auth/setup.html", errors=errors, form=form, code_required=code_required,
                           code_configured=bool(expected)), (422 if errors else 200)


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
        if "@" not in email:
            errors["email"] = "Enter a valid email address."
        elif db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            errors["email"] = "Someone on the team already uses that email."
        problem = password_problem(form.get("password", ""))
        if problem:
            errors["password"] = problem
        if not errors:
            create_user(db, form["name"], email, form["password"], form.get("role") if form.get("role") in ROLES else "member")
            flash(f"{form['name'].strip()} can now sign in. Share their temporary password with them directly.", "ok")
            return redirect(url_for("auth.team"))
    users = db.execute("SELECT id, name, email, role, locked_until, created_at FROM users ORDER BY name").fetchall()
    return render_template("auth/team.html", users=users, errors=errors, form=form, roles=ROLES,
                           now=now_utc().isoformat()), (422 if errors else 200)


@bp.post("/team/<int:user_id>/password")
def reset_password(user_id):
    admin_required()
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


@bp.post("/team/<int:user_id>/remove")
def remove_user(user_id):
    admin_required()
    if user_id == g.user["id"]:
        flash("You can't remove your own account.", "error")
        return redirect(url_for("auth.team"))
    db = get_db()
    db.execute("DELETE FROM users WHERE id=?", (user_id,))
    db.commit()
    flash("Team member removed. Their deals and activities keep their name.", "ok")
    return redirect(url_for("auth.team"))
