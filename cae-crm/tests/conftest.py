import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auth  # noqa: E402
from app import create_app  # noqa: E402
from db import get_db  # noqa: E402

TODAY = date(2026, 10, 17)
ADMIN = ("Test Admin", "admin@example.co.uk", "correct horse battery")
MEMBER = ("Test Member", "member@example.co.uk", "staple paper clips")
# Set CAE_TEST_POSTGRES_URL to also run every test against PostgreSQL.
BACKENDS = ["sqlite"] + (["postgres"] if os.environ.get("CAE_TEST_POSTGRES_URL") else [])


@pytest.fixture(autouse=True)
def no_hosting_env(monkeypatch):
    for name in ("VERCEL", "DATABASE_URL", "POSTGRES_URL", "CAE_DATABASE", "CAE_DEMO_DATA", "CAE_SETUP_CODE"):
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


def make_app(database, demo=True):
    return create_app({"TESTING": True, "DATABASE": database, "DEMO_DATA": demo, "TODAY": TODAY,
                       "SECRET_KEY": "test", "MISSING_SETTINGS": []})


def add_user(app, user, role):
    with app.app_context():
        auth.create_user(get_db(), *user, role=role)


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
    add_user(app, ADMIN, "admin")
    add_user(app, MEMBER, "member")
    return app


@pytest.fixture
def client(app):
    return login(app, ADMIN[1], ADMIN[2])


@pytest.fixture
def member_client(app):
    return login(app, MEMBER[1], MEMBER[2])


@pytest.fixture
def anon(app):
    c = app.test_client()
    c.get("/login")
    return refresh_csrf(c)
