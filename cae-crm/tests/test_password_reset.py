import re

import pytest

from conftest import ADMIN, MEMBER, login, query, refresh_csrf


@pytest.fixture
def outbox(app):
    app.config["MAIL_BACKEND"] = "memory"
    app.extensions["outbox"] = []
    return app.extensions["outbox"]


def visitor(app):
    c = app.test_client()
    c.get("/forgot")
    return refresh_csrf(c)


def ask(app, email, ip="198.51.100.20"):
    c = visitor(app)
    return c.post("/forgot", data={"csrf": c.csrf, "email": email}, headers={"X-Real-IP": ip})


def reset_link(outbox):
    return re.search(r'href="(http[^"]+/reset/[^"]+)"', outbox[-1]["html"]).group(1).replace("http://localhost", "")


def test_reset_by_email_works_once_and_unlocks(app, outbox):
    with app.app_context():
        from db import get_db
        get_db().execute("UPDATE users SET failed_logins=4, locked_until='2999-01-01' WHERE email=?", (MEMBER[1],))
        get_db().commit()
    page = ask(app, MEMBER[1]).get_data(as_text=True)
    assert "we've sent it a link" in page and len(outbox) == 1 and outbox[0]["to"] == [MEMBER[1]]
    link = reset_link(outbox)
    c = app.test_client()
    form = c.get(link)
    assert form.status_code == 200 and MEMBER[1] in form.get_data(as_text=True)
    refresh_csrf(c)
    assert c.post(link, data={"csrf": c.csrf, "password": "short", "confirm": "short"}).status_code == 422
    assert c.post(link, data={"csrf": c.csrf, "password": "a fresh new password", "confirm": "a fresh new password"}).status_code == 302
    assert query(app, "SELECT failed_logins, locked_until FROM users WHERE email=?", MEMBER[1])[0][0] == 0
    login(app, MEMBER[1], "a fresh new password")
    assert app.test_client().get(link).status_code == 400  # used: the password it was for has changed


def test_unknown_emails_get_the_same_answer_and_no_email(app, outbox):
    known = ask(app, MEMBER[1]).get_data(as_text=True)
    unknown = ask(app, "nobody@example.co.uk").get_data(as_text=True)
    assert "we've sent it a link" in unknown
    assert len(outbox) == 1
    assert known.replace(MEMBER[1], "X") == unknown.replace("nobody@example.co.uk", "X")


def test_tampered_or_expired_links_are_refused(app, outbox):
    assert app.test_client().get("/reset/not-a-real-token").status_code == 400
    ask(app, MEMBER[1])
    link = reset_link(outbox)
    assert app.test_client().get(link[:-3] + "abc").status_code == 400


def test_reset_requests_are_rate_limited(app, outbox):
    for _ in range(5):
        ask(app, MEMBER[1])
    assert len(outbox) == 3  # three an hour per account
    for n in range(10):
        ask(app, f"person{n}@example.co.uk", ip="203.0.113.50")
    ask(app, ADMIN[1], ip="203.0.113.50")
    assert all(m["to"] != [ADMIN[1]] for m in outbox)  # that address has asked too often


def test_without_email_people_are_told_to_ask_an_admin(app):
    page = visitor(app).get("/forgot").get_data(as_text=True)
    assert "Ask an admin" in page and "Send reset link" not in page


def test_changing_a_password_signs_out_other_sessions(app, member_client):
    laptop = login(app, MEMBER[1], MEMBER[2])
    member_client.post("/account", data={"csrf": member_client.csrf, "current": MEMBER[2],
                                         "password": "another long password", "confirm": "another long password"})
    assert member_client.get("/contacts").status_code == 200  # this device stays signed in
    assert laptop.get("/contacts").status_code == 302  # the other one is signed out


def test_admin_reset_signs_the_member_out(app, client, member_client):
    member = query(app, "SELECT id FROM users WHERE email=?", MEMBER[1])[0][0]
    client.post(f"/team/{member}/password", data={"csrf": client.csrf, "password": "temporary password 1"})
    assert member_client.get("/contacts").status_code == 302


def test_settings_hub_and_tabs(app, client, member_client):
    page = client.get("/workspace").get_data(as_text=True)
    for label in ("Business details", "Team", "Integrations", "Import", "VAT returns"):
        assert label in page
    assert 'class="settings-tabs"' in client.get("/team").get_data(as_text=True)
    member_page = member_client.get("/workspace").get_data(as_text=True)
    assert "Team" in member_page and "Business details" not in member_page and "Import" not in member_page
    nav = client.get("/").get_data(as_text=True)
    assert nav.count('class="nav-heading"') == 3
