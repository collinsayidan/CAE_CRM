"""Operational dashboard dates and board/list views must agree without crossing workspaces."""

from contextlib import contextmanager
from datetime import timedelta
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

import pytest
from flask import template_rendered

from conftest import ADMIN, TODAY, first_id
from db import get_db


@contextmanager
def rendered_context(app):
    captured = []

    def capture(sender, template, context, **extra):
        captured.append(context)

    template_rendered.connect(capture, app)
    try:
        yield captured
    finally:
        template_rendered.disconnect(capture, app)


def add_deal(app, title, offset, *, owner=ADMIN[0], stage="Qualified", workspace=None, old=False):
    workspace = workspace or app.ws
    company = first_id(app, "companies", workspace)
    with app.app_context():
        db = get_db()
        deal_id = db.insert("deals", workspace_id=workspace, company_id=company, title=title, value=123456,
                            probability=30, stage=stage, owner=owner, source="Website",
                            close_date=(TODAY + timedelta(days=offset)).isoformat(),
                            created_at=(TODAY - timedelta(days=60) if old else TODAY).isoformat())
        db.commit()
        return deal_id


def test_dashboard_splits_overdue_from_inclusive_upcoming_window(app, client, rival):
    yesterday = add_deal(app, "Review overdue date", -1)
    today = add_deal(app, "Due on boundary today", 0)
    last = add_deal(app, "Due on boundary thirty", 30)
    later = add_deal(app, "Outside thirty days", 31)
    won = add_deal(app, "Already closed", 2, stage="Won")
    foreign = add_deal(app, "Another workspace deal", 0, workspace=app.rival_ws)
    foreign_overdue = add_deal(app, "Another workspace overdue", -1, workspace=app.rival_ws)
    # Keep known boundaries in the first six despite seeded deals.
    with app.app_context():
        db = get_db()
        db.execute("UPDATE deals SET stage='Lost' WHERE workspace_id=? AND id NOT IN (?,?,?,?,?,?)",
                   (app.ws, yesterday, today, last, later, won, -1))
        db.commit()
    with rendered_context(app) as captured:
        client.get("/")
    data = captured[-1]
    assert {d["id"] for d in data["closing_soon"]} == {today, last}
    assert {d["id"] for d in data["overdue_deals"]} == {yesterday}
    assert data["overdue_deal_count"] == 1
    assert not {later, won, foreign, foreign_overdue} & {d["id"] for d in data["closing_soon"]}


def test_daily_focus_only_incomplete_tasks_due_today_or_earlier(app, client, rival):
    with app.app_context():
        db = get_db()
        db.execute("UPDATE activities SET done=1 WHERE workspace_id=?", (app.ws,))
        for title, offset, done, workspace in (
            ("Old outstanding", -4, 0, app.ws), ("Today outstanding", 0, 0, app.ws),
            ("Tomorrow outstanding", 1, 0, app.ws), ("Old completed", -3, 1, app.ws),
            ("Foreign outstanding", -2, 0, app.rival_ws),
        ):
            db.insert("activities", workspace_id=workspace, kind="Task", subject=title, owner=ADMIN[0],
                      due_at=(TODAY + timedelta(days=offset)).isoformat() + "T09:00", done=done)
        db.commit()
    with rendered_context(app) as captured:
        client.get("/")
    data = captured[-1]
    assert [a["subject"] for a in data["focus_tasks"]] == ["Old outstanding", "Today outstanding"]
    assert data["overdue_tasks"] == 1


@pytest.mark.parametrize("focus,offset,old", [("overdue", -1, False), ("upcoming", 30, False), ("quiet", 7, True)])
def test_board_and_list_share_owner_search_and_focus(app, client, rival, focus, offset, old):
    wanted = add_deal(app, "ExactFilter wanted", offset, old=old)
    add_deal(app, "ExactFilter wrong owner", offset, old=old, owner="Test Member")
    add_deal(app, "Different search", offset, old=old)
    add_deal(app, "ExactFilter foreign", offset, old=old, workspace=app.rival_ws)
    query = {"focus": focus, "q": "ExactFilter", "owner": ADMIN[0]}
    with rendered_context(app) as captured:
        board = client.get("/pipeline", query_string=query).get_data(as_text=True)
    context = captured[-1]
    ids = {d["id"] for column in context["columns"].values() for d in column}
    assert ids == {wanted}
    assert context["board_count"] == 1 and context["board_total"] == 123456
    assert context["board_forecast"] == 37036
    with rendered_context(app) as captured:
        client.get("/pipeline", query_string=query | {"view": "list", "open": "1"})
    assert {d["id"] for d in captured[-1]["records"]} == ids
    assert 'role="region" aria-label="Deals by stage"' in board and 'tabindex="0"' in board


def test_overdue_and_inactive_are_distinct_views(app, client):
    overdue = add_deal(app, "RiskFixture overdue", -1, old=True)
    inactive = add_deal(app, "RiskFixture inactive", 4, old=True)
    active = add_deal(app, "RiskFixture active", 4)
    with rendered_context(app) as captured:
        page = client.get("/pipeline?q=RiskFixture&focus=quiet").get_data(as_text=True)
    assert {d["id"] for column in captured[-1]["columns"].values() for d in column} == {inactive}
    assert f'data-deal="{overdue}"' not in page and f'data-deal="{active}"' not in page
    assert "No recent activity" in page
    page = client.get("/pipeline?q=RiskFixture&focus=overdue").get_data(as_text=True)
    assert f'data-deal="{overdue}"' in page and "Close date overdue" in page


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.urls.append(dict(attrs).get("href", ""))


def test_layout_switch_preserves_supported_filters_and_contacts_open_active_filters(client):
    page = client.get("/pipeline?owner=Test+Admin&q=Acme&focus=overdue").get_data(as_text=True)
    parser = Links()
    parser.feed(page)
    targets = [parse_qs(urlparse(url).query) for url in parser.urls if url.startswith("/pipeline?")]
    assert any(q.get("view") == ["list"] and q.get("focus") == ["overdue"]
               and q.get("owner") == ["Test Admin"] and q.get("q") == ["acme"] for q in targets)
    page = client.get("/contacts?consent=0&lifecycle=Lead").get_data(as_text=True)
    assert '<details class="advanced-filters" open>' in page
    assert '<span class="filter-count">2</span>' in page
    assert 'name="consent" data-autosubmit' in page
    assert 'href="/static/workspace.css?v=' in page
