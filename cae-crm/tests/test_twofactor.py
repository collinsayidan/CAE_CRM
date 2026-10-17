import re
import time

import pytest

from conftest import ADMIN, MEMBER, query, refresh_csrf
from twofactor import code_at, matching_step


def test_codes_match_the_standard():
    # RFC 6238 test vector: secret "12345678901234567890", time 59s -> 94287082 (last six digits for six-digit codes).
    assert code_at("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", 59 // 30) == "287082"
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    step = matching_step(secret, code_at(secret, int(time.time() // 30)))
    assert step is not None
    assert matching_step(secret, code_at(secret, step), last_step=step) is None  # a code works once


@pytest.fixture
def required(app):
    app.config["ADMIN_2FA_REQUIRED"] = True
    return app


def password_step(app, email, password):
    c = app.test_client()
    c.get("/login")
    refresh_csrf(c)
    resp = c.post("/login", data={"csrf": c.csrf, "email": email, "password": password})
    if resp.headers.get("Location", "").endswith("/login/two-factor"):
        c.get("/login/two-factor")  # as the browser would, which gives the new session its form token
    return c, resp


def turn_on(app, client):
    page = client.get("/account/two-factor").get_data(as_text=True)
    secret = re.search(r'<code class="secret">([A-Z2-7]+)</code>', page).group(1)
    refresh_csrf(client)
    done = client.post("/account/two-factor", data={"csrf": client.csrf, "code": code_at(secret, int(time.time() // 30))})
    codes = re.findall(r"<li><code>([0-9a-f]{4}-[0-9a-f]{4})</code></li>", done.get_data(as_text=True))
    assert done.status_code == 200 and len(codes) == 10
    return secret, codes


def test_admins_must_set_it_up_and_members_needn_t(required, client, member_client):
    resp = client.get("/contacts")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/account/two-factor")
    assert member_client.get("/contacts").status_code == 200
    turn_on(required, client)
    assert client.get("/contacts").status_code == 200


def test_signing_in_needs_the_code(required, client):
    secret, codes = turn_on(required, client)
    c, resp = password_step(required, ADMIN[1], ADMIN[2])
    assert resp.headers["Location"].endswith("/login/two-factor")
    assert c.get("/contacts").status_code == 302  # not signed in yet
    refresh_csrf(c)
    assert c.post("/login/two-factor", data={"csrf": c.csrf, "code": "000000"}).status_code == 401
    future = code_at(secret, int(time.time() // 30) + 1)  # the setup code's step is used; take the next one
    assert c.post("/login/two-factor", data={"csrf": c.csrf, "code": future}).status_code == 302
    assert c.get("/contacts").status_code == 200
    actions = [r[0] for r in query(required, "SELECT action FROM audit_events WHERE workspace_id=?", required.ws)]
    assert "Turned on two-factor sign-in" in actions and "Signed in with two-factor" in actions


def test_recovery_codes_work_once(required, client):
    _, codes = turn_on(required, client)
    first, _ = password_step(required, ADMIN[1], ADMIN[2])
    refresh_csrf(first)
    first.post("/login/two-factor", data={"csrf": first.csrf, "code": codes[0]})
    assert first.get("/contacts").status_code == 200
    again, _ = password_step(required, ADMIN[1], ADMIN[2])
    refresh_csrf(again)
    again.post("/login/two-factor", data={"csrf": again.csrf, "code": codes[0]})
    assert again.get("/contacts").status_code == 302  # used up


def test_too_many_wrong_codes_start_again(required, client):
    turn_on(required, client)
    c, _ = password_step(required, ADMIN[1], ADMIN[2])
    refresh_csrf(c)
    for _ in range(5):
        resp = c.post("/login/two-factor", data={"csrf": c.csrf, "code": "111111"})
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/login")
    assert c.get("/login/two-factor").headers["Location"].endswith("/login")


def test_admin_resets_a_member_and_admins_cannot_turn_it_off(required, client, member_client):
    turn_on(required, member_client)
    member = query(required, "SELECT id FROM users WHERE email=?", MEMBER[1])[0][0]
    turn_on(required, client)
    refresh_csrf(client)
    client.post(f"/team/{member}/two-factor/reset", data={"csrf": client.csrf})
    assert query(required, "SELECT totp_enabled_at FROM users WHERE id=?", member)[0][0] is None
    client.post("/account/two-factor/off", data={"csrf": client.csrf})
    assert query(required, "SELECT totp_enabled_at FROM users WHERE email=?", ADMIN[1])[0][0] is not None
