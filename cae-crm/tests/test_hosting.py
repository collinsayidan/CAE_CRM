from app import create_app


def test_previews_never_use_the_live_database(monkeypatch, tmp_path):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "preview")
    monkeypatch.setenv("CAE_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("DATABASE_URL", "postgresql://live.example/postgres")
    app = create_app()
    assert app.config["DATABASE"] is None and app.config["MISSING_SETTINGS"] == ["PREVIEW_DATABASE_URL"]
    page = app.test_client().get("/login")
    assert page.status_code == 503 and "PREVIEW_DATABASE_URL" in page.get_data(as_text=True)

    preview_db = str(tmp_path / "preview.sqlite3")
    monkeypatch.setenv("PREVIEW_DATABASE_URL", preview_db)
    assert create_app().config["DATABASE"] == preview_db


def test_production_uses_database_url(monkeypatch, tmp_path):
    live = str(tmp_path / "live.sqlite3")
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv("CAE_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("DATABASE_URL", live)
    monkeypatch.setenv("PREVIEW_DATABASE_URL", str(tmp_path / "other.sqlite3"))
    assert create_app().config["DATABASE"] == live
