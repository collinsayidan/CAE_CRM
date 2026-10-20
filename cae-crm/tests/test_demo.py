from datetime import datetime, timedelta, timezone

from flask import g, url_for

import demo
import mail
from conftest import query, refresh_csrf


def start(app, ip="203.0.113.7"):
    c = app.test_client()
    c.get("/login", environ_base={"REMOTE_ADDR": ip})
    refresh_csrf(c)
    resp = c.post("/demo", data={"csrf": c.csrf}, environ_base={"REMOTE_ADDR": ip})
    c.get("/")
    return refresh_csrf(c), resp


def demo_ids(app):
    return [r[0] for r in query(app, "SELECT id FROM workspaces WHERE demo_until IS NOT NULL ORDER BY id")]


def path(app, endpoint, **kw):
    with app.test_request_context():
        return url_for(endpoint, **kw)


def test_homepage_and_sign_in_offer_the_demo(anon):
    for page in ("/welcome", "/login"):
        html = anon.get(page).get_data(as_text=True)
        assert "Try the demo" in html and 'action="/demo"' in html, page


def test_a_demo_is_a_private_sample_workspace_without_signing_up(app):
    app.config["ADMIN_2FA_REQUIRED"] = True  # a demo's admin isn't asked to set up two-factor sign-in
    c, resp = start(app)
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/")
    page = c.get("/").get_data(as_text=True)
    assert "You're exploring a demo" in page and "Good" in page and "Alex" in page
    (ws_id,) = demo_ids(app)
    assert ws_id != app.ws
    assert query(app, "SELECT COUNT(*) FROM deals WHERE workspace_id=?", ws_id)[0][0] > 0
    until = datetime.fromisoformat(query(app, "SELECT demo_until FROM workspaces WHERE id=?", ws_id)[0][0])
    assert timedelta(hours=23) < until - datetime.now(timezone.utc) <= timedelta(hours=24)
    # It can't see the real business, and the real business can't see it.
    assert "Thistle Ltd" not in c.get("/companies").get_data(as_text=True)
    # Ordinary work is allowed.
    resp = c.post("/contacts", data={"csrf": c.csrf, "first_name": "Ada", "last_name": "Byron", "lawful_basis": "Contract"})
    assert resp.status_code in (200, 302)
    assert query(app, "SELECT COUNT(*) FROM contacts WHERE workspace_id=? AND last_name='Byron'", ws_id)[0][0] == 1


def test_a_demo_cant_email_connect_or_publish(app):
    c, _ = start(app)
    (ws_id,) = demo_ids(app)
    before = query(app, "SELECT name, reply_to FROM workspaces WHERE id=?", ws_id)[0]
    resp = c.post(path(app, "settings"), data={"csrf": c.csrf, "name": "Phish Ltd", "reply_to": "x@evil.example"},
                  headers={"Referer": "http://localhost/settings"})
    assert resp.status_code == 302
    assert "switched off in the demo" in c.get("/settings").get_data(as_text=True)
    assert query(app, "SELECT name, reply_to FROM workspaces WHERE id=?", ws_id)[0] == before
    for endpoint in ("create_api_key", "create_webhook", "create_form", "billing_checkout", "auth.team", "upload_file"):
        assert endpoint in demo.BLOCKED
    resp = c.post(path(app, "create_api_key"), data={"csrf": c.csrf, "name": "k"},
                  headers={"X-Requested-With": "fetch"})
    assert resp.status_code == 403 and "switched off" in resp.get_json()["error"]
    assert query(app, "SELECT COUNT(*) FROM api_keys WHERE workspace_id=?", ws_id)[0][0] == 0


def test_mail_from_a_demo_is_dropped_even_by_the_daily_job(app):
    app.config["MAIL_BACKEND"] = "memory"
    start(app)
    (ws_id,) = demo_ids(app)
    with app.test_request_context():
        g.public_workspace = ws_id
        assert mail.send(mail.message("real@example.co.uk", "Hi", "<p>x</p>", "x", "Demo")) == ""
        g.public_workspace = app.ws
        assert mail.send(mail.message("real@example.co.uk", "Hi", "<p>x</p>", "x", "Real")) != ""
        g.pop("public_workspace")
        assert mail.send(mail.message("demo-1@demo.invalid", "Hi", "<p>x</p>", "x", "Demo")) == ""
    assert len(app.extensions["outbox"]) == 1


def test_each_network_can_start_a_few_demos_an_hour(app):
    for _ in range(demo.PER_NETWORK_PER_HOUR):
        start(app, ip="198.51.100.1")
    assert len(demo_ids(app)) == demo.PER_NETWORK_PER_HOUR
    c, resp = start(app, ip="198.51.100.1")
    assert len(demo_ids(app)) == demo.PER_NETWORK_PER_HOUR
    assert "try again in an hour" in c.get("/login").get_data(as_text=True)
    start(app, ip="198.51.100.2")  # someone else is fine
    assert len(demo_ids(app)) == demo.PER_NETWORK_PER_HOUR + 1
    assert query(app, "SELECT demo_ip FROM workspaces WHERE id=?", demo_ids(app)[0])[0][0] != "198.51.100.1"


def test_expired_demos_are_deleted_with_everything_in_them(app):
    start(app)
    (ws_id,) = demo_ids(app)
    real_deals = query(app, "SELECT COUNT(*) FROM deals WHERE workspace_id=?", app.ws)[0][0]
    with app.app_context():
        from db import get_db
        get_db().execute("UPDATE workspaces SET demo_until='2000-01-01T00:00:00+00:00' WHERE id=?", (ws_id,))
        get_db().commit()
        assert demo.purge() == 1
    assert demo_ids(app) == []
    for table in ("deals", "contacts", "companies", "invoices", "tickets", "users"):
        assert query(app, f"SELECT COUNT(*) FROM {table} WHERE workspace_id=?", ws_id)[0][0] == 0, table
    assert query(app, "SELECT COUNT(*) FROM deals WHERE workspace_id=?", app.ws)[0][0] == real_deals
    with app.app_context():
        assert demo.purge([app.ws]) == 1 and query(app, "SELECT COUNT(*) FROM workspaces WHERE id=?", app.ws)[0][0] == 1


def test_leaving_the_demo_deletes_it_and_goes_to_sign_up(app):
    c, _ = start(app)
    resp = c.post("/demo/leave", data={"csrf": c.csrf})
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/signup")
    assert demo_ids(app) == []
    assert "Create your workspace" in c.get("/signup").get_data(as_text=True)
