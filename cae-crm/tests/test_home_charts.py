"""Home page charts: the won panel's status, chart choices remembered per person, and the running total."""
import json
import re

import charts
from conftest import query


def chart_data(page):
    return json.loads(re.search(r'<script type="application/json" id="revenue-data">(.*?)</script>', page, re.S).group(1))


def pressed(page, attr):
    return re.findall(rf'data-{attr}="(\w+)" aria-pressed="true"', page)


def test_everyone_starts_on_bars_and_the_stage_bar(client):
    page = client.get("/").get_data(as_text=True)
    assert pressed(page, "chart-view") == ["bars"] and pressed(page, "pipeline-view") == ["bar"]
    assert 'data-view="bars"' in page and 'data-mix-view="bar"' in page


def test_a_chosen_view_is_remembered_for_that_person_only(client, member_client):
    for chart, view in (("revenue", "running"), ("pipeline", "donut")):
        resp = client.post("/home/chart-view", data={"csrf": client.csrf, "chart": chart, "view": view},
                           headers={"X-Requested-With": "fetch"})
        assert resp.status_code == 204
    page = client.get("/").get_data(as_text=True)
    assert pressed(page, "chart-view") == ["running"] and pressed(page, "pipeline-view") == ["donut"]
    # The range buttons don't apply to the running total, and the donut is the one pipeline view shown.
    assert re.search(r'data-range-group\s+hidden', page)
    assert re.search(r'data-pipeline-panel="donut"\s*>', page) and re.search(r'data-pipeline-panel="bar"\s+hidden', page)
    # Someone else on the team still sees the defaults.
    other = member_client.get("/").get_data(as_text=True)
    assert pressed(other, "chart-view") == ["bars"] and pressed(other, "pipeline-view") == ["bar"]


def test_unknown_charts_and_views_are_refused(app, client):
    for chart, view in (("revenue", "pie"), ("pipeline", "running"), ("sales", "bars"), ("revenue", "")):
        resp = client.post("/home/chart-view", data={"csrf": client.csrf, "chart": chart, "view": view},
                           headers={"X-Requested-With": "fetch"})
        assert resp.status_code == 400, (chart, view)
    assert query(app, "SELECT chart_prefs FROM users WHERE email='admin@example.co.uk'")[0][0] is None


def test_saving_a_view_needs_the_csrf_token(client):
    resp = client.post("/home/chart-view", data={"chart": "revenue", "view": "line"})
    assert resp.status_code in (400, 403)


def test_running_total_adds_up_this_month_and_projects_today_s_pace(app, client):
    data = chart_data(client.get("/").get_data(as_text=True))
    running, target = data["running"], data["target"]
    days = running["days"]
    assert len(days) == 31 and days[0]["label"] == "1" and days[-1]["label"] == "31"  # October 2026
    # Won so far stops at today (the 16th); the projection starts there and runs to the month end.
    assert days[15]["won"] is not None and days[16]["won"] is None
    assert days[14]["projected"] is None and days[15]["projected"] == days[15]["won"]
    won = [d["won"] for d in days if d["won"] is not None]
    assert won == sorted(won) and won[-1] == running["won"]
    month_won = query(app, "SELECT SUM(value) FROM deals WHERE workspace_id=? AND stage='Won' AND closed_at >= '2026-10-01' "
                           "AND closed_at <= '2026-10-16T23:59'", app.ws)[0][0] or 0
    assert round(running["won"] * 100) == month_won
    # Even pace reaches the target on the last working day.
    assert days[-1]["pace"] == target and days[0]["pace"] > 0
    assert running["projected"] == days[-1]["projected"] >= running["won"]


def test_won_panel_shows_its_status_with_words_and_an_icon(client):
    page = client.get("/").get_data(as_text=True)
    status = re.search(r'<section class="track (is-ahead|is-behind)"', page).group(1)
    word = "on or ahead of pace" if status == "is-ahead" else "behind pace"
    assert f"Won so far: {word}" in page and "Where an even pace would be today" in page
    assert re.search(r'<p class="verdict-main"><svg class="icon"', page)


def test_donut_shares_add_up_and_skip_empty_stages():
    svg = str(charts.donut([(300, "var(--stage-1)"), (100, "var(--stage-2)"), (0, "var(--stage-3)")], "4", "open deals", "Ring"))
    lengths = [float(a) for a, _ in re.findall(r'stroke-dasharray="([\d.]+) ([\d.]+)"', svg)]
    assert len(lengths) == 2 and abs(sum(lengths) - (100 - 2 * 0.8)) < 0.01
    assert ">4</text>" in svg and ">open deals</text>" in svg and 'aria-label="Ring"' in svg
    empty = str(charts.donut([(0, "x")], "0", "open deals", "Ring"))
    assert "donut-seg" not in empty and "donut-track" in empty
