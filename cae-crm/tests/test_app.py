import io
import re

import pytest

from conftest import first_id, query

FETCH = {"X-Requested-With": "fetch"}


@pytest.mark.parametrize("path", ["/", "/contacts", "/contacts?lifecycle=Customer&sort=name", "/companies",
                                  "/companies?sort=pipeline", "/pipeline", "/pipeline?view=list&stage=Won",
                                  "/tickets", "/tickets?view=list&open=1", "/tasks", "/tasks?month=2026-12&mine=1",
                                  "/products", "/products?show=archived", "/invoices", "/projects", "/reports",
                                  "/settings", "/import"])
def test_pages_render(client, path):
    assert client.get(path).status_code == 200


def test_record_pages_render(app, client):
    for table, path in [("contacts", "/contacts/{}"), ("companies", "/companies/{}"), ("deals", "/deals/{}"),
                        ("tickets", "/tickets/{}"), ("invoices", "/invoices/{}")]:
        assert client.get(path.format(first_id(app, table, app.ws))).status_code == 200, table


def test_old_addresses_redirect(app, client):
    company = first_id(app, "companies", app.ws)
    assert client.get("/customers").headers["Location"].endswith("/companies")
    assert client.get(f"/customers/{company}").headers["Location"].endswith(f"/companies/{company}")
    assert client.get("/schedule").headers["Location"].endswith("/tasks")
    assert client.get("/finance").headers["Location"].endswith("/invoices")
    assert client.get("/growth").headers["Location"].endswith("/reports")


def test_overview_has_dashboard_sections(client):
    html = client.get("/").get_data(as_text=True)
    for text in ("Won in October", "Open pipeline", "Open tickets", "Closing in the next 30 days",
                 "Pipeline by stage", "FY2026/27 Q3", "<svg", "revenue-data"):
        assert text in html
    # Friday 16/10/2026: 11 of October's 22 working days have gone.
    assert "11 of 22 working days gone" in html


def test_search_api_finds_every_kind(client):
    assert client.get("/api/search?q=a").json == []
    kinds = {r["kind"] for r in client.get("/api/search?q=Mersey").json}
    assert {"Company", "Contact"} <= kinds
    assert any(r["kind"] == "Ticket" for r in client.get("/api/search?q=invoice").json)


def test_post_without_csrf_is_rejected(client):
    assert client.post("/deals", data={"title": "x"}).status_code == 400


def test_open_redirect_blocked(app, client):
    task = first_id(app, "activities", app.ws)
    resp = client.post(f"/activities/{task}/toggle", data={"csrf": client.csrf, "next": "//evil.example"})
    assert resp.headers["Location"].endswith("/tasks")


# --- Contacts and companies ------------------------------------------------------

def test_create_company_validates_uk_fields(client):
    resp = client.post("/companies", data={"csrf": client.csrf, "name": "Acme", "postcode": "NOPE", "vat_no": "12"})
    html = resp.get_data(as_text=True)
    assert resp.status_code == 422 and "valid UK postcode" in html and "GB123456789" in html
    resp = client.post("/companies", data={"csrf": client.csrf, "name": "Acme Ltd", "postcode": "sw1a1aa",
                                           "vat_no": "GB123456789", "company_no": "1234567", "website": "acme.co.uk"})
    page = client.get(resp.headers["Location"]).get_data(as_text=True)
    assert "SW1A 1AA" in page and "01234567" in page and "https://acme.co.uk" in page


