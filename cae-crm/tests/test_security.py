import hashlib
import re
import urllib.error

import pytest

from conftest import ADMIN, MEMBER, first_id, login, make_app, query, refresh_csrf
from db import get_db, init_db

SIGNUP = {"business": "Bramble & Oak Ltd", "name": "Ada Lovelace", "email": "ada@example.co.uk",
          "password": "analytical engine", "confirm": "analytical engine"}


@pytest.fixture
def outbox(app):
    app.config["MAIL_BACKEND"] = "memory"
    app.extensions["outbox"] = []
    return app.extensions["outbox"]


def link_in(message, path):
    return re.search(rf'href="(http[^"]+/{path}/[^"]+)"', message["html"]).group(1).replace("http://localhost", "")


def sql(app, statement, *args):
    with app.app_context():
        get_db().execute(statement, args)
        get_db().commit()


def signed_up(app):
    c = app.test_client()
    c.get("/signup")
    refresh_csrf(c)
    assert c.post("/signup", data=SIGNUP | {"csrf": c.csrf}).status_code == 302
    c.get("/")
    return refresh_csrf(c)


def unpaid_invoice(app, ws_id):
    return first_id(app, "invoices", ws_id, "paid_date IS NULL")


# --- Confirming email addresses ---------------------------------------------------------------------------------------

def test_new_sign_ups_confirm_their_email_before_sending(app, outbox):
    c = signed_up(app)
    (welcome,) = outbox
    assert welcome["to"] == [SIGNUP["email"]] and "Confirm your email" in welcome["subject"]
    home = c.get("/").get_data(as_text=True)
    assert "Confirm your email address." in home and "Send a new link" in home
    ws_id = query(app, "SELECT workspace_id FROM users WHERE email=?", SIGNUP["email"])[0][0]
    # Nothing goes out to customers or colleagues yet.
    company = first_id(app, "companies", ws_id) if query(app, "SELECT 1 FROM companies WHERE workspace_id=?", ws_id) else None
    blocked = c.post("/team", data={"csrf": c.csrf, "name": "Ben", "email": "ben@example.co.uk"})
    assert blocked.status_code == 302 and len(outbox) == 1
    assert not query(app, "SELECT 1 FROM users WHERE email='ben@example.co.uk'")
    assert "Confirm your email address first" in c.get("/").get_data(as_text=True)
    # The link confirms it, and then sending works.
    resp = c.get(link_in(welcome, "verify"))
    assert resp.status_code == 302
    assert query(app, "SELECT email_verified_at FROM users WHERE email=?", SIGNUP["email"])[0][0]
    assert "Confirm your email address." not in c.get("/").get_data(as_text=True)
    c.post("/team", data={"csrf": c.csrf, "name": "Ben", "email": "ben@example.co.uk"})
    assert query(app, "SELECT 1 FROM users WHERE email='ben@example.co.uk'")
    assert company is None  # a new workspace without sample data has no companies


def test_unconfirmed_people_cannot_email_invoices(app, client, outbox):
    sql(app, "UPDATE users SET email_verified_at=NULL WHERE email=?", ADMIN[1])
    invoice = unpaid_invoice(app, app.ws)
    client.post(f"/invoices/{invoice}/email", data={"csrf": client.csrf, "contact_id": "", "email": "a@customer.co.uk"})
    assert not outbox
    sql(app, "UPDATE users SET email_verified_at='2026-10-16T10:00:00' WHERE email=?", ADMIN[1])
    client.post(f"/invoices/{invoice}/email", data={"csrf": client.csrf, "contact_id": "", "email": "a@customer.co.uk"})
    assert len(outbox) == 1


def test_resending_the_link_is_rate_limited(app, outbox):
    c = signed_up(app)
    c.post("/verify/resend", data={"csrf": c.csrf})
    assert len(outbox) == 1  # sent at sign-up moments ago
    sql(app, "UPDATE users SET verify_sent_at='2026-01-01T00:00:00+00:00' WHERE email=?", SIGNUP["email"])
    c.post("/verify/resend", data={"csrf": c.csrf})
    assert len(outbox) == 2 and outbox[-1]["to"] == [SIGNUP["email"]]


def test_bad_or_changed_links_do_not_confirm(app, outbox):
    c = signed_up(app)
    link = link_in(outbox[0], "verify")
    c.get(link[:-3] + "xyz")
    assert not query(app, "SELECT email_verified_at FROM users WHERE email=?", SIGNUP["email"])[0][0]
    sql(app, "UPDATE users SET email='other@example.co.uk' WHERE email=?", SIGNUP["email"])
    c.get(link)
    assert not query(app, "SELECT email_verified_at FROM users WHERE email='other@example.co.uk'")[0][0]


def test_without_email_nothing_is_held_back(app):
    c = signed_up(app)
    assert "Confirm your email address." not in c.get("/").get_data(as_text=True)


