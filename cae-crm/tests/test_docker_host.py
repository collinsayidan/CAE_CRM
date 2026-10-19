import json

import pytest

import cron
from conftest import make_app


def test_health_check_needs_no_sign_in(anon):
    resp = anon.get("/healthz")
    assert resp.status_code == 200 and resp.get_data(as_text=True) == "ok"


def test_behind_coolifys_proxy_links_use_the_public_address(monkeypatch, database):
    monkeypatch.setenv("CAE_HOSTED", "1")
    monkeypatch.setenv("CAE_SECRET_KEY", "test-secret")
    monkeypatch.setenv("DATABASE_URL", database)
    app = make_app(database)
    assert app.config["SESSION_COOKIE_SECURE"] is True
    page = app.test_client().get("/welcome", headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "cae.example.co.uk"})
    assert '<link rel="canonical" href="https://cae.example.co.uk/welcome">' in page.get_data(as_text=True)


def test_hosted_without_settings_refuses_to_run(monkeypatch, tmp_path):
    from app import create_app
    monkeypatch.setenv("CAE_HOSTED", "1")
    app = create_app({"TESTING": True})
    assert set(app.config["MISSING_SETTINGS"]) == {"CAE_SECRET_KEY", "DATABASE_URL"}
    assert app.test_client().get("/welcome").status_code == 503


def test_cron_runner(monkeypatch, database, capsys):
    app = make_app(database)
    monkeypatch.setattr(cron, "create_app", lambda: app)
    monkeypatch.delenv("CAE_BASE_URL", raising=False)
    assert cron.main() == 1 and "CAE_BASE_URL" in capsys.readouterr().err
    monkeypatch.setenv("CAE_BASE_URL", "https://cae.example.co.uk")
    app.config["CRON_SECRET"] = ""
    assert cron.main() == 1 and "CRON_SECRET" in capsys.readouterr().err
    app.config["CRON_SECRET"] = "cron-test"
    assert cron.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert {"synced", "reminders", "webhooks"} <= out.keys()
