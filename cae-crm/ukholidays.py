"""Bank holidays for each UK nation: England and Wales, Scotland, and Northern Ireland. A workspace chooses its nation
under Business details, and service-level clocks, the Tasks calendar and working days on Home follow it.

Dates come from GOV.UK's feed (www.gov.uk/bank-holidays.json), which the daily job fetches into the bank_holidays
table. The dates GOV.UK published up to 2028 are built in, so working hours are right even if the feed can't be
reached. Tests set HOLIDAYS_BACKEND to a fake that returns the feed's JSON."""

import json
import urllib.error
import urllib.request
from datetime import date

from flask import current_app, g

from db import get_db

FEED = "https://www.gov.uk/bank-holidays.json"
REGIONS = {"england-and-wales": "England and Wales", "scotland": "Scotland", "northern-ireland": "Northern Ireland"}
DEFAULT = "england-and-wales"
# From GOV.UK's feed, October 2026.
BUILT_IN = {
    "england-and-wales": (
        "2025-01-01 2025-04-18 2025-04-21 2025-05-05 2025-05-26 2025-08-25 2025-12-25 2025-12-26 "
        "2026-01-01 2026-04-03 2026-04-06 2026-05-04 2026-05-25 2026-08-31 2026-12-25 2026-12-28 "
        "2027-01-01 2027-03-26 2027-03-29 2027-05-03 2027-05-31 2027-08-30 2027-12-27 2027-12-28 "
        "2028-01-03 2028-04-14 2028-04-17 2028-05-01 2028-05-29 2028-08-28 2028-12-25 2028-12-26"),
    "scotland": (
        "2025-01-01 2025-01-02 2025-04-18 2025-05-05 2025-05-26 2025-08-04 2025-12-01 2025-12-25 2025-12-26 "
        "2026-01-01 2026-01-02 2026-04-03 2026-05-04 2026-05-25 2026-06-15 2026-08-03 2026-11-30 2026-12-25 2026-12-28 "
        "2027-01-01 2027-01-04 2027-03-26 2027-05-03 2027-05-31 2027-08-02 2027-11-30 2027-12-27 2027-12-28 "
        "2028-01-03 2028-01-04 2028-04-14 2028-05-01 2028-05-29 2028-08-07 2028-11-30 2028-12-25 2028-12-26"),
    "northern-ireland": (
        "2025-01-01 2025-03-17 2025-04-18 2025-04-21 2025-05-05 2025-05-26 2025-07-14 2025-08-25 2025-12-25 2025-12-26 "
        "2026-01-01 2026-03-17 2026-04-03 2026-04-06 2026-05-04 2026-05-25 2026-07-13 2026-08-31 2026-12-25 2026-12-28 "
        "2027-01-01 2027-03-17 2027-03-26 2027-03-29 2027-05-03 2027-05-31 2027-07-12 2027-08-30 2027-12-27 2027-12-28 "
        "2028-01-03 2028-03-17 2028-04-14 2028-04-17 2028-05-01 2028-05-29 2028-07-12 2028-08-28 2028-12-25 2028-12-26"),
}


def built_in(region):
    return {date.fromisoformat(d) for d in BUILT_IN.get(region, BUILT_IN[DEFAULT]).split()}


def for_region(region):
    """Every known bank holiday in a nation: the built-in dates plus any fetched from GOV.UK since."""
    region = region if region in REGIONS else DEFAULT
    cache = g.setdefault("bank_holidays", {})
    if region not in cache:
        found = built_in(region)
        try:
            found |= {date.fromisoformat(r[0]) for r in get_db().execute(
                "SELECT day FROM bank_holidays WHERE region=?", (region,)).fetchall()}
        except Exception:  # before the table exists, for example while seeding a brand new database
            pass
        cache[region] = found
    return cache[region]


def for_workspace(workspace_id=None):
    from core import ws
    row = get_db().execute("SELECT bank_holiday_region FROM workspaces WHERE id=?", (workspace_id or ws(),)).fetchone()
    return for_region(row[0] if row else DEFAULT)


def refresh():
    """For the daily job: fetch GOV.UK's feed and store any dates we didn't know. Returns how many were added."""
    fake = current_app.config.get("HOLIDAYS_BACKEND")
    try:
        if fake:
            data = fake()
        else:
            req = urllib.request.Request(FEED, headers={"User-Agent": "CAE-CRM"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        current_app.logger.warning("Bank holidays not refreshed: %s", e)
        return 0
    db, added = get_db(), 0
    for region in REGIONS:
        known = {r[0] for r in db.execute("SELECT day FROM bank_holidays WHERE region=?", (region,)).fetchall()}
        for event in (data.get(region) or {}).get("events") or []:
            day = str(event.get("date", ""))[:10]
            try:
                date.fromisoformat(day)
            except ValueError:
                continue
            if day not in known:
                db.insert("bank_holidays", region=region, day=day, title=str(event.get("title", ""))[:120])
                known.add(day)
                added += 1
    db.commit()
    return added
