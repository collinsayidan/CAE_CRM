"""Fixes from the November 2026 site audit: redirects stay on this site, and every response carries security headers."""
import pytest

from conftest import ADMIN, query
from core import is_local_path

OFFSITE = ["//evil.example", "/\\evil.example", "/\\/evil.example", "/\t/evil.example", "/x\\..\\evil", "https://evil.example"]


@pytest.mark.parametrize("target", OFFSITE + ["", None, "deals"])
def test_offsite_and_odd_targets_are_not_local(target):
    assert not is_local_path(target)


@pytest.mark.parametrize("target", ["/", "/deals/4", "/contacts?q=morag&page=2", "/knowledge-base/3#top"])
def test_paths_on_this_site_are_local(target):
    assert is_local_path(target)


@pytest.mark.parametrize("target", OFFSITE)
def test_login_never_sends_people_offsite(app, anon, target):
    resp = anon.post("/login", data={"csrf": anon.csrf, "email": ADMIN[1], "password": ADMIN[2], "next": target})
    assert resp.headers["Location"] == "/"


@pytest.mark.parametrize("target", ["//evil.example", "/\\evil.example"])
def test_form_next_values_stay_on_this_site(client, target):
    resp = client.post("/notifications/read", data={"csrf": client.csrf, "next": target})
    assert resp.headers["Location"] == "/notifications"
    assert client.post("/notifications/read", data={"csrf": client.csrf, "next": "/deals"}).headers["Location"] == "/deals"


def test_pages_get_security_headers(client, anon):
    for c, path in ((anon, "/login"), (client, "/"), (client, "/contacts")):
        h = c.get(path).headers
        assert h["X-Content-Type-Options"] == "nosniff", path
        assert h["Referrer-Policy"] == "strict-origin-when-cross-origin", path
        assert "camera=()" in h["Permissions-Policy"], path
        assert h["X-Frame-Options"] == "SAMEORIGIN", path
        assert h["Content-Security-Policy"] == "frame-ancestors 'self'", path
    assert "Strict-Transport-Security" not in anon.get("/login").headers  # only when hosted on HTTPS


def test_hsts_when_hosted(app, anon):
    app.config["SESSION_COOKIE_SECURE"] = True
    assert anon.get("/login").headers["Strict-Transport-Security"].startswith("max-age=31536000")


def test_web_forms_can_still_be_embedded_on_other_sites(app, client):
    client.post("/forms", data={"csrf": client.csrf, "name": "Website enquiries"})
    token = query(app, "SELECT token FROM web_forms WHERE workspace_id=?", app.ws)[0][0]
    h = app.test_client().get(f"/f/{token}?embed=1").headers
    assert "X-Frame-Options" not in h and "frame-ancestors" not in h.get("Content-Security-Policy", "")
    assert h["X-Content-Type-Options"] == "nosniff"


def test_downloads_work_for_any_filename():
    from files import disposition
    for name in ("合同.pdf", "café 🎉.pdf", 'a"b' + chr(92) + 'c.pdf'):
        header = disposition(name)
        header.encode("ascii")  # gunicorn sends headers as Latin-1; plain ASCII is always safe
        assert header.startswith('attachment; filename="') and "filename*=UTF-8''" in header
    assert disposition("Quote Q-0001.pdf") == "attachment; filename=\"Quote Q-0001.pdf\"; filename*=UTF-8''Quote%20Q-0001.pdf"
