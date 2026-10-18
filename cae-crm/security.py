"""Account security: confirming email addresses, inviting colleagues by email, the list of places someone is signed
in, alerts for sign-ins from a new device, a limit on failed sign-ins from one network, and refusing passwords that
have appeared in known data breaches.

Sessions are recorded on the server (user_sessions), so signing out, changing a password or "sign out everywhere"
ends them for real, and each person can see where they're signed in. A long-lived cae_device cookie recognises a
browser, so a sign-in from one that hasn't been used before can be emailed to the person.

Breached passwords are checked with Have I Been Pwned's range API: only the first five characters of the password's
SHA-1 hash leave the server, never the password. If the service can't be reached, the password is allowed. Tests set
BREACH_CHECK to False, or BREACH_BACKEND to a fake that takes a hash prefix and returns the API's text."""

import hashlib
import secrets
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from flask import current_app, flash, g, jsonify, redirect, render_template, request, session, url_for

from db import get_db

DEVICE_COOKIE = "cae_device"
SESSION_IDLE = timedelta(hours=12)  # matches PERMANENT_SESSION_LIFETIME: a sign-in ends after 12 hours unused
SEEN_EVERY = timedelta(minutes=5)  # how often "last active" is updated, so most requests don't write
FAILURE_WINDOW = timedelta(minutes=15)
FAILURES_PER_IP = 20
VERIFY_DAYS = 7
INVITE_DAYS = 7
RESEND_EVERY = timedelta(minutes=5)
# Pages that send email to customers or colleagues: not until the person has confirmed their own email address.
SENDS_EMAIL = {"email_invoice", "remind_invoice", "email_quote", "campaign_test", "campaign_start", "campaign_deliver",
               "auth.team", "auth.resend_invite", "ticket_reply"}


def now_utc():
    return datetime.now(timezone.utc)


def stamp(when=None):
    return (when or now_utc()).isoformat(timespec="seconds")


def client_ip():
    from quotes import client_ip as ip
    return ip()


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


# --- Devices and sessions ---------------------------------------------------------------------------------------------

def device_id():
    """This browser's device id, made on first sight and saved in a cookie when the response goes out."""
    found = request.cookies.get(DEVICE_COOKIE, "")
    if len(found) == 32 and found.isalnum():
        return found
    if "new_device_id" not in g:
        g.new_device_id = secrets.token_hex(16)
    return g.new_device_id


def describe(user_agent):
    """'Chrome on Windows' from a browser's user agent, for the list of sessions and sign-in alerts."""
    ua = user_agent or ""
    browser = next((name for key, name in (("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"),
                                          ("CriOS", "Chrome"), ("Chrome/", "Chrome"), ("Safari/", "Safari"))
                    if key in ua), "A browser")
    system = next((name for key, name in (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"),
                                         ("CrOS", "ChromeOS"), ("Windows", "Windows"), ("Macintosh", "Mac"),
                                         ("Linux", "Linux")) if key in ua), "an unknown device")
    return f"{browser} on {system}"


def open_session(user):
    """Record a new sign-in on the server and remember its token in the cookie. Emails the person if this is a device
    they haven't signed in from before (other than on their very first sign-in). No commit."""
    db, when = get_db(), stamp()
    token = secrets.token_urlsafe(32)
    db.insert("user_sessions", user_id=user["id"], workspace_id=user["workspace_id"], token_hash=token_hash(token),
              device_id=device_id(), ip=client_ip(), user_agent=(request.user_agent.string or "")[:300],
              created_at=when, last_seen_at=when)
    session["sid"] = token
    device = device_id()
    known = [r[0] for r in db.execute("SELECT device_id FROM known_devices WHERE user_id=?", (user["id"],)).fetchall()]
    if device not in known:
        db.insert("known_devices", user_id=user["id"], device_id=device, first_seen_at=when)
        if known:
            new_device_alert(user)


def session_ok(user):
    """Whether this cookie's sign-in is still live on the server, noting when it was last used."""
    db = get_db()
    sid = session.get("sid")
    if not sid:
        open_session(user)  # a sign-in from before sessions were recorded carries on, and now shows in the list
        db.commit()
        return True
    row = db.execute("SELECT id, last_seen_at FROM user_sessions WHERE token_hash=? AND user_id=?",
                     (token_hash(sid), user["id"])).fetchone()
    if row is None:
        return False
    seen = datetime.fromisoformat(row["last_seen_at"])
    if now_utc() - seen > SESSION_IDLE:
        db.execute("DELETE FROM user_sessions WHERE id=?", (row["id"],))
        db.commit()
        return False
    if now_utc() - seen > SEEN_EVERY:
        db.execute("UPDATE user_sessions SET last_seen_at=?, ip=? WHERE id=?", (stamp(), client_ip(), row["id"]))
        db.commit()
    return True