def test_people_from_before_are_already_confirmed(app):
    """Upgrading a database adds the column and counts everyone already there as confirmed."""
    with app.app_context():
        get_db().execute("ALTER TABLE users DROP COLUMN email_verified_at")
        get_db().commit()
    init_db(app.config["DATABASE"], app.config["TODAY"])
    assert all(r[0] for r in query(app, "SELECT email_verified_at FROM users"))


# --- Invites ----------------------------------------------------------------------------------------------------------

def test_invites_let_colleagues_choose_their_own_password(app, client, outbox):
    page = client.get("/team").get_data(as_text=True)
    assert "Send invite" in page and "Temporary password" not in page
    client.post("/team", data={"csrf": client.csrf, "name": "Rhys Evans", "email": "Rhys@Example.co.uk", "role": "member"})
    (invite,) = outbox
    assert invite["to"] == ["rhys@example.co.uk"] and "invited you to Thistle Ltd" in invite["subject"]
    assert "Invited, not joined yet" in client.get("/team").get_data(as_text=True)
    link = link_in(invite, "invite")
    guest = app.test_client()
    form = guest.get(link)
    assert form.status_code == 200 and "Join Thistle Ltd" in form.get_data(as_text=True)
    refresh_csrf(guest)
    assert guest.post(link, data={"csrf": guest.csrf, "password": "short", "confirm": "short"}).status_code == 422
    done = guest.post(link, data={"csrf": guest.csrf, "password": "valley of the rivers", "confirm": "valley of the rivers"})
    assert done.status_code == 302 and done.headers["Location"].endswith("/")
    assert guest.get("/").status_code == 200
    verified, accepted = query(app, "SELECT email_verified_at, invite_accepted_at FROM users WHERE email='rhys@example.co.uk'")[0]
    assert verified and accepted
    assert "Invited, not joined yet" not in client.get("/team").get_data(as_text=True)
    # The link works once.
    assert app.test_client().get(link).status_code == 400
    assert "Accepted their invite and signed in" in [r[0] for r in query(app, "SELECT action FROM audit_events")]


def test_resending_and_cancelling_invites(app, client, member_client, rival, outbox):
    client.post("/team", data={"csrf": client.csrf, "name": "Rhys Evans", "email": "rhys@example.co.uk"})
    person = query(app, "SELECT id FROM users WHERE email='rhys@example.co.uk'")[0][0]
    first_link = link_in(outbox[0], "invite")
    assert member_client.post(f"/team/{person}/invite", data={"csrf": member_client.csrf}).status_code == 403
    assert rival.post(f"/team/{person}/invite", data={"csrf": rival.csrf}).status_code == 404
    client.post(f"/team/{person}/invite", data={"csrf": client.csrf})
    assert len(outbox) == 2 and outbox[1]["to"] == ["rhys@example.co.uk"]
    client.post(f"/team/{person}/remove", data={"csrf": client.csrf})
    assert not query(app, "SELECT 1 FROM users WHERE email='rhys@example.co.uk'")
    assert app.test_client().get(first_link).status_code == 400


def test_an_invitee_who_resets_their_password_has_joined(app, client, outbox):
    client.post("/team", data={"csrf": client.csrf, "name": "Rhys Evans", "email": "rhys@example.co.uk"})
    v = app.test_client()
    v.get("/forgot")
    refresh_csrf(v)
    v.post("/forgot", data={"csrf": v.csrf, "email": "rhys@example.co.uk"})
    reset = link_in(outbox[-1], "reset")
    v.get(reset)
    refresh_csrf(v)
    v.post(reset, data={"csrf": v.csrf, "password": "valley of the rivers", "confirm": "valley of the rivers"})
    verified, accepted = query(app, "SELECT email_verified_at, invite_accepted_at FROM users WHERE email='rhys@example.co.uk'")[0]
    assert verified and accepted


# --- Sessions and devices ---------------------------------------------------------------------------------------------

def test_sessions_are_listed_and_can_be_signed_out(app):
    laptop = login(app, MEMBER[1], MEMBER[2])
    phone = login(app, MEMBER[1], MEMBER[2])
    page = laptop.get("/account").get_data(as_text=True)
    assert "Where you're signed in" in page and page.count("This device") == 1
    ids = [r[0] for r in query(app, "SELECT s.id FROM user_sessions s JOIN users u ON u.id=s.user_id WHERE u.email=? "
                                    "ORDER BY s.id", MEMBER[1])]
    assert len(ids) == 2
    laptop.post(f"/account/sessions/{ids[1]}/end", data={"csrf": laptop.csrf})
    assert phone.get("/").status_code == 302  # signed out
    assert laptop.get("/").status_code == 200


def test_sign_out_everywhere_else_and_password_changes(app):
    a, b, c = (login(app, MEMBER[1], MEMBER[2]) for _ in range(3))
    a.post("/account/sessions/end-others", data={"csrf": a.csrf})
    assert b.get("/").status_code == 302 and c.get("/").status_code == 302 and a.get("/").status_code == 200
    d = login(app, MEMBER[1], MEMBER[2])
    a.post("/account", data={"csrf": a.csrf, "current": MEMBER[2], "password": "a brand new phrase", "confirm": "a brand new phrase"})
    assert d.get("/").status_code == 302 and a.get("/").status_code == 200
    assert len(query(app, "SELECT id FROM user_sessions s WHERE user_id=(SELECT id FROM users WHERE email=?)", MEMBER[1])) == 1


