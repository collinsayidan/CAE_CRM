"""Two-factor sign-in with an authenticator app (TOTP, RFC 6238): a 6-digit code that changes every 30 seconds.
Required for admins, optional for everyone else. The secret is stored encrypted; each code works once; ten one-off
recovery codes cover a lost phone, and an admin can reset a team member's two-factor sign-in."""

import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from urllib.parse import quote

from flask import current_app, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

STEP = 30
DIGITS = 6
WINDOW = 1  # also accept the code just before and just after, for clocks a little out
MAX_TRIES = 5
RECOVERY_CODES = 10
ISSUER = "CAE CRM"


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def code_at(secret, step):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10 ** DIGITS).zfill(DIGITS)


def matching_step(secret, code, last_step=None, now=None):
    """The time step a code belongs to, or None. A step already used can't be used again."""
    code = "".join(ch for ch in str(code) if ch.isdigit())
    if len(code) != DIGITS:
        return None
    current = int((now or time.time()) // STEP)
    for step in range(current - WINDOW, current + WINDOW + 1):
        if (last_step is None or step > last_step) and hmac.compare_digest(code_at(secret, step), code):
            return step
    return None


def setup_uri(secret, email):
    label = quote(f"{ISSUER}:{email}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(ISSUER)}&digits={DIGITS}&period={STEP}"


def qr_svg(uri):
    import segno
    return segno.make(uri, error="m").svg_inline(scale=5, dark="#0f1f3d", light="#ffffff", border=2)


def make_recovery_codes():
    codes = [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(RECOVERY_CODES)]
    return codes, json.dumps([generate_password_hash(c) for c in codes])


def use_recovery_code(db, user, code):
    """True if the code is one of the user's unused recovery codes, which is then used up."""
    code = code.strip().lower()
    stored = json.loads(user["recovery_codes"] or "[]")
    for i, hashed in enumerate(stored):
        if check_password_hash(hashed, code):
            del stored[i]
            db.execute("UPDATE users SET recovery_codes=? WHERE id=?", (json.dumps(stored), user["id"]))
            db.commit()
            return True
    return False


def required(user):
    # A demo's made-up admin has nothing to protect, and a visitor couldn't scan a code for it.
    return user["role"] == "admin" and current_app.config.get("ADMIN_2FA_REQUIRED", True) and not g.get("demo")


def register(bp, helpers):
    """Add the two-factor pages to the auth blueprint. helpers carries auth's own functions."""
    get_db, start_session, admin_required, team_member, now_utc, safe_next = (
        helpers["get_db"], helpers["start_session"], helpers["admin_required"], helpers["team_member"],
        helpers["now_utc"], helpers["safe_next"])
    from integrations import seal, unseal

    @bp.route("/login/two-factor", methods=["GET", "POST"])
    def two_factor_check():
        """The second step of signing in, after the password."""
        pending = session.get("2fa_user")
        if not pending:
            return redirect(url_for("auth.login"))
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE id=?", (pending,)).fetchone()
        if user is None or not user["totp_enabled_at"]:
            session.pop("2fa_user", None)
            return redirect(url_for("auth.login"))
        error = None
        if request.method == "POST":
            tries = session.get("2fa_tries", 0) + 1
            session["2fa_tries"] = tries
            code = request.form.get("code", "")
            step = matching_step(unseal(user["totp_secret"]) or "", code, user["totp_last_step"])
            ok = step is not None
            if ok:
                db.execute("UPDATE users SET totp_last_step=? WHERE id=?", (step, user["id"]))
                db.commit()
            elif "-" in code and use_recovery_code(db, user, code):
                ok = True
                flash("Signed in with a recovery code. You have fewer left: make new ones under Profile and password.", "ok")
            if ok:
                next_url = session.get("2fa_next")
                start_session(user["id"])
                return redirect(safe_next(next_url))
            if tries >= MAX_TRIES:
                session.pop("2fa_user", None)
                flash("Too many wrong codes. Sign in again.", "error")
                return redirect(url_for("auth.login"))
            error = "That code didn't work. Check your authenticator app and try again."
        return render_template("auth/two_factor_check.html", error=error), (401 if error else 200)

    @bp.route("/account/two-factor", methods=["GET", "POST"])
    def two_factor_setup():
        """Scan the QR code, confirm with a code, and get recovery codes."""
        db = get_db()
        me = db.execute("SELECT * FROM users WHERE id=?", (g.user["id"],)).fetchone()
        if me["totp_enabled_at"] and request.method == "GET" and not request.args.get("codes"):
            return redirect(url_for("auth.account"))
        if request.method == "POST" and request.form.get("regenerate") == "1" and me["totp_enabled_at"]:
            codes, hashed = make_recovery_codes()
            db.execute("UPDATE users SET recovery_codes=? WHERE id=?", (hashed, me["id"]))
            db.commit()
            return render_template("auth/two_factor_setup.html", codes=codes, done=True)
        secret = session.get("2fa_setup") or new_secret()
        session["2fa_setup"] = secret
        error = None
        if request.method == "POST":
            step = matching_step(secret, request.form.get("code", ""))
            if step is None:
                error = "That code didn't match. Make sure you scanned the code on this page, then try the newest code."
            else:
                codes, hashed = make_recovery_codes()
                db.execute("UPDATE users SET totp_secret=?, totp_enabled_at=?, totp_last_step=?, recovery_codes=? WHERE id=?",
                           (seal(secret), now_utc().isoformat(timespec="seconds"), step, hashed, me["id"]))
                db.commit()
                session.pop("2fa_setup", None)
                return render_template("auth/two_factor_setup.html", codes=codes, done=True)
        uri = setup_uri(secret, me["email"])
        return render_template("auth/two_factor_setup.html", done=False, qr=qr_svg(uri), secret=secret, uri=uri,
                               error=error, forced=required(me) and not me["totp_enabled_at"]), (422 if error else 200)

    @bp.post("/account/two-factor/off")
    def two_factor_off():
        if required(g.user):
            flash("Admins must keep two-factor sign-in on. You can make new recovery codes instead.", "error")
            return redirect(url_for("auth.account"))
        db = get_db()
        db.execute("UPDATE users SET totp_secret=NULL, totp_enabled_at=NULL, totp_last_step=NULL, recovery_codes=NULL "
                   "WHERE id=?", (g.user["id"],))
        db.commit()
        flash("Two-factor sign-in is off.", "ok")
        return redirect(url_for("auth.account"))

    @bp.post("/team/<int:user_id>/two-factor/reset")
    def two_factor_reset(user_id):
        """For someone who's lost their phone and their recovery codes. They set it up again at next sign-in."""
        admin_required()
        team_member(user_id)
        if user_id == g.user["id"]:
            flash("You can't reset your own two-factor sign-in. Ask another admin, or use a recovery code.", "error")
            return redirect(url_for("auth.member", user_id=user_id))
        db = get_db()
        db.execute("UPDATE users SET totp_secret=NULL, totp_enabled_at=NULL, totp_last_step=NULL, recovery_codes=NULL "
                   "WHERE id=? AND workspace_id=?", (user_id, g.user["workspace_id"]))
        db.commit()
        flash("Two-factor sign-in reset. They'll set it up again when they next sign in.", "ok")
        return redirect(url_for("auth.member", user_id=user_id))
