"""Business summaries must show real balances and correctly scoped relationships."""

from contextlib import contextmanager
from datetime import timedelta
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import urlsplit

import pytest
from flask import template_rendered

from conftest import ADMIN, TODAY, first_id, query
from db import get_db


@contextmanager
def context_for(app):
    found = []

    def capture(sender, template, context, **extra):
        found.append(context)

    template_rendered.connect(capture, app)
    try:
        yield found
    finally:
        template_rendered.disconnect(capture, app)


class PageStructure(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.links, self.headings = [], [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.append(attrs["id"])
        if attrs.get("href"):
            self.links.append(attrs["href"])
        if tag in ("h1", "h2", "h3"):
            self.headings.append(tag)


@pytest.mark.parametrize("table,route", [("contacts", "contacts"), ("companies", "companies"), ("deals", "deals")])
def test_record_navigation_has_real_targets_and_one_primary_heading(app, client, table, route):
    page = client.get(f"/{route}/{first_id(app, table, app.ws)}").get_data(as_text=True)
    structure = PageStructure()
    structure.feed(page)
    assert structure.headings[0] == "h1" and structure.headings.count("h1") == 1
    assert len(structure.ids) == len(set(structure.ids))
    for link in structure.links:
        if link.startswith("#"):
            assert link[1:] in structure.ids, link
    for anchor in ("record-composer", "record-activity", "related-quotes", "related-invoices"):
        assert anchor in structure.ids
    assert 'aria-label="Related records"' in page and 'aria-label="Business snapshot"' in page
    assert "data-activity-search" in page and 'aria-live="polite"' in page


def test_next_action_updates_after_completion_and_ignores_done_tasks(app, client):
    contact = first_id(app, "contacts", app.ws)
    with app.app_context():
        db = get_db()
        db.execute("UPDATE activities SET done=1 WHERE workspace_id=?", (app.ws,))
        late = db.insert("activities", workspace_id=app.ws, contact_id=contact, kind="Call", owner=ADMIN[0],
                         subject="Priority overdue call", due_at=(TODAY - timedelta(days=1)).isoformat()+"T09:00", done=0)
        db.insert("activities", workspace_id=app.ws, contact_id=contact, kind="Task", owner=ADMIN[0],
                  subject="Next planned action", due_at=TODAY.isoformat()+"T14:00", done=0)
        db.commit()
    with context_for(app) as contexts:
        client.get(f"/contacts/{contact}")
    assert contexts[-1]["insights"]["next_task"]["id"] == late
    assert contexts[-1]["insights"]["overdue_tasks"] == 1
    assert client.post(f"/activities/{late}/toggle", data={"csrf": client.csrf}).status_code == 302
    with context_for(app) as contexts:
        client.get(f"/contacts/{contact}")
    assert contexts[-1]["insights"]["next_task"]["subject"] == "Next planned action"
    assert contexts[-1]["insights"]["overdue_tasks"] == 0


def new_invoice(db, workspace, company, number, **extra):
    return db.insert("invoices", workspace_id=workspace, company_id=company, number=number,
                     description="Summary fixture", net=100000, vat=20000, vat_rate=20,
                     issue_date=TODAY.isoformat(), due_date=(TODAY - timedelta(days=1)).isoformat(), **extra)


def test_company_balance_accounts_for_payments_credits_charges_and_legacy_paid_records(app, client):
    company = first_id(app, "companies", app.ws)
    with app.app_context():
        db = get_db()
        db.execute("UPDATE invoices SET paid_date=? WHERE workspace_id=?", (TODAY.isoformat(), app.ws))
        partial = new_invoice(db, app.ws, company, "PARTIAL", amount_paid=50000, credited=12000,
                              late_interest=2000, late_compensation=4000)
        new_invoice(db, app.ws, company, "CREDITED", credited=120000)
        new_invoice(db, app.ws, company, "PAID-EXTERNALLY", paid_date=TODAY.isoformat())
        db.commit()
    with context_for(app) as contexts:
        page = client.get(f"/companies/{company}").get_data(as_text=True)
    data = contexts[-1]
    assert data["stats"]["outstanding"] == 64000
    assert data["insights"]["outstanding"] == 64000 and data["insights"]["overdue_invoices"] == 1
    assert next(c for c in data["insights"]["invoice_cards"] if c["row"]["id"] == partial)["state"] == "Overdue"
    assert "£640.00 remaining" in page


def test_contact_finance_is_linked_to_person_not_every_invoice_at_company(app, client, rival):
    contact = first_id(app, "contacts", app.ws)
    company = first_id(app, "companies", app.ws)
    deal = first_id(app, "deals", app.ws)
    foreign_company = first_id(app, "companies", app.rival_ws)
    with app.app_context():
        db = get_db()
        db.execute("UPDATE deals SET contact_id=NULL WHERE workspace_id=?", (app.ws,))
        db.execute("UPDATE deals SET contact_id=? WHERE id=?", (contact, deal))
        linked = new_invoice(db, app.ws, company, "LINKED", deal_id=deal)
        sibling = new_invoice(db, app.ws, company, "COMPANY-ONLY")
        foreign = new_invoice(db, app.rival_ws, foreign_company, "FOREIGN", deal_id=deal)
        quote = db.insert("quotes", workspace_id=app.ws, company_id=company, contact_id=contact,
                          number="DIRECT-QUOTE", title="Direct to person", status="Sent", token="record-test-quote",
                          net=1000, vat=200, issue_date=TODAY.isoformat(), expiry_date=(TODAY+timedelta(days=5)).isoformat(),
                          created_by=ADMIN[0], created_at=TODAY.isoformat())
        db.commit()
    with context_for(app) as contexts:
        client.get(f"/contacts/{contact}")
    insights = contexts[-1]["insights"]
    ids = {c["row"]["id"] for c in insights["invoice_cards"]}
    assert linked in ids and not {sibling, foreign} & ids
    assert any(c["row"]["id"] == quote for c in insights["quote_cards"])
    assert insights["waiting_quotes"] >= 1
    assert rival.get(f"/contacts/{contact}").status_code == 404


def test_closed_deal_is_described_as_closed_and_summary_gets_fresh_task_state(app, client):
    deal = first_id(app, "deals", app.ws)
    with app.app_context():
        db = get_db()
        db.execute("UPDATE deals SET stage='Won', closed_at=? WHERE id=?", (TODAY.isoformat(), deal))
        db.execute("UPDATE activities SET done=1 WHERE deal_id=?", (deal,))
        db.commit()
    page = client.get(f"/deals/{deal}").get_data(as_text=True)
    assert "Keep the handover clear" in page and "Won ·" in page
    assert "% likely · expected close" not in page


def test_brand_styles_load_on_app_marketing_login_and_legal_pages(client, anon):
    for actor, route in ((client, "/"), (anon, "/welcome"), (anon, "/login"), (anon, "/legal/privacy")):
        parser = PageStructure()
        parser.feed(actor.get(route).get_data(as_text=True))
        assert any(urlsplit(url).path == "/static/brand.css" for url in parser.links)
    assert anon.get("/static/brand.css").status_code == 200


def contrast(a, b):
    def luminance(hex_colour):
        rgb = [int(hex_colour[i:i+2], 16)/255 for i in (1, 3, 5)]
        linear = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in rgb]
        return sum(v*w for v, w in zip(linear, (.2126, .7152, .0722)))
    lighter, darker = sorted((luminance(a), luminance(b)), reverse=True)
    return (lighter+.05)/(darker+.05)


def test_brand_text_and_primary_actions_have_readable_contrast_in_both_themes():
    css = (Path(__file__).parents[1]/"static"/"brand.css").read_text()
    base = dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})", css.split(":root {", 1)[1].split("}", 1)[0]))
    dark = base | dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})", css.split(':root[data-theme="dark"] {', 1)[1].split("}", 1)[0]))
    base["--surface"] = "#ffffff"
    for palette in (base, dark):
        for foreground, background in (("--primary", "--surface"), ("--primary", "--accent-soft"),
                                       ("--ink", "--canvas"), ("--muted", "--canvas"),
                                       ("--on-primary", "--primary")):
            assert contrast(palette[foreground], palette[background]) >= 4.5, (foreground, background)
        assert contrast("#ffffff", palette["--cta"]) >= 4.5