def test_signing_out_and_admin_resets_end_sessions(app, client, member_client):
    member = query(app, "SELECT id FROM users WHERE email=?", MEMBER[1])[0][0]
    client.post(f"/team/{member}/password", data={"csrf": client.csrf, "password": "temporary password one"})
    assert member_client.get("/").status_code == 302
    assert not query(app, "SELECT 1 FROM user_sessions WHERE user_id=?", member)
    client.post("/logout", data={"csrf": client.csrf})
    assert not query(app, "SELECT 1 FROM user_sessions WHERE user_id=(SELECT id FROM users WHERE email=?)", ADMIN[1])


def test_unused_sessions_expire_and_old_cookies_carry_on(app, member_client):
    with member_client.session_transaction() as s:
        s.pop("sid")  # a sign-in from before sessions were recorded
    assert member_client.get("/").status_code == 200
    assert len(query(app, "SELECT 1 FROM user_sessions WHERE user_id=(SELECT id FROM users WHERE email=?)", MEMBER[1])) == 2
    sql(app, "UPDATE user_sessions SET last_seen_at='2026-01-01T00:00:00+00:00'")
    assert member_client.get("/").status_code == 302


def test_new_device_sign_ins_are_emailed(app, client, outbox):
    # The admin's first sign-in (the client fixture) recorded that browser without an alert.
    assert not outbox
    login(app, ADMIN[1], ADMIN[2])  # a new browser
    (alert,) = outbox
    assert alert["to"] == [ADMIN[1]] and alert["subject"] == "New sign-in to your CAE CRM account"
    client.post("/logout", data={"csrf": client.csrf})
    client.get("/login")
    refresh_csrf(client)
    client.post("/login", data={"csrf": client.csrf, "email": ADMIN[1], "password": ADMIN[2]})
    assert len(outbox) == 1  # the same browser again


# --- Sign-in limits and breached passwords ----------------------------------------------------------------------------

def test_failed_sign_ins_from_one_network_are_paused(app, anon):
    for _ in range(20):
        anon.post("/login", data={"csrf": anon.csrf, "email": MEMBER[1], "password": "wrong guess"},
                  headers={"X-Real-IP": "203.0.113.9"})
        sql(app, "UPDATE users SET failed_logins=0, locked_until=NULL")  # isolate the network limit from the account lock
    paused = anon.post("/login", data={"csrf": anon.csrf, "email": MEMBER[1], "password": MEMBER[2]},
                       headers={"X-Real-IP": "203.0.113.9"})
    assert paused.status_code == 429 and "Too many sign-in attempts" in paused.get_data(as_text=True)
    other = anon.post("/login", data={"csrf": anon.csrf, "email": MEMBER[1], "password": MEMBER[2]},
                      headers={"X-Real-IP": "198.51.100.7"})
    assert other.status_code == 302


def breach_list(*passwords):
    """A stand-in for Have I Been Pwned's range API that knows these passwords."""
    hashes = {hashlib.sha1(p.encode()).hexdigest().upper(): 1234 for p in passwords}
    asked = []

    def lookup(prefix):
        asked.append(prefix)
        return "\r\n".join(f"{h[5:]}:{n}" for h, n in hashes.items() if h.startswith(prefix)) + "\r\nABCDEF0123:0"
    lookup.asked = asked
    return lookup


def test_breached_passwords_are_refused(database):
    app = make_app(database)
    lookup = breach_list("password1234")
    app.config.update(BREACH_CHECK=True, BREACH_BACKEND=lookup)
    c = app.test_client()
    c.get("/signup")
    refresh_csrf(c)
    bad = c.post("/signup", data=SIGNUP | {"csrf": c.csrf, "password": "password1234", "confirm": "password1234"})
    assert bad.status_code == 422 and "turned up in data breaches (1,234 times)" in bad.get_data(as_text=True)
    assert lookup.asked == [hashlib.sha1(b"password1234").hexdigest().upper()[:5]]  # only 5 characters leave
    assert c.post("/signup", data=SIGNUP | {"csrf": c.csrf}).status_code == 302


def test_breach_check_allows_the_password_if_the_service_is_down(database):
    app = make_app(database)

    def down(prefix):
        raise urllib.error.URLError("unreachable")
    app.config.update(BREACH_CHECK=True, BREACH_BACKEND=down)
    c = app.test_client()
    c.get("/signup")
    refresh_csrf(c)
    assert c.post("/signup", data=SIGNUP | {"csrf": c.csrf}).status_code == 302


def test_legal_pages_describe_the_new_safeguards(anon):
    cookies = anon.get("/legal/cookies").get_data(as_text=True)
    assert "cae_device" in cookies
    privacy = anon.get("/legal/privacy").get_data(as_text=True)
    assert "Have I Been Pwned" in privacy and "browser and device" in privacy