def current_session_id():
    sid = session.get("sid")
    if not sid:
        return None
    row = get_db().execute("SELECT id FROM user_sessions WHERE token_hash=?", (token_hash(sid),)).fetchone()
    return row["id"] if row else None


def end_current():
    if session.get("sid"):
        get_db().execute("DELETE FROM user_sessions WHERE token_hash=?", (token_hash(session["sid"]),))


def end_others(user_id):
    get_db().execute("DELETE FROM user_sessions WHERE user_id=? AND token_hash<>?",
                     (user_id, token_hash(session.get("sid") or "")))


def end_all(user_id):
    get_db().execute("DELETE FROM user_sessions WHERE user_id=?", (user_id,))


def sessions_for(user_id):
    cutoff = stamp(now_utc() - SESSION_IDLE)
    get_db().execute("DELETE FROM user_sessions WHERE user_id=? AND last_seen_at < ?", (user_id, cutoff))
    current = current_session_id()
    found = get_db().execute("SELECT * FROM user_sessions WHERE user_id=? ORDER BY last_seen_at DESC",
                             (user_id,)).fetchall()
    return [dict(id=r["id"], device=describe(r["user_agent"]), ip=r["ip"], last_seen=uk_time(r["last_seen_at"]),
                 started=uk_time(r["created_at"]), current=r["id"] == current) for r in found]


def uk_time(value):
    """A stored UTC time as UK local time (naive), for showing to people."""
    from core import UK_TZ
    return datetime.fromisoformat(value).astimezone(UK_TZ).replace(tzinfo=None).isoformat(timespec="minutes")


def purge():
    """For the daily job: forget expired sessions and old failed sign-ins."""
    db = get_db()
    db.execute("DELETE FROM user_sessions WHERE last_seen_at < ?", (stamp(now_utc() - SESSION_IDLE),))
    db.execute("DELETE FROM sign_in_failures WHERE created_at < ?", (stamp(now_utc() - timedelta(days=1)),))
    db.commit()


# --- Sign-in limits ---------------------------------------------------------------------------------------------------

def too_many_failures():
    since = stamp(now_utc() - FAILURE_WINDOW)
    count = get_db().execute("SELECT COUNT(*) FROM sign_in_failures WHERE ip=? AND created_at >= ?",
                             (client_ip(), since)).fetchone()[0]
    return count >= FAILURES_PER_IP


def note_failure():
    get_db().insert("sign_in_failures", ip=client_ip(), created_at=stamp())


# --- Breached passwords -----------------------------------------------------------------------------------------------