def test_contact_lifecycle_timeline_and_gdpr(app, client):
    resp = client.post("/contacts", data={"csrf": client.csrf, "first_name": "Grace", "last_name": "Hopper",
                                          "email": "grace@example.co.uk", "phone": "07700 900001",
                                          "lawful_basis": "Consent", "marketing_consent": "on"})
    contact = int(resp.headers["Location"].rsplit("/", 1)[1])
    page = client.get(f"/contacts/{contact}").get_data(as_text=True)
    assert "+44 7700 900001" in page and "Opted in 16/10/2026" in page and "Contact created" in page
    # A duplicate email in the same workspace is refused.
    client.post("/contacts", data={"csrf": client.csrf, "first_name": "G", "last_name": "H",
                                   "email": "grace@example.co.uk", "lawful_basis": "Consent"})
    assert query(app, "SELECT COUNT(*) FROM contacts WHERE email='grace@example.co.uk'")[0][0] == 1

    client.post("/engagements", data={"csrf": client.csrf, "kind": "call", "subject": "Intro call",
                                      "outcome": "Connected", "body": "Keen on a demo", "contact_id": contact,
                                      "date": "2026-10-16", "time": "10:00"})
    page = client.get(f"/contacts/{contact}").get_data(as_text=True)
    assert "Intro call" in page and "Keen on a demo" in page and "Connected" in page

    client.post(f"/contacts/{contact}/edit", data={"csrf": client.csrf, "first_name": "Grace", "last_name": "Hopper",
                                                   "email": "grace@example.co.uk", "lawful_basis": "Consent",
                                                   "lifecycle_stage": "Sales qualified lead", "lead_status": "Connected"})
    page = client.get(f"/contacts/{contact}").get_data(as_text=True)
    assert "Lifecycle stage changed to Sales qualified lead" in page and "Marketing consent withdrawn" in page

    export = client.get(f"/contacts/{contact}/export")
    assert export.json["data_subject"]["email"] == "grace@example.co.uk"
    assert export.json["controller"]["name"] == "Thistle Ltd"
    assert any(a["subject"] == "Intro call" for a in export.json["activity"])
    client.post(f"/contacts/{contact}/erase", data={"csrf": client.csrf})
    assert client.get(f"/contacts/{contact}").status_code == 404
    assert not query(app, "SELECT 1 FROM engagements WHERE subject='Intro call'")


def test_task_from_composer_and_tick_off(app, client):
    company = first_id(app, "companies", app.ws)
    client.post("/engagements", data={"csrf": client.csrf, "kind": "task", "subject": "Send the proposal",
                                      "task_type": "Email", "company_id": company, "date": "2026-10-20", "time": "14:30"})
    (task,) = query(app, "SELECT id, kind, done FROM activities WHERE subject='Send the proposal'")
    assert (task["kind"], task["done"]) == ("Email", 0)
    assert "Send the proposal" in client.get(f"/companies/{company}").get_data(as_text=True)
    resp = client.post(f"/activities/{task['id']}/toggle", data={"csrf": client.csrf}, headers=FETCH)
    assert resp.json["done"] is True


def test_company_with_invoices_cannot_be_deleted(app, client):
    company = query(app, "SELECT company_id FROM invoices WHERE workspace_id=? LIMIT 1", app.ws)[0][0]
    client.post(f"/companies/{company}/delete", data={"csrf": client.csrf})
    assert query(app, "SELECT COUNT(*) FROM companies WHERE id=?", company)[0][0] == 1


# --- Deals, products and line items --------------------------------------------

