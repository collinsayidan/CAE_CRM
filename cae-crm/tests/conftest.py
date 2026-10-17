import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402

TODAY = date(2026, 10, 17)


@pytest.fixture
def app(tmp_path):
    return create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.sqlite3"), "TODAY": TODAY,
                       "SECRET_KEY": "test"})


@pytest.fixture
def client(app):
    c = app.test_client()
    c.get("/")  # establishes the CSRF token in the session
    with c.session_transaction() as s:
        c.csrf = s["csrf"]
    return c