def breach_count(password):
    """How many times this password appears in Have I Been Pwned's breach data, or None if we couldn't check."""
    if not current_app.config.get("BREACH_CHECK", True):
        return None
    digest = hashlib.sha1(password.encode()).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    fake = current_app.config.get("BREACH_BACKEND")
    try:
        if fake:
            body = fake(prefix)
        else:
            req = urllib.request.Request(f"https://api.pwnedpasswords.com/range/{prefix}",
                                         headers={"Add-Padding": "true", "User-Agent": "CAE-CRM"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                body = resp.read().decode()
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        current_app.logger.warning("Couldn't check a password against Have I Been Pwned")
        return None
    for line in body.splitlines():
        found, _, count = line.strip().partition(":")
        if found == suffix and count.isdigit() and int(count) > 0:
            return int(count)
    return 0


def breach_problem(password):
    count = breach_count(password)
    if count:
        times = f"{count:,} times" if count > 1 else "once"
        return (f"That password has turned up in data breaches ({times}), so it's one of the first that attackers "
                "try. Choose a different one.")
    return None


# --- Emails -----------------------------------------------------------------------------------------------------------

def _signer(salt):
    from itsdangerous import URLSafeTimedSerializer
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=salt)


def _send(to, subject, heading, paragraphs, button_url, button_label, footer, text, from_name="CAE CRM"):
    import mail
    html = render_template("emails/notice.html", business={"name": from_name}, heading=heading, paragraphs=paragraphs,
                           button_url=button_url, button_label=button_label, footer=footer)
    try:
        mail.send(mail.message(to, subject, html, text, from_name))
        return True
    except mail.MailError:
        current_app.logger.warning("%s email not sent", heading)
        return False


def first_name(user):
    return (user["name"] or "there").split()[0]


def new_device_alert(user):
    import mail
    if not mail.configured():
        return
    from ukfmt import uk_datetime
    from core import now
    device, ip = describe(request.user_agent.string), client_ip()
    when = uk_datetime(now().isoformat(timespec="minutes"))
    link = url_for("auth.account", _external=True) + "#sessions"
    _send(user["email"], "New sign-in to your CAE CRM account", "New sign-in to your account", [
        f"Hi {first_name(user)},",
        f"Someone signed in to your CAE CRM account from a device we haven't seen before: {device}, "
        f"IP address {ip}, at {when} UK time.",
        "If it was you, there's nothing to do. If it wasn't, change your password straight away and sign out "
        "everywhere else from Profile and password."],
        link, "Check where you're signed in",
        "You're getting this because a new device signed in to your CAE CRM account.",
        f"Hi {first_name(user)},\n\nNew sign-in to your CAE CRM account: {device}, IP {ip}, at {when} UK time.\n"
        f"If it wasn't you, change your password and sign out everywhere else: {link}\n")


def needs_verification(user):
    """Whether this person must confirm their email address before sending email or inviting anyone."""
    import mail
    return bool(user) and not user["email_verified_at"] and mail.configured()


def send_verification(user):
    token = _signer("cae-verify-email").dumps({"u": user["id"], "e": user["email"]})
    link = url_for("auth.verify_email", token=token, _external=True)
    get_db().execute("UPDATE users SET verify_sent_at=? WHERE id=?", (stamp(), user["id"]))
    return _send(user["email"], "Confirm your email address for CAE CRM", "Confirm your email address", [
        f"Hi {first_name(user)},",
        "Please confirm this is your email address, so CAE CRM can send emails for your business and you can "
        f"invite your team. The link lasts {VERIFY_DAYS} days."],
        link, "Confirm my email address",
        "You're getting this because this email address was used to sign up to CAE CRM.",
        f"Hi {first_name(user)},\n\nConfirm your email address for CAE CRM (link lasts {VERIFY_DAYS} days):\n{link}\n")


def invite_token(user):
    from auth import password_version
    return _signer("cae-invite").dumps({"u": user["id"], "v": password_version(user["password_hash"])})


def send_invite(user, inviter, workspace):
    link = url_for("auth.accept_invite", token=invite_token(user), _external=True)
    get_db().execute("UPDATE users SET invited_at=?, invited_by=? WHERE id=?", (stamp(), inviter["name"], user["id"]))
    return _send(user["email"], f"{inviter['name']} invited you to {workspace['name']} on CAE CRM",
                 f"Join {workspace['name']} on CAE CRM", [
                     f"Hi {first_name(user)},",
                     f"{inviter['name']} has invited you to join {workspace['name']} on CAE CRM, where the team keeps "
                     f"its customers, deals and support tickets. Choose your password to get started. The link lasts "
                     f"{INVITE_DAYS} days and works once."],
                 link, "Accept the invite",
                 f"You're getting this because {inviter['name']} added this email address to {workspace['name']}.",
                 f"Hi {first_name(user)},\n\n{inviter['name']} invited you to {workspace['name']} on CAE CRM.\n"
                 f"Accept and choose your password (link lasts {INVITE_DAYS} days):\n{link}\n", workspace["name"])


# --- Pages ------------------------------------------------------------------------------------------------------------

def register(bp):

    @bp.after_app_request
    def save_device_cookie(response):
        if g.get("new_device_id"):
            response.set_cookie(DEVICE_COOKIE, g.new_device_id, max_age=2 * 365 * 24 * 3600, httponly=True,
                                samesite="Lax", secure=current_app.config.get("SESSION_COOKIE_SECURE", False))
        return response

    @bp.before_app_request
    def hold_email_until_verified():
        """Someone who hasn't confirmed their email address can't send email or invite people yet."""
        if request.method != "POST" or request.endpoint not in SENDS_EMAIL or not needs_verification(g.get("user")):
            return None
        message = "Confirm your email address first. We sent you a link; you can ask for a new one at the top of the page."
        if request.headers.get("X-Requested-With") == "fetch":
            return jsonify(error=message), 403
        flash(message, "error")
        target = request.form.get("next") or request.referrer or ""
        from urllib.parse import urlsplit
        path = urlsplit(target).path
        return redirect(path if path.startswith("/") and not path.startswith("//") else url_for("overview"))

    @bp.app_context_processor
    def verification_banner():
        user = g.get("user")
        return {"needs_verify": needs_verification(user)} if user else {}

    @bp.get("/verify/<token>")
    def verify_email(token):
        from itsdangerous import BadSignature
        try:
            data = _signer("cae-verify-email").loads(token, max_age=VERIFY_DAYS * 86400)
        except BadSignature:
            data = None
        db = get_db()
        user = db.execute("SELECT id, email, email_verified_at FROM users WHERE id=?", (data["u"],)).fetchone() \
            if data else None
        if not user or user["email"] != data.get("e"):
            flash("That confirmation link has expired or isn't valid. Sign in and ask for a new one.", "error")
            return redirect(url_for("overview") if g.get("user") else url_for("auth.login"))
        if not user["email_verified_at"]:
            db.execute("UPDATE users SET email_verified_at=? WHERE id=?", (stamp(), user["id"]))
            db.commit()
        flash("Thanks, your email address is confirmed.", "ok")
        return redirect(url_for("overview") if g.get("user") else url_for("auth.login"))

    @bp.post("/verify/resend")
    def resend_verification():
        db = get_db()
        me = db.execute("SELECT * FROM users WHERE id=?", (g.user["id"],)).fetchone()
        back = redirect(request.referrer if (request.referrer or "").startswith(request.host_url) else url_for("overview"))
        if me["email_verified_at"]:
            return back
        if me["verify_sent_at"] and now_utc() - datetime.fromisoformat(me["verify_sent_at"]) < RESEND_EVERY:
            flash("We sent a link a few minutes ago. Check your inbox and spam folder, or try again shortly.", "error")
            return back
        sent = send_verification(me)
        db.commit()
        flash(f"We've sent a new link to {me['email']}." if sent else "The email couldn't be sent. Try again later.",
              "ok" if sent else "error")
        return back

    @bp.route("/invite/<token>", methods=["GET", "POST"])
    def accept_invite(token):
        from itsdangerous import BadSignature
        from werkzeug.security import generate_password_hash
        from auth import password_problem, password_version, start_session
        try:
            data = _signer("cae-invite").loads(token, max_age=INVITE_DAYS * 86400)
        except BadSignature:
            data = None
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE id=?", (data["u"],)).fetchone() if data else None
        if not user or password_version(user["password_hash"]) != data.get("v") or user["invite_accepted_at"]:
            return render_template("auth/invite.html", invalid=True, errors={}), 400
        w = db.execute("SELECT * FROM workspaces WHERE id=?", (user["workspace_id"],)).fetchone()
        errors = {}
        if request.method == "POST":
            problem = password_problem(request.form.get("password", ""), request.form.get("confirm", ""))
            if problem:
                errors["password"] = problem
            else:
                when = stamp()
                db.execute("UPDATE users SET password_hash=?, email_verified_at=?, invite_accepted_at=?, failed_logins=0, "
                           "locked_until=NULL WHERE id=?",
                           (generate_password_hash(request.form["password"]), when, when, user["id"]))
                db.commit()
                start_session(user["id"])
                db.commit()
                flash(f"Welcome to {w['name']} on CAE CRM.", "ok")
                return redirect(url_for("overview"))
        from documents import logo_url
        return render_template("auth/invite.html", invalid=False, errors=errors, person=user, w=w, logo=logo_url(w)), \
            (422 if errors else 200)

    @bp.post("/team/<int:user_id>/invite")
    def resend_invite(user_id):
        from auth import _team_member, admin_required
        admin_required()
        person = _team_member(user_id)
        if not person["invited_at"] or person["invite_accepted_at"]:
            flash("They've already joined.", "error")
            return redirect(url_for("auth.team"))
        from core import workspace
        sent = send_invite(person, g.user, workspace())
        get_db().commit()
        flash(f"Invite sent again to {person['email']}." if sent else "The invite couldn't be sent. Try again later.",
              "ok" if sent else "error")
        return redirect(url_for("auth.team"))

    @bp.post("/account/sessions/<int:session_id>/end")
    def end_session(session_id):
        db = get_db()
        if session_id == current_session_id():
            return redirect(url_for("auth.logout"), 307)
        db.execute("DELETE FROM user_sessions WHERE id=? AND user_id=?", (session_id, g.user["id"]))
        db.commit()
        flash("That device has been signed out.", "ok")
        return redirect(url_for("auth.account") + "#sessions")

    @bp.post("/account/sessions/end-others")
    def end_other_sessions():
        end_others(g.user["id"])
        get_db().commit()
        flash("You've been signed out everywhere else.", "ok")
        return redirect(url_for("auth.account") + "#sessions")