def test_deal_from_products_then_won_and_invoiced(app, client):
    company = first_id(app, "companies", app.ws)
    contact = first_id(app, "contacts", app.ws, "company_id=?", company)
    resp = client.post("/deals", data={"csrf": client.csrf, "title": "Test rollout", "company_id": company,
                                       "contact_id": contact, "close_date": "2026-11-30", "stage": "Proposal"})
    deal = int(resp.headers["Location"].rsplit("/", 1)[1])
    client.post("/products", data={"csrf": client.csrf, "name": "Widget", "unit_price": "£100", "vat_rate": "20",
                                   "billing": "One-off"})
    widget = first_id(app, "products", app.ws, "name='Widget'")
    client.post(f"/deals/{deal}/lines", data={"csrf": client.csrf, "product_id": widget, "quantity": "3"})
    client.post(f"/deals/{deal}/lines", data={"csrf": client.csrf, "name": "Children's car seats", "quantity": "2",
                                              "unit_price": "50", "discount_pct": "10", "vat_rate": "5"})
    assert query(app, "SELECT value FROM deals WHERE id=?", deal)[0][0] == 30_000 + 9_000
    page = client.get(f"/deals/{deal}").get_data(as_text=True)
    assert "VAT at 20% on £300.00" in page and "VAT at 5% on £90.00" in page and "£454.50" in page

    resp = client.post(f"/deals/{deal}/stage", data={"stage": "Won"}, headers=FETCH | {"X-CSRF-Token": client.csrf})
    assert resp.json["ok"] and resp.json["probability"] == 100
    assert query(app, "SELECT closed_at FROM deals WHERE id=?", deal)[0][0] == "2026-10-16"
    assert query(app, "SELECT COUNT(*) FROM projects WHERE deal_id=?", deal)[0][0] == 1
    assert query(app, "SELECT lifecycle_stage FROM contacts WHERE id=?", contact)[0][0] == "Customer"

    resp = client.post(f"/deals/{deal}/invoice", data={"csrf": client.csrf})
    inv = query(app, "SELECT * FROM invoices WHERE deal_id=?", deal)[0]
    assert (inv["net"], inv["vat"], inv["vat_rate"]) == (39_000, 6_000 + 450, -1)
    assert inv["due_date"] == "2026-11-15"
    html = client.get(resp.headers["Location"]).get_data(as_text=True)
    assert "Children&#39;s car seats" in html and "£454.50" in html and "Tax point" in html


def test_removing_lines_and_product_archive(app, client):
    deal = first_id(app, "deals", app.ws, "stage='Proposal'")
    lines = query(app, "SELECT id FROM line_items WHERE deal_id=?", deal)
    for (line_id,) in lines:
        client.post(f"/deals/{deal}/lines/{line_id}", data={"csrf": client.csrf, "action": "delete"})
    assert query(app, "SELECT value FROM deals WHERE id=?", deal)[0][0] == 0
    product = first_id(app, "products", app.ws)
    client.post(f"/products/{product}", data={"csrf": client.csrf, "action": "archive"})
    assert query(app, "SELECT active FROM products WHERE id=?", product)[0][0] == 0
    assert client.post("/products", data={"csrf": client.csrf, "name": "Free audit", "unit_price": "0",
                                          "vat_rate": "20"}).status_code == 302
    assert query(app, "SELECT unit_price FROM products WHERE name='Free audit'")[0][0] == 0


def test_not_vat_registered_charges_no_vat(app, client):
    client.post("/settings", data={"csrf": client.csrf, "name": "Thistle Ltd", "legal_name": "Thistle Ltd",
                                   "monthly_target": "100,000", "invoice_prefix": "TH", "payment_terms": "14"})
    company = first_id(app, "companies", app.ws)
    client.post("/invoices", data={"csrf": client.csrf, "company_id": company, "description": "Consulting",
                                   "net": "1,000.00", "vat_rate": "20"})
    inv = query(app, "SELECT * FROM invoices WHERE workspace_id=? ORDER BY id DESC LIMIT 1", app.ws)[0]
    assert (inv["net"], inv["vat"], inv["due_date"]) == (100_000, 0, "2026-10-30")
    assert inv["number"].startswith("TH-")
    assert "not registered for VAT" in client.get(f"/invoices/{inv['id']}").get_data(as_text=True)


def test_invoice_vat_and_payment(app, client):
    company = first_id(app, "companies", app.ws)
    client.post("/invoices", data={"csrf": client.csrf, "company_id": company, "description": "Consulting",
                                   "net": "1,000.00", "vat_rate": "20"})
    inv = query(app, "SELECT * FROM invoices WHERE workspace_id=? ORDER BY id DESC LIMIT 1", app.ws)[0]
    assert (inv["net"], inv["vat"], inv["due_date"]) == (100_000, 20_000, "2026-11-15")
    assert "£1,200.00" in client.get(f"/invoices/{inv['id']}").get_data(as_text=True)
    client.post(f"/invoices/{inv['id']}/paid", data={"csrf": client.csrf})
    assert query(app, "SELECT paid_date FROM invoices WHERE id=?", inv["id"])[0][0] == "2026-10-16"


