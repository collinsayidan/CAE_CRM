"""Search engines and caches, from the November 2026 site audit."""
import re


def test_robots_and_sitemap_list_the_public_pages(anon):
    robots = anon.get("/robots.txt")
    assert robots.status_code == 200 and robots.mimetype == "text/plain"
    assert "Sitemap: http://localhost/sitemap.xml" in robots.get_data(as_text=True)
    sitemap = anon.get("/sitemap.xml")
    assert sitemap.status_code == 200 and sitemap.mimetype == "application/xml"
    urls = re.findall(r"<loc>([^<]+)</loc>", sitemap.get_data(as_text=True))
    assert "http://localhost/welcome" in urls and "http://localhost/legal/privacy" in urls and len(urls) == 9


def test_only_public_pages_can_be_indexed(app, anon, client):
    for path in ("/welcome", "/signup", "/legal", "/legal/terms", "/robots.txt"):
        assert "X-Robots-Tag" not in anon.get(path).headers, path
    for c, path in ((anon, "/login"), (anon, "/forgot"), (client, "/"), (client, "/contacts")):
        assert c.get(path).headers["X-Robots-Tag"] == "noindex, nofollow", path


def test_static_files_are_fingerprinted_and_cached_for_a_year(anon):
    page = anon.get("/login").get_data(as_text=True)
    href = re.search(r'href="(/static/style\.css\?v=[0-9a-f]{10})"', page).group(1)
    resp = anon.get(href)
    assert resp.status_code == 200
    assert resp.cache_control.max_age == 31536000 and resp.cache_control.immutable and resp.cache_control.public
    assert not resp.cache_control.no_cache
    # Without the fingerprint, browsers still check back every time.
    assert anon.get("/static/style.css").cache_control.max_age is None


def test_fonts_are_cached_for_a_month(anon):
    resp = anon.get("/static/fonts/plus-jakarta-sans-latin-wght-normal.woff2")
    assert resp.status_code == 200 and resp.cache_control.max_age == 30 * 24 * 3600


def test_public_pages_have_descriptions(anon):
    for path in ("/welcome", "/signup", "/demo", "/legal", "/legal/privacy"):
        assert '<meta name="description" content="' in anon.get(path).get_data(as_text=True), path
