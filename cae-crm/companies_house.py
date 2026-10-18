"""Companies House lookups: suggest companies from the register while someone types a company's name, fill in its
number and registered office, and record its status and industry (SIC) codes, warning when a customer has been
dissolved or is in liquidation, administration or another insolvency process.

It appears once COMPANIES_HOUSE_API_KEY is set (a free key from developer.company-information.service.gov.uk). Calls
go from the server, so pages still load nothing from other websites. The daily job re-checks up to 100 companies.
Tests set CH_BACKEND to a fake with the same request(path, params) signature."""

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from flask import abort, current_app, flash, jsonify, redirect, request, url_for

from core import get_or_404, log_event, now, rows, ws
from db import get_db

API = "https://api.company-information.service.gov.uk"
# Statuses that mean a customer may not pay or may not exist: shown as a warning.
WARN = {"dissolved": "Dissolved", "liquidation": "In liquidation", "receivership": "In receivership",
        "administration": "In administration", "voluntary-arrangement": "Voluntary arrangement",
        "insolvency-proceedings": "Insolvency proceedings", "converted-closed": "Closed", "closed": "Closed",
        "removed": "Removed from the register"}
DAILY_CHECKS = 100


class CompaniesHouseError(Exception):
    pass


def configured():
    c = current_app.config
    return bool(c.get("CH_BACKEND") or c.get("COMPANIES_HOUSE_API_KEY"))


def call(path, params=None):
    fake = current_app.config.get("CH_BACKEND")
    if fake:
        return fake.request(path, params or {})
    key = current_app.config.get("COMPANIES_HOUSE_API_KEY") or ""
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    auth = base64.b64encode(f"{key}:".encode()).decode()
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {auth}", "User-Agent": "CAE-CRM"})
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise CompaniesHouseError(f"Companies House refused the request ({e.code}).") from None
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise CompaniesHouseError(f"Couldn't reach Companies House: {e}") from None


def status_label(status):
    return WARN.get(status) or (status or "").replace("-", " ").capitalize()


def _address(a):
    a = a or {}
    line = ", ".join(filter(None, [" ".join(filter(None, [a.get("premises"), a.get("address_line_1")])),
                                   a.get("address_line_2")]))
    return line, a.get("locality") or "", a.get("postal_code") or ""


def search(q):
    data = call("/search/companies", {"q": q, "items_per_page": 8}) or {}
    out = []
    for item in data.get("items") or []:
        line, city, postcode = _address(item.get("address"))
        out.append(dict(name=item.get("title", ""), number=item.get("company_number", ""),
                        status=item.get("company_status", ""), status_label=status_label(item.get("company_status")),
                        warn=item.get("company_status") in WARN, snippet=item.get("address_snippet", ""),
                        address=line, city=city, postcode=postcode))
    return out


def profile(number):
    data = call(f"/company/{urllib.parse.quote(number.strip().upper())}")
    if not data:
        return None
    line, city, postcode = _address(data.get("registered_office_address"))
    return dict(name=data.get("company_name", ""), number=data.get("company_number", ""),
                status=data.get("company_status", ""), sic=", ".join(data.get("sic_codes") or []),
                address=line, city=city, postcode=postcode)


def refresh(company):
    """Update a company from the register: status, SIC codes and registered office. Returns the profile, or None
    if the number isn't on the register. No commit."""
    p = profile(company["company_no"])
    db = get_db()
    stamp = now().isoformat(timespec="minutes")
    if p is None:
        db.execute("UPDATE companies SET ch_status=?, ch_checked_at=? WHERE id=?", ("not-found", stamp, company["id"]))
        return None
    db.execute("UPDATE companies SET ch_status=?, ch_sic=?, ch_checked_at=?, address=COALESCE(NULLIF(?, ''), address), "
               "city=COALESCE(NULLIF(?, ''), city), postcode=COALESCE(NULLIF(?, ''), postcode) WHERE id=?",
               (p["status"], p["sic"] or None, stamp, p["address"], p["city"], p["postcode"], company["id"]))
    if p["status"] in WARN and company["ch_status"] != p["status"]:
        log_event(f"Companies House status: {status_label(p['status'])}",
                  "Check before extending credit or taking new orders.", company_id=company["id"])
    return p


def refresh_due(budget=20):
    """For the daily job: re-check the companies checked longest ago, up to DAILY_CHECKS or the time budget."""
    if not configured():
        return 0
    started, done = time.monotonic(), 0
    due = rows("SELECT * FROM companies WHERE company_no IS NOT NULL AND company_no <> '' "
               "ORDER BY ch_checked_at IS NOT NULL, ch_checked_at LIMIT ?", DAILY_CHECKS)
    from flask import g
    for c in due:
        if time.monotonic() - started > budget:
            break
        g.public_workspace = c["workspace_id"]  # so timeline entries land in the company's workspace
        try:
            refresh(c)
        except CompaniesHouseError:
            current_app.logger.warning("Companies House check stopped: %s", c["company_no"])
            break
        finally:
            g.pop("public_workspace", None)
        done += 1
    get_db().commit()
    return done


def register(app):
    app.config.setdefault("COMPANIES_HOUSE_API_KEY", __import__("os").environ.get("COMPANIES_HOUSE_API_KEY", ""))
    app.config.setdefault("CH_BACKEND", None)
    app.add_template_global(configured, "companies_house_on")
    app.add_template_global(status_label, "ch_status_label")
    app.add_template_global(WARN, "ch_warn")

    @app.get("/companies-house/search")
    def companies_house_search():
        if not configured():
            abort(404)
        q = request.args.get("q", "").strip()
        if len(q) < 3:
            return jsonify(results=[])
        try:
            return jsonify(results=search(q[:100]))
        except CompaniesHouseError as e:
            current_app.logger.warning("Companies House search failed: %s", e)
            return jsonify(results=[], error="Companies House couldn't be reached. Type the details in instead."), 502

    @app.post("/companies/<int:company_id>/companies-house")
    def companies_house_refresh(company_id):
        if not configured():
            abort(404)
        c = get_or_404("companies", company_id)
        if not c["company_no"]:
            flash("Add the company's Companies House number first.", "error")
            return redirect(url_for("company", company_id=company_id))
        try:
            p = refresh(c)
        except CompaniesHouseError as e:
            flash(f"{e} Try again later.", "error")
            return redirect(url_for("company", company_id=company_id))
        get_db().commit()
        if p is None:
            flash(f"Companies House has no company numbered {c['company_no']}. Check the number.", "error")
        else:
            flash(f"Updated from Companies House: {status_label(p['status'])}.", "error" if p["status"] in WARN else "ok")
        return redirect(url_for("company", company_id=company_id))
