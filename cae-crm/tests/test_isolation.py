"""Each business on CAE CRM sees and changes only its own records."""

from conftest import first_id, query

FETCH = {"X-Requested-With": "fetch"}


def theirs(app):
    """One of each record belonging to Thistle Ltd."""
    return {t: first_id(app, t, app.ws) for t in ("contacts", "companies", "deals", "tickets", "invoices", "products",
                                                  "activities", "projects", "engagements")}


def test_record_pages_are_not_found_across_workspaces(app, rival):
    ids = theirs(app)
    for path in (f"/contacts/{ids['contacts']}", f"/companies/{ids['companies']}", f"/deals/{ids['deals']}",
                 f"/tickets/{ids['tickets']}", f"/invoices/{ids['invoices']}", f"/contacts/{ids['contacts']}/export",
                 f"/products?edit={ids['products']}"):
        resp = rival.get(path)
        if path.startswith("/products"):
            assert "dlg-edit-product" not in resp.get_data(as_text=True)
        else:
            assert resp.status_code == 404, path


def test_writes_are_refused_across_workspaces(app, rival):
    ids = theirs(app)
    c = rival.csrf
    attempts = [
        (f"/contacts/{ids['contacts']}/edit", {"first_name": "Hacked", "last_name": "X", "lawful_basis": "Consent"}),
        (f"/contacts/{ids['contacts']}/erase", {}),
        (f"/companies/{ids['companies']}/edit", {"name": "Hacked", "postcode": "EH1 1AA"}),
        (f"/companies/{ids['companies']}/delete", {}),
        (f"/deals/{ids['deals']}/stage", {"stage": "Lost"}),
        (f"/deals/{ids['deals']}/edit", {"title": "Hacked"}),
        (f"/deals/{ids['deals']}/lines", {"name": "Hack", "quantity": "1", "unit_price": "1", "vat_rate": "20"}),
        (f"/deals/{ids['deals']}/invoice", {}),
        (f"/deals/{ids['deals']}/delete", {}),
        (f"/tickets/{ids['tickets']}/status", {"status": "Closed"}),
        (f"/tickets/{ids['tickets']}/edit", {"subject": "Hacked"}),
        (f"/invoices/{ids['invoices']}/paid", {}),
        (f"/products/{ids['products']}", {"action": "archive"}),
        (f"/activities/{ids['activities']}/toggle", {}),
        (f"/projects/{ids['projects']}", {"progress": "100", "status": "Complete"}),
        (f"/engagements/{ids['engagements']}/delete", {}),
    ]
    before = query(app, "SELECT COUNT(*) FROM engagements WHERE workspace_id=?", app.ws)[0][0]
    for path, data in attempts:
        assert rival.post(path, data=data | {"csrf": c}).status_code == 404, path
    assert query(app, "SELECT first_name FROM contacts WHERE id=?", ids["contacts"])[0][0] != "Hacked"
    assert query(app, "SELECT name FROM companies WHERE id=?", ids["companies"])[0][0] != "Hacked"
    assert query(app, "SELECT COUNT(*) FROM engagements WHERE workspace_id=?", app.ws)[0][0] == before


def test_forms_cannot_link_to_another_workspaces_records(app, rival):
    ids = theirs(app)
    rival.post("/contacts", data={"csrf": rival.csrf, "first_name": "Sly", "last_name": "Fox", "lawful_basis": "Consent",
                                  "company_id": ids["companies"]})
    assert query(app, "SELECT company_id FROM contacts WHERE first_name='Sly'")[0][0] is None
    rival.post("/deals", data={"csrf": rival.csrf, "title": "Sneaky", "company_id": ids["companies"],
                               "close_date": "2026-12-01"})
    assert not query(app, "SELECT 1 FROM deals WHERE title='Sneaky'")
    rival.post("/tickets", data={"csrf": rival.csrf, "subject": "Sneaky ticket", "contact_id": ids["contacts"],
                                 "company_id": ids["companies"]})
    t = query(app, "SELECT company_id, contact_id, workspace_id FROM tickets WHERE subject='Sneaky ticket'")[0]
    assert (t["company_id"], t["contact_id"], t["workspace_id"]) == (None, None, app.rival_ws)
    rival.post("/engagements", data={"csrf": rival.csrf, "kind": "note", "body": "Planted", "contact_id": ids["contacts"]})
    assert not query(app, "SELECT 1 FROM engagements WHERE body='Planted' AND contact_id IS NOT NULL")


