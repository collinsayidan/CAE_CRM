import pytest

import approve
import mail
from conftest import ADMIN, query, refresh_csrf
from db import get_db
from test_helpers import FakeClaude

SIGNUP = {"business": "Open Door Ltd", "name": "Sam Open", "email": "sam@opendoor.example", "password": "a long enough password",
          "confirm": "a long enough password"}


def sign_up(app, code=None):
    c = app.test_client()
    c.get("/signup")
    refresh_csrf(c)
    data = SIGNUP | {"csrf": c.csrf} | ({"setup_code": code} if code else {})
    assert c.post("/signup", data=data).status_code == 302
    c.get("/")
    return refresh_csrf(c)


def new_ws(app):
    return query(app, "SELECT id FROM workspaces WHERE name='Open Door Ltd'")[0][0]


@pytest.fixture
def ai(app):
    app.config["AI_BACKEND"] = FakeClaude()
    app.config["MAIL_BACKEND"] = "memory"


def test_existing_and_invited_workspaces_are_approved(app):
    assert query(app, "SELECT approved FROM workspaces WHERE id=?", app.ws)[0][0] == 1
    app.config["SIGNUP_CODE"] = "letmein"
    sign_up(app, code="letmein")
    assert query(app, "SELECT approved FROM workspaces WHERE id=?", new_ws(app))[0][0] == 1


def test_open_sign_ups_wait_for_approval_and_the_owner_is_told(app, ai):
    app.config["SIGNUP_ALERT"] = "owner@collinalitics.example"
    c = sign_up(app)
    ws_id = new_ws(app)
    assert query(app, "SELECT approved FROM workspaces WHERE id=?", ws_id)[0][0] == 0
    alert = [m for m in app.extensions["outbox"] if m["to"] == ["owner@collinalitics.example"]]
    assert alert and "Open Door Ltd" in alert[0]["subject"] and f"approve.py approve {ws_id}" in alert[0]["text"]
    # AI can't be switched on yet, and website chat neither.
    page = c.get("/settings/assistant").get_data(as_text=True)
    assert "Waiting for approval" in page
    c.post("/settings/assistant", data={"csrf": c.csrf, "enabled": "on"})
    assert query(app, "SELECT ai_enabled FROM workspaces WHERE id=?", ws_id)[0][0] == 0
    c.post("/settings/chat", data={"csrf": c.csrf, "enabled": "on"})
    assert query(app, "SELECT chat_on FROM workspaces WHERE id=?", ws_id)[0][0] == 0
    # Approving opens it up.
    with app.app_context():
        assert approve.set_approved(get_db(), ws_id, True) == 0
    c.post("/settings/assistant", data={"csrf": c.csrf, "enabled": "on"})
    assert query(app, "SELECT ai_enabled FROM workspaces WHERE id=?", ws_id)[0][0] == 1


def test_unapproved_workspaces_have_a_daily_email_allowance(app, ai):
    app.config["UNAPPROVED_DAILY_EMAILS"] = 3
    sign_up(app)
    ws_id = new_ws(app)
    with app.test_request_context():
        from flask import g
        msg = mail.message("someone@example.co.uk", "Hi", "<p>x</p>", "x", "Open Door")
        g.public_workspace = ws_id
        for _ in range(3):
            mail.send(msg)
        with pytest.raises(mail.MailError, match="3 emails a day"):
            mail.send(msg)
        with pytest.raises(mail.MailError):
            mail.send_batch([msg, msg])
        g.public_workspace = app.ws  # an approved workspace isn't limited
        for _ in range(5):
            mail.send(msg)
    assert query(app, "SELECT sent FROM mail_usage WHERE workspace_id=?", ws_id)[0][0] == 3


def test_the_approve_command(app, capsys):
    sign_up(app)
    ws_id = new_ws(app)
    assert approve.main([], app) == 0
    out = capsys.readouterr().out
    assert "WAITING" in out and "Open Door Ltd" in out and "sam@opendoor.example" in out and "Thistle Ltd" not in out
    assert approve.main(["approve", str(ws_id)], app) == 0
    assert query(app, "SELECT approved FROM workspaces WHERE id=?", ws_id)[0][0] == 1
    assert approve.main(["approve", "99999"], app) == 1
    assert approve.main(["nonsense"], app) == 2
