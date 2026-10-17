"""Sign-up (a new workspace for a business), sign-in, the team and their profiles, and password changes."""

import base64
import hashlib
import hmac
import io
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from flask import (Blueprint, Response, abort, current_app, flash, g, redirect, render_template, request, session,
                   url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import ukfmt
from db import DEFAULT_MONTHLY_TARGET, get_db

bp = Blueprint("auth", __name__)

MIN_PASSWORD = 10  # NCSC guidance favours length over complexity rules
MAX_FAILED = 5
LOCKOUT = timedelta(minutes=15)
ROLES = ("admin", "member")
PROFILE_FIELDS = ("job_title", "department", "phone", "location", "linkedin", "bio")
MAX_BIO = 500
MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_PHOTO_PIXELS = 40_000_000  # refuse decompression bombs before decoding
PHOTO_SIZE = 256
# Records name their owner (or author) as text, so a renamed team member takes their records along.
NAMED_COLUMNS = [("companies", "owner"), ("contacts", "owner"), ("deals", "owner"), ("activities", "owner"),
                 ("projects", "owner"), ("tickets", "owner"), ("engagements", "author")]
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
    trial = timedelta(days=int(current_app.config.get("TRIAL_DAYS") or 14))
    return db.insert("workspaces", name=name.strip(), legal_name=name.strip(), vat_registered=1,
                     monthly_target=DEFAULT_MONTHLY_TARGET, invoice_prefix="INV", payment_terms=30,
                     created_at=today.isoformat(), plan_status="trialing", trial_ends=(today + trial).isoformat())


def password_version(password_hash):
    """A fingerprint of the current password, kept in the session: changing the password signs out other sessions."""
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


def load_user():
    user_id = session.get("user_id")
    if user_id is None:
        return None
    user = get_db().execute("SELECT id, email, name, role, workspace_id, job_title, password_hash, totp_enabled_at "
                            "FROM users WHERE id=?",
                            (user_id,)).fetchone()
    if user is None:
        return None
    version = password_version(user["password_hash"])
    if "pv" not in session:
        session["pv"] = version  # sessions from before this check carry on
    elif session["pv"] != version:
        session.clear()  # the password changed since this session started
        return None
    return user


def start_session(user_id):
    session.clear()  # new session on sign-in, so an old cookie can't be reused
    session.permanent = True
    session["user_id"] = user_id
    row = get_db().execute("SELECT password_hash FROM users WHERE id=?", (user_id,)).fetchone()
    session["pv"] = password_version(row["password_hash"])


def admin_required():
    if not g.user or g.user["role"] != "admin":
        abort(403)


def process_photo(upload):
    """An uploaded image as a 256px square WebP (base64), with EXIF data such as GPS location stripped.
    Raises ValueError with a message for the person when it isn't a usable image."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    data = upload.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        raise ValueError("That photo is over 5 MB. Choose a smaller one.")
    try:
        img = Image.open(io.BytesIO(data))
        if img.width * img.height > MAX_PHOTO_PIXELS:
            raise ValueError("That photo is too large. Choose one under 40 megapixels.")
        img = ImageOps.exif_transpose(img).convert("RGB")
        img = ImageOps.fit(img, (PHOTO_SIZE, PHOTO_SIZE), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        img.save(out, "WEBP", quality=82)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError("That file isn't a photo we can read. Use a JPG, PNG or WebP image.") from None
    return base64.b64encode(out.getvalue()).decode()


def read_profile(form):
    """Validated profile values from a form, and any errors keyed by field."""
    errors = {}
    data = {"name": form.get("name", "").strip()}
    if not data["name"]:
        errors["name"] = "Enter a name."
    for key in ("job_title", "department", "location"):
        data[key] = form.get(key, "").strip()[:80]
    data["phone"] = ukfmt.normalise_phone(form.get("phone"))
    if data["phone"] is None:
        errors["phone"] = "Enter a UK number, like 0131 496 0000 or +44 7700 900123."
    linkedin = form.get("linkedin", "").strip()
    if linkedin:
        if "://" not in linkedin:
            linkedin = "https://" + linkedin
        host = (urlsplit(linkedin).hostname or "").lower()
        if urlsplit(linkedin).scheme != "https" or not (host == "linkedin.com" or host.endswith(".linkedin.com")):
            errors["linkedin"] = "Enter a LinkedIn profile link, like linkedin.com/in/your-name."
    data["linkedin"] = linkedin
    data["bio"] = form.get("bio", "").strip()
    if len(data["bio"]) > MAX_BIO:
        errors["bio"] = f"Keep it to {MAX_BIO} characters. It's {len(data['bio'])} at the moment."
    return data, errors


def save_profile(db, user, form, files):
    """Update a team member's profile and photo. Returns errors, or {} once saved."""
    data, errors = read_profile(form)
    upload = files.get("photo")
    photo = None
    if upload and upload.filename:
        try:
            photo = process_photo(upload)
        except ValueError as e:
            errors["photo"] = str(e)
    if errors:
        return errors
    db.execute(f"UPDATE users SET name=?, {', '.join(f'{k}=?' for k in PROFILE_FIELDS)} WHERE id=?",
               (data["name"], *(data[k] for k in PROFILE_FIELDS), user["id"]))
    if photo or form.get("remove_photo") == "on":
        db.execute("UPDATE users SET photo=?, photo_updated=? WHERE id=?",
                   (photo, now_utc().strftime("%Y%m%d%H%M%S") if photo else None, user["id"]))
    old = user["name"]
    namesake = db.execute("SELECT 1 FROM users WHERE workspace_id=? AND name=? AND id<>?",
                          (user["workspace_id"], old, user["id"])).fetchone()
    if data["name"] != old and not namesake:
        for table, column in NAMED_COLUMNS:
            db.execute(f"UPDATE {table} SET {column}=? WHERE workspace_id=? AND {column}=?",
                       (data["name"], user["workspace_id"], old))
    db.commit()
    return {}


def team_photo(name):
    """URL of the photo of the team member with this name, or None. For avatars on owned records."""
    if not g.get("user") or not name:
        return None
    if "team_photos" not in g:
        found = get_db().execute("SELECT id, name, photo_updated FROM users WHERE workspace_id=? AND photo IS NOT NULL",
                                 (g.user["workspace_id"],)).fetchall()
        g.team_photos = {r["name"]: url_for("auth.photo", user_id=r["id"], v=r["photo_updated"]) for r in found}
    return g.team_photos.get(name)


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
            if user["totp_enabled_at"]:
                # Password right; now the code from their authenticator app.
                session.clear()
                session["2fa_user"], session["2fa_next"], session["2fa_tries"] = user["id"], request.form.get("next"), 0
                return redirect(url_for("auth.two_factor_check"))
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


RESET_HOURS = 1
RESETS_PER_USER = 3  # an hour
RESETS_PER_IP = 10  # an hour


def reset_signer():
    from itsdangerous import URLSafeTimedSerializer
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="cae-password-reset")