def test_settings_validate(client):
    resp = client.post("/settings", data={"csrf": client.csrf, "name": "", "vat_registered": "on", "vat_no": "",
                                          "invoice_prefix": "too-long-prefix", "payment_terms": "365",
                                          "monthly_target": "lots"})
    assert resp.status_code == 422


# --- Tickets ----------------------------------------------------------------------

def test_ticket_service_levels_use_uk_working_hours(app, client):
    contact = first_id(app, "contacts", app.ws, "company_id IS NOT NULL")
    # Opened 11:00 on Friday 16 October. An Urgent ticket needs a reply within 1 working hour and a fix within 4.
    resp = client.post("/tickets", data={"csrf": client.csrf, "subject": "Can't log in", "priority": "Urgent",
                                         "contact_id": contact})
    ticket = int(resp.headers["Location"].rsplit("/", 1)[1])
    t = query(app, "SELECT * FROM tickets WHERE id=?", ticket)[0]
    assert (t["first_response_due"], t["resolution_due"]) == ("2026-10-16T12:00", "2026-10-16T15:00")
    assert t["company_id"] == query(app, "SELECT company_id FROM contacts WHERE id=?", contact)[0][0]
    # Low priority: 16 and 40 working hours run over the weekend into the following weeks.
    client.post(f"/tickets/{ticket}/edit", data={"csrf": client.csrf, "subject": "Can't log in", "priority": "Low",
                                                 "contact_id": contact})
    t = query(app, "SELECT * FROM tickets WHERE id=?", ticket)[0]
    assert (t["first_response_due"], t["resolution_due"]) == ("2026-10-20T11:00", "2026-10-23T11:00")

    resp = client.post(f"/tickets/{ticket}/status", data={"status": "Waiting on contact"},
                       headers=FETCH | {"X-CSRF-Token": client.csrf})
    assert resp.json["ok"]
    t = query(app, "SELECT * FROM tickets WHERE id=?", ticket)[0]
    assert t["first_responded_at"] == "2026-10-16T11:00" and t["closed_at"] is None
    client.post(f"/tickets/{ticket}/status", data={"csrf": client.csrf, "status": "Closed"})
    page = client.get(f"/tickets/{ticket}").get_data(as_text=True)
    assert "Ticket closed" in page and page.count("Met") >= 2


def test_ticket_board_and_list(client):
    board = client.get("/tickets").get_data(as_text=True)
    assert "Waiting on us" in board and "past due" in board
    listing = client.get("/tickets?view=list&priority=Urgent").get_data(as_text=True)
    assert "Urgent" in listing


# --- Lists, views, bulk actions, import and export --------------------------------

def test_list_filters_and_saved_views(app, client):
    html = client.get("/contacts?lifecycle=Customer").get_data(as_text=True)
    assert "Customer" in html and "Save view" not in html  # matches the built-in Customers tab
    resp = client.post("/views", data={"csrf": client.csrf, "object": "contacts", "name": "Scots",
                                       "query": "owner=Priya+Nair&lifecycle=Customer"})
    assert resp.status_code == 302
    html = client.get(resp.headers["Location"]).get_data(as_text=True)
    assert "Scots" in html
    view = query(app, "SELECT id FROM saved_views WHERE name='Scots'")[0][0]
    client.post(f"/views/{view}/delete", data={"csrf": client.csrf})
    assert not query(app, "SELECT 1 FROM saved_views WHERE id=?", view)


