"""The screen lock: after a spell with nothing done, the password again, but not the authenticator code."""

import time

from conftest import ADMIN, query


def go_idle(c, minutes):
    with c.session_transaction() as s:
        s["last_active"] = time.time() - minutes * 60


def test_a_session_left_alone_locks_and_the_password_unlocks_it(client):
    assert client.get("/contacts").status_code == 200
    go_idle(client, 31)
    resp = client.get("/contacts?q=ada")
    assert resp.status_code == 302 and resp.headers["Location"].startswith("/unlock?next=/contacts")
    page = client.get("/unlock").get_data(as_text=True)
    assert "Screen locked" in page and ADMIN[1] in page
    assert "authenticator" not in page.lower()
    # Everything stays shut until the password is entered, saves from the page included.
    assert client.get("/").status_code == 302
    assert client.get("/legal/privacy").status_code == 200  # public pages still open
    blocked = client.post("/session/active", data={"csrf": client.csrf}, headers={"X-Requested-With": "fetch"})
    assert blocked.status_code == 401 and blocked.get_json()["locked"] is True
    resp = client.post("/unlock", data={"csrf": client.csrf, "password": ADMIN[2], "next": "/contacts?q=ada"})
    assert resp.status_code == 302 and resp.headers["Location"] == "/contacts?q=ada"
    assert client.get("/contacts").status_code == 200


def test_activity_keeps_the_screen_unlocked(client):
    go_idle(client, 29)
    assert client.post("/session/active", data={"csrf": client.csrf},
                       headers={"X-Requested-With": "fetch"}).status_code == 204
    with client.session_transaction() as s:
        assert time.time() - s["last_active"] < 5
    assert client.get("/contacts").status_code == 200


def test_the_page_unlocks_in_place_without_reloading(client):
    go_idle(client, 45)
    fetch = {"X-Requested-With": "fetch"}
    assert client.get("/api/search?q=a", headers=fetch).get_json()["locked"] is True
    wrong = client.post("/unlock", data={"csrf": client.csrf, "password": "not it"}, headers=fetch)
    assert wrong.status_code == 401 and "4 tries left" in wrong.get_json()["error"]
    right = client.post("/unlock", data={"csrf": client.csrf, "password": ADMIN[2]}, headers=fetch)
    assert right.status_code == 200 and right.get_json() == {"ok": True}
    assert query(client.application, "SELECT failed_logins FROM users WHERE email=?", ADMIN[1])[0][0] == 0


def test_five_wrong_passwords_sign_out_completely(client):
    go_idle(client, 31)
    for _ in range(4):
        assert client.post("/unlock", data={"csrf": client.csrf, "password": "guess"}).status_code == 401
    resp = client.post("/unlock", data={"csrf": client.csrf, "password": "guess"})
    assert resp.status_code == 302 and resp.headers["Location"] == "/login"
    with client.session_transaction() as s:
        assert "user_id" not in s
    # The account is held for a while, as after failed sign-ins.
    assert query(client.application, "SELECT locked_until FROM users WHERE email=?", ADMIN[1])[0][0]


def test_an_old_copy_of_the_cookie_doesnt_reset_the_count(client):
    go_idle(client, 31)
    with client.session_transaction() as s:
        saved = dict(s)
    for _ in range(3):
        client.post("/unlock", data={"csrf": client.csrf, "password": "guess"})
    with client.session_transaction() as s:
        s.clear()
        s.update(saved)
    client.post("/unlock", data={"csrf": client.csrf, "password": "guess"})
    assert client.post("/unlock", data={"csrf": client.csrf, "password": "guess"}).headers["Location"] == "/login"


def test_admins_choose_the_lock_time(client, member_client):
    page = client.get("/settings").get_data(as_text=True)
    assert 'name="lock_minutes"' in page and '<option value="30" selected' in page
    form = {"csrf": client.csrf, "name": "Thistle Ltd", "monthly_target": "150,000", "quiet_days": "14",
            "invoice_prefix": "INV", "payment_terms": "30", "lock_minutes": "240"}
    assert client.post("/settings", data=form).status_code == 302
    assert query(client.application, "SELECT lock_minutes FROM workspaces WHERE id=?", client.application.ws)[0][0] == 240
    # Only the choices offered are kept.
    client.post("/settings", data=form | {"lock_minutes": "1"})
    assert query(client.application, "SELECT lock_minutes FROM workspaces WHERE id=?", client.application.ws)[0][0] == 240
    # Everyone in the workspace gets it: 3 hours idle is fine, 5 hours locks.
    go_idle(member_client, 180)
    assert member_client.get("/contacts").status_code == 200
    go_idle(member_client, 300)
    assert member_client.get("/contacts").headers["Location"].startswith("/unlock")


def test_the_page_tells_the_browser_when_to_lock(client):
    page = client.get("/").get_data(as_text=True)
    assert 'data-lock-after="1800"' in page and 'data-lock-warn="120"' in page


def test_signing_out_from_the_lock_screen_works(client):
    go_idle(client, 31)
    resp = client.post("/logout", data={"csrf": client.csrf})
    assert resp.status_code == 302 and resp.headers["Location"] == "/login"


def test_the_demo_never_locks(app):
    from test_demo import start
    c, _ = start(app)
    go_idle(c, 600)
    resp = c.get("/contacts")
    assert resp.status_code == 200 and "data-lock-after" not in resp.get_data(as_text=True)


def test_when_the_browser_locks_the_server_locks_too(client):
    fetch = {"X-Requested-With": "fetch"}
    assert client.post("/session/lock", data={"csrf": client.csrf}, headers=fetch).status_code == 204
    assert client.get("/contacts").headers["Location"].startswith("/unlock")
    wrong = client.post("/unlock", data={"csrf": client.csrf, "password": "not it"}, headers=fetch)
    assert wrong.status_code == 401
    assert client.post("/unlock", data={"csrf": client.csrf, "password": ADMIN[2]}, headers=fetch).status_code == 200
    assert client.get("/contacts").status_code == 200


def test_a_request_with_an_older_cookie_cant_undo_the_lock(client):
    with client.session_transaction() as s:
        before = dict(s)
    assert client.post("/session/lock", data={"csrf": client.csrf}, headers={"X-Requested-With": "fetch"}).status_code == 204
    with client.session_transaction() as s:
        s.clear()
        s.update(before)  # as if a request that started before the lock wrote its cookie back afterwards
    assert client.get("/contacts").headers["Location"].startswith("/unlock")
