import base64
import os
from urllib.parse import urlsplit, urlunsplit

import pytest

import move_database
from conftest import ADMIN, first_id, login, make_app, query


@pytest.fixture
def target(tmp_path):
    """An empty database to move into: PostgreSQL when the tests have one (a second database on the same server),
    otherwise SQLite."""
    url = os.environ.get("CAE_TEST_POSTGRES_URL")
    if not url:
        return str(tmp_path / "target.sqlite3")
    import psycopg
    with psycopg.connect(url, autocommit=True) as conn:
        # FORCE: the app keeps PostgreSQL connections open between requests, including from the previous test.
        conn.execute("DROP DATABASE IF EXISTS cae_move_target WITH (FORCE)")
        conn.execute("CREATE DATABASE cae_move_target")
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path="/cae_move_target"))


def add_stored_file(app, data=b"%PDF-1.4 kept in the bucket"):
    """An attachment as Supabase Storage keeps it: a key and no content in the row."""
    contact = first_id(app, "contacts", app.ws)
    with app.app_context():
        from db import get_db
        db = get_db()
        db.insert("attachments", workspace_id=app.ws, record_type="contact", record_id=contact, filename="contract.pdf",
                  content_type="application/pdf", size=len(data), storage_key=f"{app.ws}/contact/{contact}/abc-contract.pdf",
                  content=None, uploaded_by=ADMIN[0], created_at="2026-10-16T10:00")
        db.commit()
    return data


def test_everything_moves_and_the_app_runs_on_the_new_database(app, target):
    data = add_stored_file(app)
    asked = []

    def fake_fetch(storage, path):
        asked.append((storage["bucket"], path))
        return data

    copied = move_database.move(app.config["DATABASE"], target, storage={"url": "https://x.supabase.co", "key": "k",
                                                                           "bucket": "attachments"}, fetch=fake_fetch,
                                log=lambda *_: None)
    assert copied["contacts"] > 0 and copied["deals"] > 0 and copied["attachments"] == 1
    assert asked == [("attachments", query(app, "SELECT storage_key FROM attachments")[0][0])]
    assert move_database.check(app.config["DATABASE"], target)
    # The app works on the moved data: sign in, see the file, and add new records without clashing ids.
    moved = make_app(target)
    moved.ws = app.ws
    c = login(moved, ADMIN[1], ADMIN[2])
    file_id = query(moved, "SELECT id FROM attachments")[0][0]
    assert c.get(f"/files/{file_id}").data == data
    before = query(moved, "SELECT MAX(id) FROM contacts")[0][0]
    c.post("/contacts", data={"csrf": c.csrf, "first_name": "Ada", "last_name": "Byron", "lawful_basis": "Contract"})
    assert query(moved, "SELECT MAX(id) FROM contacts")[0][0] == before + 1


def test_refuses_unsafe_moves(app, target):
    with pytest.raises(SystemExit, match="TARGET_DATABASE_URL"):
        move_database.move(app.config["DATABASE"], "")
    with pytest.raises(SystemExit, match="same database"):
        move_database.move(app.config["DATABASE"], app.config["DATABASE"])
    add_stored_file(app)
    with pytest.raises(SystemExit, match="Supabase Storage"):
        move_database.move(app.config["DATABASE"], target, storage=None, log=lambda *_: None)
    # A second run into a database that now has data is refused, so nothing is copied twice.
    fresh = make_app(target)
    with fresh.app_context():
        from db import get_db
        get_db().insert("workspaces", name="Already here", created_at="2026-10-16")
        get_db().commit()
    with pytest.raises(SystemExit, match="already has data"):
        move_database.move(app.config["DATABASE"], target, log=lambda *_: None)


def test_check_reports_differences(app, target, capsys):
    make_app(target)  # an empty copy of the tables
    assert move_database.check(app.config["DATABASE"], target) is False
    assert "DIFF" in capsys.readouterr().out


def test_files_already_in_the_database_need_no_storage(app, target):
    contact = first_id(app, "contacts", app.ws)
    with app.app_context():
        from db import get_db
        get_db().insert("attachments", workspace_id=app.ws, record_type="contact", record_id=contact, filename="a.txt",
                        content_type="text/plain", size=2, storage_key="k", content=base64.b64encode(b"hi").decode(),
                        uploaded_by=ADMIN[0], created_at="2026-10-16T10:00")
        get_db().commit()
    move_database.move(app.config["DATABASE"], target, storage=None, log=lambda *_: None)
    assert query(make_app(target), "SELECT content FROM attachments")[0][0] == base64.b64encode(b"hi").decode()
