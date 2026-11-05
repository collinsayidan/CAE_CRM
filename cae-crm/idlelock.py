"""The screen lock: after a spell with nothing done, the app asks for the password again (no authenticator code).

The page underneath stays as it was, so nothing typed is lost. The browser shows the lock on time (app.js) and the
server enforces it too: once the session has been idle for the workspace's lock time, every request except the unlock
itself is turned away until the password is entered. Five wrong passwords sign the person out completely.

The 12-hour limit in security.py still applies on top of this, and needs a full sign-in with two-factor."""

import time

from flask import flash, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

import security
from core import workspace
from db import get_db

LOCK_CHOICES = {15: "15 minutes", 30: "30 minutes", 60: "1 hour", 240: "4 hours"}
DEFAULT_MINUTES = 30
WARN_SECONDS = 120  # the browser warns this long before locking
ALLOWED_WHILE_LOCKED = {"unlock", "session_lock", "auth.logout", "static", "favicon", "healthz"}


def lock_minutes():
    minutes = workspace()["lock_minutes"] if g.get("user") else None
    return minutes if minutes in LOCK_CHOICES else DEFAULT_MINUTES


def enabled():
    return bool(g.get("user")) and not g.get("demo")


def is_locked():
    if "screen_locked" in g:
        return g.screen_locked
    row = g.get("user_session")
    return bool(row and row["locked"])


def set_locked(locked):
    """Kept on the server's record of this sign-in, so a request carrying an older cookie can't undo it."""
    row = g.get("user_session")
    g.screen_locked = locked
    if row is None:
        return
    get_db().execute("UPDATE user_sessions SET locked=?, unlocked_at=? WHERE id=?",
                     (1 if locked else 0, row["unlocked_at"] if locked else int(time.time()), row["id"]))
    get_db().commit()


def check(public=()):
    """Called before every signed-in request. Returns a response when the session is locked, else None.
    Public pages, such as a quote a customer signs, open as usual: they show nothing the lock protects."""
    if not enabled():
        return None
    now = time.time()
    row = g.get("user_session")
    # The last activity this cookie knows of, but never before the last unlock.
    last = max(session.get("last_active") or 0, (row["unlocked_at"] or 0) if row else 0) or None
    locked = is_locked()
    if not locked and last is not None and now - last > lock_minutes() * 60:
        set_locked(True)
        locked = True
    if locked:
        if request.endpoint in ALLOWED_WHILE_LOCKED or request.endpoint in public:
            return None
        if request.headers.get("X-Requested-With") == "fetch" or request.path.startswith("/api/"):
            return jsonify(error="Your screen is locked. Enter your password to carry on.", locked=True), 401
        if request.method == "GET":
            return redirect(url_for("unlock", next=request.full_path.rstrip("?")))
        return redirect(url_for("unlock"))
    # Activity: note it, but rewrite the cookie at most every 15 seconds.
    if last is None or now - last > 15:
        session["last_active"] = now
    return None


def _sign_out_fully():
    security.end_current()
    get_db().commit()
    session.clear()


def register(app):
    @app.context_processor
    def lock_settings():
        return {"lock_after": lock_minutes() * 60 if enabled() else None, "lock_warn": WARN_SECONDS}

    @app.route("/unlock", methods=["GET", "POST"])
    def unlock():
        from auth import LOCKOUT, MAX_FAILED, now_utc, safe_next
        if not g.get("user"):
            return redirect(url_for("auth.login"))
        fetch = request.headers.get("X-Requested-With") == "fetch"
        target = request.values.get("next", "")
        if not is_locked():
            return jsonify(ok=True) if fetch else redirect(safe_next(target))
        error = None
        if request.method == "POST":
            db = get_db()
            user = db.execute("SELECT password_hash, failed_logins FROM users WHERE id=?", (g.user["id"],)).fetchone()
            if security.too_many_failures():
                error = "Too many attempts from your network. Wait 15 minutes, then try again."
            elif check_password_hash(user["password_hash"], request.form.get("password", "")):
                db.execute("UPDATE users SET failed_logins=0 WHERE id=?", (g.user["id"],))
                db.commit()
                set_locked(False)
                session["last_active"] = time.time()
                return jsonify(ok=True) if fetch else redirect(safe_next(target))
            else:
                # Counted on the account, not the cookie, so an old copy of the cookie can't reset the count.
                fails = (user["failed_logins"] or 0) + 1
                security.note_failure()
                if fails >= MAX_FAILED:
                    db.execute("UPDATE users SET failed_logins=0, locked_until=? WHERE id=?",
                               ((now_utc() + LOCKOUT).isoformat(), g.user["id"]))
                    _sign_out_fully()
                    flash("Too many wrong passwords, so you've been signed out. Try again in 15 minutes.", "error")
                    if fetch:
                        return jsonify(error="Signed out.", signed_out=True, url=url_for("auth.login")), 401
                    return redirect(url_for("auth.login"))
                db.execute("UPDATE users SET failed_logins=? WHERE id=?", (fails, g.user["id"]))
                db.commit()
                left = MAX_FAILED - fails
                error = f"That password isn't right. {left} {'try' if left == 1 else 'tries'} left before you're signed out."
            if fetch:
                return jsonify(error=error), 401
        return render_template("auth/unlock.html", error=error, next=target), (401 if error else 200)

    @app.post("/session/lock")
    def session_lock():
        """The browser locked the screen on time: lock here too, so only the password opens it again."""
        set_locked(True)
        return "", 204

    @app.post("/session/active")
    def session_active():
        """The browser saying someone is using the page. The guard has already noted the activity."""
        return "", 204
