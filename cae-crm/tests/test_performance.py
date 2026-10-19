import pytest

import db as dbmod
from conftest import make_app, query


@pytest.fixture
def statements(monkeypatch):
    """Counts SQL statements run through the Database wrapper."""
    seen = []
    original = dbmod.Database.execute

    def counting(self, sql, params=()):
        seen.append(sql)
        return original(self, sql, params)

    monkeypatch.setattr(dbmod.Database, "execute", counting)
    return seen


def test_start_up_skips_the_schema_check_when_nothing_has_changed(database, statements):
    make_app(database)
    first = len(statements)
    assert first > 20  # a new database is set up in full
    statements.clear()
    app = make_app(database)
    assert len(statements) == 1  # just reads the fingerprint
    # A different version of the code (a changed schema) runs the full check again.
    with app.app_context():
        dbmod.get_db().execute("UPDATE schema_state SET fingerprint='older'")
        dbmod.get_db().commit()
    statements.clear()
    make_app(database)
    assert len(statements) > 20
    assert query(app, "SELECT fingerprint FROM schema_state")[0][0] == dbmod.SCHEMA_FINGERPRINT


def test_sidebar_badges_come_from_one_query(client, statements):
    client.get("/contacts")
    badge_queries = [s for s in statements if "COUNT(*) FROM deals" in s or "COUNT(*) FROM tickets" in s]
    assert len(badge_queries) == 1


def test_postgres_connection_is_kept_and_recovers_when_dropped(app, client):
    if not dbmod.is_postgres(app.config["DATABASE"]):
        pytest.skip("only PostgreSQL connections are kept between requests")
    with app.app_context():
        first = dbmod.get_db().conn
    with app.app_context():
        assert dbmod.get_db().conn is first  # the same connection, not a new one
        first.close()  # as if the pooler closed it while idle
    assert client.get("/contacts").status_code == 200
    with app.app_context():
        assert not dbmod.get_db().conn.closed