@bp.route("/forgot", methods=["GET", "POST"])
def forgot():
    """Email a link to set a new password. Says the same whether or not the email has an account."""
    import mail
    from quotes import client_ip
    if g.get("user"):
        return redirect(url_for("auth.account"))
    sent, email = False, ""
    if request.method == "POST" and mail.configured():
        email = request.form.get("email", "").strip().lower()
        db = get_db()
        user = db.execute("SELECT id, name, email, password_hash FROM users WHERE email=?", (email,)).fetchone()
        since = (now_utc() - timedelta(hours=1)).isoformat()
        ip = client_ip()
        busy = db.execute("SELECT COUNT(*) FROM password_resets WHERE ip=? AND created_at >= ?", (ip, since)).fetchone()[0] >= RESETS_PER_IP
        if user and not busy and db.execute("SELECT COUNT(*) FROM password_resets WHERE user_id=? AND created_at >= ?",
                                            (user["id"], since)).fetchone()[0] < RESETS_PER_USER:
            token = reset_signer().dumps({"u": user["id"], "v": password_version(user["password_hash"])})
            link = url_for("auth.reset", token=token, _external=True)
            business = {"name": "CAE CRM"}
            html = render_template("emails/notice.html", business=business, heading="Reset your password", paragraphs=[
                f"Hi {user['name'].split()[0]},",
                "Someone asked to reset the password for your CAE CRM account. If it was you, choose a new password "
                f"using the button below. The link works once and lasts {RESET_HOURS} hour.",
                "If it wasn't you, ignore this email. Your password won't change."],
                button_url=link, button_label="Choose a new password",
                footer="You're getting this because a password reset was requested for this email address on CAE CRM.")
            text = (f"Hi {user['name'].split()[0]},\n\nChoose a new CAE CRM password here (works once, for {RESET_HOURS} hour):\n"
                    f"{link}\n\nIf you didn't ask for this, ignore this email.\n")
            try:
                mail.send(mail.message(user["email"], "Reset your CAE CRM password", html, text, "CAE CRM"))
            except mail.MailError:
                current_app.logger.warning("Password reset email not sent")
        db.insert("password_resets", user_id=user["id"] if user else None, ip=ip, created_at=now_utc().isoformat())
        db.commit()
        sent = True
    return render_template("auth/forgot.html", sent=sent, email=email, can_email=mail.configured())


