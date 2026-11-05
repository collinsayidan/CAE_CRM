"""How the site looks to search engines and to browsers' caches.

Search engines: robots.txt and a sitemap list the public pages worth finding. Every other response says
"noindex", so quote, payment, form, reset and other private links never turn up in search results, even when
someone shares one publicly.

Caches: every url_for('static', ...) link carries a short fingerprint of the file (?v=...), so browsers can keep
the file for a year and still fetch a new copy the moment it changes. Fonts, which CSS links without a fingerprint,
are kept for 30 days; they never change in place.
"""
import hashlib
import os

from flask import Response, current_app, request, url_for

# Public pages search engines may list. Business help centres are public on purpose, so they can be found too.
INDEXABLE_ENDPOINTS = {"landing", "legal_index", "legal", "auth.signup", "start_demo", "help_index", "help_article",
                       "robots_txt", "sitemap"}
YEAR, MONTH = 365 * 24 * 3600, 30 * 24 * 3600
_fingerprints = {}


def fingerprint(filename):
    if filename not in _fingerprints:
        try:
            with open(os.path.join(current_app.static_folder, filename), "rb") as f:
                _fingerprints[filename] = hashlib.sha256(f.read()).hexdigest()[:10]
        except OSError:
            _fingerprints[filename] = ""
    return _fingerprints[filename]


def register(app):

    @app.url_defaults
    def static_fingerprint(endpoint, values):
        if endpoint == "static" and values.get("filename") and "v" not in values:
            v = fingerprint(values["filename"])
            if v:
                values["v"] = v

    @app.after_request
    def cache_and_index_headers(resp):
        if request.endpoint == "static" and resp.status_code in (200, 304):
            if request.args.get("v"):
                resp.cache_control.no_cache = None
                resp.cache_control.public = True
                resp.cache_control.max_age = YEAR
                resp.cache_control.immutable = True
            elif request.path.startswith("/static/fonts/"):
                resp.cache_control.no_cache = None
                resp.cache_control.public = True
                resp.cache_control.max_age = MONTH
        elif request.endpoint not in INDEXABLE_ENDPOINTS:
            resp.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
        return resp

    @app.get("/robots.txt")
    def robots_txt():
        body = f"User-agent: *\nAllow: /\n\nSitemap: {url_for('sitemap', _external=True)}\n"
        return Response(body, mimetype="text/plain", headers={"Cache-Control": "public, max-age=86400"})

    @app.get("/sitemap.xml")
    def sitemap():
        from legal import DOCS
        pages = [url_for("landing", _external=True), url_for("auth.signup", _external=True),
                 url_for("start_demo", _external=True), url_for("legal_index", _external=True)]
        pages += [url_for("legal", doc=key, _external=True) for key in DOCS]
        body = ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                + "".join(f"  <url><loc>{p}</loc></url>\n" for p in pages) + "</urlset>\n")
        return Response(body, mimetype="application/xml", headers={"Cache-Control": "public, max-age=86400"})
