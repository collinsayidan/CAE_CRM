import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auth  # noqa: E402
from app import create_app  # noqa: E402
from db import get_db  # noqa: E402
from seed import seed_workspace  # noqa: E402

TODAY = date(2026, 10, 16)  # a Friday; the clock is pinned to 11:00
ADMIN = ("Test Admin", "admin@example.co.uk", "correct horse battery")
MEMBER = ("Test Member", "member@example.co.uk", "staple paper clips")
RIVAL = ("Rival Admin", "rival@example.co.uk", "another long password")
# Set CAE_TEST_POSTGRES_URL to also run every test against PostgreSQL.
BACKENDS = ["sqlite"] + (["postgres"] if os.environ.get("CAE_TEST_POSTGRES_URL") else [])


@pytest.fixture(autouse=True)
def no_hosting_env(monkeypatch):
    for name in ("VERCEL", "DATABASE_URL", "POSTGRES_URL", "CAE_DATABASE", "CAE_SETUP_CODE"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(params=BACKENDS)
def database(request, tmp_path):
    if request.param == "sqlite":
        return str(tmp_path / "test.sqlite3")
    import psycopg
    url = os.environ["CAE_TEST_POSTGRES_URL"]
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
    return url


def make_app(database):
    # Two-factor sign-in for admins has its own tests; elsewhere admins sign in with just a password.
    return create_app({"TESTING": True, "DATABASE": database, "TODAY": TODAY, "SECRET_KEY": "test",
                       "MISSING_SETTINGS": [], "ADMIN_2FA_REQUIRED": False})


def add_workspace(app, name, admin, sample=True):
    """A business with its first admin, optionally filled with sample data. Returns the workspace id."""
    with app.app_context():
        db = get_db()
        ws_id = auth.create_workspace(db, name, TODAY)
        auth.create_user(db, ws_id, *admin, role="admin")
        if sample:
            seed_workspace(db, ws_id, TODAY, admin[0], 15_670_000)
        db.commit()
        return ws_id


def add_user(app, ws_id, user, role):
    with app.app_context():
        auth.create_user(get_db(), ws_id, *user, role=role)
        get_db().commit()


def query(app, sql, *args):
    with app.app_context():
        return get_db().execute(sql, args).fetchall()


def first_id(app, table, ws_id, where="1=1", *args):
    rows = query(app, f"SELECT id FROM {table} WHERE workspace_id=? AND {where} ORDER BY id LIMIT 1", ws_id, *args)
    assert rows, f"no {table} in workspace {ws_id}"
    return rows[0][0]


def refresh_csrf(c):
    with c.session_transaction() as s:
        c.csrf = s.get("csrf")
    return c


def login(app, email, password):
    c = app.test_client()
    c.get("/login")
    refresh_csrf(c)
    resp = c.post("/login", data={"csrf": c.csrf, "email": email, "password": password})
    assert resp.status_code == 302, resp.get_data(as_text=True)
    c.get("/")  # signing in starts a fresh session, so fetch its new CSRF token
    return refresh_csrf(c)


@pytest.fixture
def app(database):
    app = make_app(database)
    app.ws = add_workspace(app, "Thistle Ltd", ADMIN)
    add_user(app, app.ws, MEMBER, "member")
    return app


@pytest.fixture
def client(app):
    return login(app, ADMIN[1], ADMIN[2])


@pytest.fixture
def member_client(app):
    return login(app, MEMBER[1], MEMBER[2])


@pytest.fixture
def rival(app):
    """Someone signed in to a different business on the same CAE CRM."""
    app.rival_ws = add_workspace(app, "Rival Ltd", RIVAL)
    return login(app, RIVAL[1], RIVAL[2])


@pytest.fixture
def anon(app):
    c = app.test_client()
    c.get("/login")
    return refresh_csrf(c)