@bp.route("/reset/<token>", methods=["GET", "POST"])
def reset(token):
    from itsdangerous import BadSignature
    try:
        data = reset_signer().loads(token, max_age=RESET_HOURS * 3600)
    except BadSignature:  # expired or tampered with
        data = None
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (data["u"],)).fetchone() if data else None
    if not user or password_version(user["password_hash"]) != data.get("v"):
        return render_template("auth/reset.html", invalid=True, errors={}), 400  # used already, or the password changed
    errors = {}
    if request.method == "POST":
        problem = password_problem(request.form.get("password", ""), request.form.get("confirm", ""))
        if problem:
            errors["password"] = problem
        else:
            db.execute("UPDATE users SET password_hash=?, failed_logins=0, locked_until=NULL WHERE id=?",
                       (generate_password_hash(request.form["password"]), user["id"]))
            db.commit()
            session.clear()
            flash("Password changed. Sign in with your new password. Any devices signed in to your account were signed out.", "ok")
            return redirect(url_for("auth.login"))
    return render_template("auth/reset.html", invalid=False, errors=errors, email=user["email"]), (422 if errors else 200)


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
            new_hash = generate_password_hash(request.form["password"])
            db.execute("UPDATE users SET password_hash=? WHERE id=?", (new_hash, g.user["id"]))
            db.commit()
            session["pv"] = password_version(new_hash)  # stay signed in here; other sessions are signed out
            flash("Password changed. Any other devices signed in to your account have been signed out.", "ok")
            return redirect(url_for("auth.account"))
    return _account_page(errors=errors), (422 if errors else 200)


def _account_page(**context):
    me = get_db().execute("SELECT * FROM users WHERE id=?", (g.user["id"],)).fetchone()
    context.setdefault("errors", {})
    context.setdefault("profile_errors", {})
    import json
    recovery_left = len(json.loads(me["recovery_codes"] or "[]"))
    return render_template("auth/account.html", me=me, profile=context.pop("profile", me), max_bio=MAX_BIO,
                           recovery_left=recovery_left, **context)


@bp.post("/account/profile")
def account_profile():
    db = get_db()
    me = db.execute("SELECT * FROM users WHERE id=?", (g.user["id"],)).fetchone()
    errors = save_profile(db, me, request.form, request.files)
    if errors:
        return _account_page(profile_errors=errors, profile=request.form), 422
    flash("Profile saved.", "ok")
    return redirect(url_for("auth.account"))


TEAM_COLUMNS = ("id, name, email, role, locked_until, created_at, job_title, department, phone, location, linkedin, "
                "bio, photo_updated")


@bp.route("/team", methods=["GET", "POST"])
def team():
    """Everyone can see who's on the team; only admins can add people."""
    db = get_db()
    errors, form = {}, {}
    if request.method == "POST":
        admin_required()
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
            user_id = create_user(db, g.user["workspace_id"], form["name"], email, form["password"],
                                  form.get("role") if form.get("role") in ROLES else "member")
            job_title = form.get("job_title", "").strip()[:80]
            if job_title:
                db.execute("UPDATE users SET job_title=? WHERE id=?", (job_title, user_id))
                db.commit()
            from billing import sync_seats
            sync_seats(g.user["workspace_id"])
            flash(f"{form['name'].strip()} can now sign in. Share their temporary password with them directly.", "ok")
            return redirect(url_for("auth.team"))
    users = db.execute(f"SELECT {TEAM_COLUMNS} FROM users WHERE workspace_id=? ORDER BY name",
                       (g.user["workspace_id"],)).fetchall()
    return render_template("auth/team.html", users=users, errors=errors, form=form, roles=ROLES,
                           now=now_utc().isoformat()), (422 if errors else 200)


def _team_member(user_id):
    row = get_db().execute("SELECT * FROM users WHERE id=? AND workspace_id=?", (user_id, g.user["workspace_id"])).fetchone()
    if row is None:
        abort(404)
    return row


