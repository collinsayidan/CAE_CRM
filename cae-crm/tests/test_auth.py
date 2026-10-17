from conftest import ADMIN, MEMBER, TODAY, add_workspace, first_id, login, make_app, query, refresh_csrf

SIGNUP = {"business": "Bramble & Oak Ltd", "name": "Ada Lovelace", "email": "Ada@Example.co.uk",
          "password": "analytical engine", "confirm": "analytical engine"}


def signup_client(app):
    c = app.test_client()
    c.get("/signup")
    return refresh_csrf(c)


def test_pages_need_sign_in(anon):
    assert anon.get("/").headers["Location"].endswith("/welcome")
    assert "built for UK businesses" in anon.get("/welcome").get_data(as_text=True)
    resp = anon.get("/pipeline")
    assert resp.status_code == 302 and "/login?next=/pipeline" in resp.headers["Location"]
    assert anon.get("/api/search?q=mersey").status_code == 401
    assert anon.get("/static/style.css").status_code == 200


def test_signup_creates_a_workspace_with_its_first_admin(database):
    app = make_app(database)
    c = signup_client(app)
    bad = c.post("/signup", data=SIGNUP | {"csrf": c.csrf, "password": "short", "confirm": "short"})
    assert bad.status_code == 422 and "at least 10 characters" in bad.get_data(as_text=True)
    ok = c.post("/signup", data=SIGNUP | {"csrf": c.csrf})
    assert ok.status_code == 302
    html = c.get("/").get_data(as_text=True)
    assert "Bramble &amp; Oak Ltd" in html and "Welcome to Bramble" in html
    (user,) = query(app, "SELECT role, email, workspace_id FROM users")
    assert (user["role"], user["email"]) == ("admin", "ada@example.co.uk")
    assert query(app, "SELECT COUNT(*) FROM companies")[0][0] == 0
    # The same email can't open a second account.
    again = signup_client(app).post("/signup", data=SIGNUP | {"csrf": c.csrf, "business": "Another"})
    assert again.status_code in (400, 422)


def test_signup_with_sample_data(database):
    app = make_app(database)
    c = signup_client(app)
    c.post("/signup", data=SIGNUP | {"csrf": c.csrf, "sample_data": "on"})
    ws_id = query(app, "SELECT workspace_id FROM users")[0][0]
    assert query(app, "SELECT COUNT(*) FROM companies WHERE workspace_id=?", ws_id)[0][0] >= 10
    assert query(app, "SELECT COUNT(*) FROM tickets WHERE workspace_id=?", ws_id)[0][0] >= 10
    assert "Won in October" in c.get("/").get_data(as_text=True)


def test_signup_needs_invite_code_when_set(database, monkeypatch):
    monkeypatch.setenv("CAE_SETUP_CODE", "let-me-in")
    app = make_app(database)
    c = signup_client(app)
    assert c.post("/signup", data=SIGNUP | {"csrf": c.csrf, "setup_code": "guess"}).status_code == 422
    assert c.post("/signup", data=SIGNUP | {"csrf": c.csrf, "setup_code": "let-me-in"}).status_code == 302


def test_old_setup_address_goes_to_signup(anon):
    assert anon.get("/setup").headers["Location"].endswith("/signup")


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


def test_members_cannot_administer(app, member_client):
    contact = first_id(app, "contacts", app.ws)
    for path in ("/settings", "/import", "/export/contacts"):
        assert member_client.get(path).status_code == 403, path
    # Everyone can see the team, but only admins can add people.
    assert member_client.get("/team").status_code == 200
    assert member_client.post("/team", data={"csrf": member_client.csrf, "name": "Sneaky", "email": "s@example.co.uk",
                                             "password": "long enough password"}).status_code == 403
    assert member_client.post(f"/contacts/{contact}/erase", data={"csrf": member_client.csrf}).status_code == 403
    assert "Erase" not in member_client.get(f"/contacts/{contact}").get_data(as_text=True)
    # Members still do the everyday work.
    assert member_client.get(f"/contacts/{contact}/export").status_code == 200


def test_admin_adds_member_to_their_workspace(app, client):
    resp = client.post("/team", data={"csrf": client.csrf, "name": "New Starter", "email": "new@example.co.uk",
                                      "password": "fresh temporary pass", "role": "member"})
    assert resp.status_code == 302
    dup = client.post("/team", data={"csrf": client.csrf, "name": "Again", "email": "new@example.co.uk",
                                     "password": "fresh temporary pass", "role": "member"})
    assert dup.status_code == 422
    assert query(app, "SELECT workspace_id FROM users WHERE email='new@example.co.uk'")[0][0] == app.ws
    newbie = login(app, "new@example.co.uk", "fresh temporary pass")
    assert "Thistle Ltd" in newbie.get("/").get_data(as_text=True)


def test_change_password_and_sign_out(app, member_client):
    bad = member_client.post("/account", data={"csrf": member_client.csrf, "current": "wrong",
                                               "password": "a brand new password", "confirm": "a brand new password"})
    assert bad.status_code == 422
    ok = member_client.post("/account", data={"csrf": member_client.csrf, "current": MEMBER[2],
                                              "password": "a brand new password", "confirm": "a brand new password"})
    assert ok.status_code == 302
    member_client.post("/logout", data={"csrf": member_client.csrf})
    assert member_client.get("/contacts").status_code == 302
    login(app, MEMBER[1], "a brand new password")


def test_new_deal_defaults_to_signed_in_owner(app, client):
    company = first_id(app, "companies", app.ws)
    client.post("/deals", data={"csrf": client.csrf, "title": "Owned deal", "company_id": company, "value": "1000",
                                "close_date": "2026-12-01", "owner": "Someone Invented"})
    assert query(app, "SELECT owner FROM deals WHERE title='Owned deal'")[0][0] == ADMIN[0]


def test_empty_workspace_renders_everywhere(database):
    app = make_app(database)
    add_workspace(app, "Empty Ltd", ADMIN, sample=False)
    c = login(app, ADMIN[1], ADMIN[2])
    for path in ["/", "/contacts", "/companies", "/pipeline", "/pipeline?view=list", "/tickets", "/tickets?view=list",
                 "/tasks", "/products", "/invoices", "/projects", "/reports", "/settings", "/team", "/account", "/import"]:
        assert c.get(path).status_code == 200, path
    assert "Welcome to Empty Ltd" in c.get("/").get_data(as_text=True)
    assert TODAY.year == 2026
