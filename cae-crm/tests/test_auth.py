from conftest import ADMIN, MEMBER, login, make_app, refresh_csrf


def test_pages_need_sign_in(anon):
    resp = anon.get("/pipeline")
    assert resp.status_code == 302 and "/login?next=/pipeline" in resp.headers["Location"]
    assert anon.get("/api/search?q=mersey").status_code == 401
    assert anon.get("/static/style.css").status_code == 200


def test_first_run_setup_creates_admin_then_closes(database):
    app = make_app(database)
    c = app.test_client()
    assert c.get("/").headers["Location"].endswith("/setup")
    c.get("/setup")
    refresh_csrf(c)
    bad = c.post("/setup", data={"csrf": c.csrf, "name": "Ada", "email": "ada@example.co.uk",
                                 "password": "short", "confirm": "short"})
    assert bad.status_code == 422 and "at least 10 characters" in bad.get_data(as_text=True)
    ok = c.post("/setup", data={"csrf": c.csrf, "name": "Ada Lovelace", "email": "Ada@Example.co.uk",
                                "password": "analytical engine", "confirm": "analytical engine"})
    assert ok.status_code == 302
    assert "Ada Lovelace" in c.get("/").get_data(as_text=True)
    assert app.test_client().get("/setup").headers["Location"].endswith("/login")


def test_hosted_setup_needs_setup_code(database, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("CAE_SETUP_CODE", "let-me-in")
    app = make_app(database)
    c = app.test_client()
    c.get("/setup")
    refresh_csrf(c)
    form = {"csrf": c.csrf, "name": "Ada", "email": "ada@example.co.uk",
            "password": "analytical engine", "confirm": "analytical engine"}
    assert c.post("/setup", data=form | {"setup_code": "guess"}).status_code == 422
    assert c.post("/setup", data=form | {"setup_code": "let-me-in"}).status_code == 302


def test_hosted_without_settings_shows_what_is_missing(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    from app import create_app
    resp = create_app({"TESTING": True}).test_client().get("/")
    html = resp.get_data(as_text=True)
    assert resp.status_code == 503 and "DATABASE_URL" in html and "CAE_SECRET_KEY" in html


def test_wrong_password_then_lockout(app, anon):
    form = {"csrf": anon.csrf, "email": ADMIN[1], "password": "not the password"}
    resp = anon.post("/login", data=form)
    assert resp.status_code == 401 and "match an account" in resp.get_data(as_text=True)
    for _ in range(4):
        anon.post("/login", data=form)
    locked = anon.post("/login", data=form | {"password": ADMIN[2]})
    assert locked.status_code == 401 and "Too many failed attempts" in locked.get_data(as_text=True)


def test_unknown_email_gets_same_message(anon):
    resp = anon.post("/login", data={"csrf": anon.csrf, "email": "nobody@example.co.uk", "password": "whatever123"})
    assert resp.status_code == 401 and "match an account" in resp.get_data(as_text=True)


def test_login_redirects_to_next_but_not_offsite(app, anon):
    resp = anon.post("/login", data={"csrf": anon.csrf, "email": ADMIN[1], "password": ADMIN[2], "next": "//evil.example"})
    assert resp.headers["Location"] == "/"


def test_members_cannot_manage_team_or_erase(member_client):
    assert member_client.get("/team").status_code == 403
    assert member_client.post("/contacts/1/erase", data={"csrf": member_client.csrf}).status_code == 403
    assert "Erase" not in member_client.get("/customers/1").get_data(as_text=True)


def test_admin_adds_member_who_can_sign_in(app, client):
    resp = client.post("/team", data={"csrf": client.csrf, "name": "New Starter", "email": "new@example.co.uk",
                                      "password": "fresh temporary pass", "role": "member"})
    assert resp.status_code == 302
    dup = client.post("/team", data={"csrf": client.csrf, "name": "Again", "email": "new@example.co.uk",
                                     "password": "fresh temporary pass", "role": "member"})
    assert dup.status_code == 422
    newbie = login(app, "new@example.co.uk", "fresh temporary pass")
    assert "New Starter" in newbie.get("/").get_data(as_text=True)


def test_change_password_and_sign_out(app, member_client):
    bad = member_client.post("/account", data={"csrf": member_client.csrf, "current": "wrong",
                                               "password": "a brand new password", "confirm": "a brand new password"})
    assert bad.status_code == 422
    ok = member_client.post("/account", data={"csrf": member_client.csrf, "current": MEMBER[2],
                                              "password": "a brand new password", "confirm": "a brand new password"})
    assert ok.status_code == 302
    member_client.post("/logout", data={"csrf": member_client.csrf})
    assert member_client.get("/").status_code == 302
    login(app, MEMBER[1], "a brand new password")


def test_new_deal_defaults_to_signed_in_owner(app, client):
    client.post("/deals", data={"csrf": client.csrf, "title": "Owned deal", "company_id": "1", "value": "1000",
                                "close_date": "2026-12-01", "owner": "Someone Invented"})
    with app.app_context():
        from db import get_db
        assert get_db().execute("SELECT owner FROM deals WHERE title='Owned deal'").fetchone()[0] == ADMIN[0]


def test_empty_production_database_renders(database):
    app = make_app(database, demo=False)
    from conftest import add_user
    add_user(app, ADMIN, "admin")
    c = login(app, ADMIN[1], ADMIN[2])
    for path in ["/", "/pipeline", "/customers", "/schedule", "/finance", "/growth", "/projects", "/team", "/account"]:
        assert c.get(path).status_code == 200, path
    assert "Add a customer first" in c.get("/").get_data(as_text=True)