def test_bulk_owner_lifecycle_and_delete(app, client):
    ids = [r[0] for r in query(app, "SELECT id FROM contacts WHERE workspace_id=? ORDER BY id LIMIT 3", app.ws)]
    client.post("/bulk/contacts", data={"csrf": client.csrf, "ids": ids, "action": "owner", "value": "Test Member"})
    client.post("/bulk/contacts", data={"csrf": client.csrf, "ids": ids, "action": "lifecycle", "value": "Evangelist"})
    rows = query(app, f"SELECT owner, lifecycle_stage FROM contacts WHERE id IN ({','.join('?' * 3)})", *ids)
    assert {tuple(r) for r in rows} == {("Test Member", "Evangelist")}
    client.post("/bulk/contacts", data={"csrf": client.csrf, "ids": ids[:1], "action": "delete"})
    assert not query(app, "SELECT 1 FROM contacts WHERE id=?", ids[0])


def test_members_cannot_bulk_delete(app, member_client):
    contact = first_id(app, "contacts", app.ws)
    resp = member_client.post("/bulk/contacts", data={"csrf": member_client.csrf, "ids": [contact], "action": "delete"})
    assert resp.status_code == 403


def test_export_is_spreadsheet_safe(app, client):
    company = first_id(app, "companies", app.ws)
    client.post("/contacts", data={"csrf": client.csrf, "first_name": "=HYPERLINK(\"x\")", "last_name": "Smith",
                                   "lawful_basis": "Consent", "company_id": company})
    csv_text = client.get("/export/contacts?q=smith").get_data(as_text=True)
    assert csv_text.startswith("﻿First name,Last name")
    assert "'=HYPERLINK" in csv_text


def test_import_contacts_with_mapping(app, client):
    existing = query(app, "SELECT email FROM contacts WHERE workspace_id=? AND email <> '' LIMIT 1", app.ws)[0][0]
    data = ("Name,E-mail,Organisation,Mobile,Opted in\r\n"
            "Ada Lovelace,ada@engine.co.uk,Analytical Ltd,07700 900123,yes\r\n"
            f"Someone Else,{existing},,,no\r\n"
            "Nobody,,,,\r\n").encode("cp1252")
    resp = client.post("/import", data={"csrf": client.csrf, "object": "contacts",
                                        "file": (io.BytesIO(data), "people.csv")}, content_type="multipart/form-data")
    mapping_page = client.get(resp.headers["Location"]).get_data(as_text=True)
    assert "Full name (split into first and last)" in mapping_page and "ada@engine.co.uk" in mapping_page
    resp = client.post(resp.headers["Location"], data={"csrf": client.csrf, "map_0": "full_name", "map_1": "email",
                                                        "map_2": "company", "map_3": "phone", "map_4": "marketing_consent",
                                                        "duplicates": "skip", "lawful_basis": "Legitimate interests",
                                                        "lifecycle": "Lead"})
    html = resp.get_data(as_text=True)
    assert "Import finished" in html and "already in your contacts" in html and "Needs a first and last name" in html
    ada = query(app, "SELECT * FROM contacts WHERE email='ada@engine.co.uk'")[0]
    assert (ada["first_name"], ada["last_name"], ada["phone"], ada["marketing_consent"]) == \
        ("Ada", "Lovelace", "+44 7700 900123", 1)
    assert query(app, "SELECT name FROM companies WHERE id=?", ada["company_id"])[0][0] == "Analytical Ltd"


def test_import_rejects_files_without_rows(client):
    resp = client.post("/import", data={"csrf": client.csrf, "object": "companies",
                                        "file": (io.BytesIO(b"Name\r\n"), "empty.csv")}, content_type="multipart/form-data")
    assert resp.headers["Location"].endswith("/import")


def test_reports_figures(client):
    html = client.get("/reports").get_data(as_text=True)
    for text in ("Lifecycle funnel", "Service levels", "Won revenue by lead source", "Leaderboard",
                 "Products in the open pipeline"):
        assert text in html
    assert re.search(r"\d+ days", html)