@bp.get("/team/<int:user_id>")
def member(user_id):
    """A team member's profile: who they are, how to reach them, and what they're working on."""
    from core import OPEN_SQL, rows, scalar, today
    person = _team_member(user_id)
    ws_id, name, t = g.user["workspace_id"], person["name"], today()
    month_start = t.replace(day=1).isoformat()
    stats = dict(
        open_deals=scalar(f"SELECT COUNT(*) FROM deals WHERE workspace_id=? AND owner=? AND {OPEN_SQL}", ws_id, name),
        pipeline=scalar(f"SELECT SUM(value) FROM deals WHERE workspace_id=? AND owner=? AND {OPEN_SQL}", ws_id, name),
        won_month=scalar("SELECT SUM(value) FROM deals WHERE workspace_id=? AND owner=? AND stage='Won' "
                         "AND substr(closed_at,1,10) >= ?", ws_id, name, month_start),
        open_tickets=scalar("SELECT COUNT(*) FROM tickets WHERE workspace_id=? AND owner=? AND status <> 'Closed'",
                            ws_id, name),
        overdue_tasks=scalar("SELECT COUNT(*) FROM activities WHERE workspace_id=? AND owner=? AND done=0 "
                             "AND substr(due_at,1,10) < ?", ws_id, name, t.isoformat()),
    )
    deals = rows(f"SELECT d.id, d.title, d.value, d.stage, d.close_date, c.name AS company FROM deals d "
                 f"JOIN companies c ON c.id=d.company_id WHERE d.workspace_id=? AND d.owner=? AND d.{OPEN_SQL} "
                 f"ORDER BY d.close_date LIMIT 6", ws_id, name)
    tasks = rows("SELECT id, subject, kind, due_at FROM activities WHERE workspace_id=? AND owner=? AND done=0 "
                 "ORDER BY due_at LIMIT 6", ws_id, name)
    return render_template("auth/member.html", person=person, stats=stats, deals=deals, tasks=tasks, roles=ROLES,
                           locked=bool(person["locked_until"] and person["locked_until"] > now_utc().isoformat()))


@bp.route("/team/<int:user_id>/edit", methods=["GET", "POST"])
def edit_member(user_id):
    """Admins can fill in anyone's profile, for example to set job titles for the whole team."""
    admin_required()
    person = _team_member(user_id)
    if user_id == g.user["id"]:
        return redirect(url_for("auth.account"))
    errors, form = {}, person
    if request.method == "POST":
        errors = save_profile(get_db(), person, request.form, request.files)
        if not errors:
            flash("Profile saved.", "ok")
            return redirect(url_for("auth.member", user_id=user_id))
        form = request.form
    return render_template("auth/member_edit.html", person=person, profile=form, profile_errors=errors,
                           max_bio=MAX_BIO), (422 if errors else 200)


@bp.get("/team/<int:user_id>/photo")
def photo(user_id):
    row = get_db().execute("SELECT photo, photo_updated FROM users WHERE id=? AND workspace_id=? AND photo IS NOT NULL",
                           (user_id, g.user["workspace_id"])).fetchone()
    if row is None:
        abort(404)
    resp = Response(base64.b64decode(row["photo"]), mimetype="image/webp")
    # The URL carries ?v=<when it changed>, so a cached copy is never stale.
    resp.headers["Cache-Control"] = "private, max-age=31536000, immutable"
    return resp


@bp.post("/team/<int:user_id>/password")
def reset_password(user_id):
    admin_required()
    _team_member(user_id)
    problem = password_problem(request.form.get("password", ""))
    if problem:
        flash(f"Password not reset. {problem}", "error")
        return redirect(url_for("auth.member", user_id=user_id))
    db = get_db()
    db.execute("UPDATE users SET password_hash=?, failed_logins=0, locked_until=NULL WHERE id=?",
               (generate_password_hash(request.form["password"]), user_id))
    db.commit()
    flash("Password reset and account unlocked.", "ok")
    return redirect(url_for("auth.member", user_id=user_id))


@bp.post("/team/<int:user_id>/role")
def change_role(user_id):
    admin_required()
    _team_member(user_id)
    role = request.form.get("role")
    if role not in ROLES or user_id == g.user["id"]:
        flash("You can't change your own role.", "error")
        return redirect(url_for("auth.member", user_id=user_id))
    db = get_db()
    db.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
    db.commit()
    flash("Role updated.", "ok")
    return redirect(url_for("auth.member", user_id=user_id))


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
    from billing import sync_seats
    sync_seats(g.user["workspace_id"])
    flash("Team member removed. Their deals and activities keep their name.", "ok")
    return redirect(url_for("auth.team"))


import twofactor  # noqa: E402  (its pages join this blueprint)

twofactor.register(bp, dict(get_db=get_db, start_session=start_session, admin_required=admin_required,
                            team_member=_team_member, now_utc=now_utc, safe_next=safe_next))