def test_lists_search_and_exports_only_show_own_records(app, rival):
    mine = query(app, "SELECT name FROM companies WHERE workspace_id=? ORDER BY name", app.rival_ws)
    other = {r[0] for r in query(app, "SELECT name FROM companies WHERE workspace_id=?", app.ws)} - {r[0] for r in mine}
    html = rival.get("/companies?sort=name").get_data(as_text=True)
    assert mine[0][0].replace("&", "&amp;") in html
    leaked = [n for n in other if n.replace("&", "&amp;") in html]
    assert not leaked
    # Searching for the other business's records finds nothing of theirs.
    contact = query(app, "SELECT email FROM contacts WHERE workspace_id=? AND email <> '' LIMIT 1", app.ws)[0][0]
    if not query(app, "SELECT 1 FROM contacts WHERE workspace_id=? AND email=?", app.rival_ws, contact):
        assert rival.get(f"/api/search?q={contact}").json == []
    export = rival.get("/export/companies").get_data(as_text=True)
    assert not [n for n in other if n in export]
    rows = query(app, "SELECT COUNT(*) FROM companies WHERE workspace_id=?", app.rival_ws)[0][0]
    assert len(export.strip().splitlines()) == rows + 1


def test_bulk_actions_ignore_other_workspaces_ids(app, rival):
    contact = first_id(app, "contacts", app.ws)
    rival.post("/bulk/contacts", data={"csrf": rival.csrf, "ids": [contact], "action": "delete"})
    rival.post("/bulk/contacts", data={"csrf": rival.csrf, "ids": [contact], "action": "owner", "value": "Rival Admin"})
    row = query(app, "SELECT owner FROM contacts WHERE id=?", contact)
    assert row and row[0][0] != "Rival Admin"


def test_saved_views_and_team_are_private(app, client, rival):
    client.post("/views", data={"csrf": client.csrf, "object": "contacts", "name": "Thistle only",
                                "query": "lifecycle=Lead"})
    view = query(app, "SELECT id FROM saved_views WHERE name='Thistle only'")[0][0]
    assert "Thistle only" not in rival.get("/contacts").get_data(as_text=True)
    assert rival.post(f"/views/{view}/delete", data={"csrf": rival.csrf}).status_code == 404
    team = rival.get("/team").get_data(as_text=True)
    assert "Rival Admin" in team and "Test Admin" not in team and "Test Member" not in team
    member = query(app, "SELECT id FROM users WHERE email='member@example.co.uk'")[0][0]
    assert rival.post(f"/team/{member}/remove", data={"csrf": rival.csrf}).status_code == 404


def test_invoice_numbers_and_settings_are_per_workspace(app, client, rival):
    for c in (client, rival):
        company = first_id(app, "companies", app.ws if c is client else app.rival_ws)
        c.post("/invoices", data={"csrf": c.csrf, "company_id": company, "description": "Work", "net": "100",
                                  "vat_rate": "20"})
    numbers = {r[0]: r[1] for r in query(app, "SELECT workspace_id, MAX(number) FROM invoices GROUP BY workspace_id")}
    assert numbers[app.ws] == numbers[app.rival_ws]  # each business has its own sequence
    rival.post("/settings", data={"csrf": rival.csrf, "name": "Rival Renamed", "legal_name": "Rival Renamed Ltd",
                                  "monthly_target": "50000", "invoice_prefix": "RIV", "payment_terms": "30"})
    assert query(app, "SELECT name FROM workspaces WHERE id=?", app.ws)[0][0] == "Thistle Ltd"
    assert "Thistle Ltd" in client.get("/").get_data(as_text=True)
