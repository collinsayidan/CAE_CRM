import pytest


@pytest.mark.parametrize("path", ["/", "/?span=6m", "/pipeline", "/customers", "/customers/1", "/schedule",
                                  "/finance", "/finance?status=Overdue", "/invoices/1", "/growth", "/projects"])
def test_pages_render(client, path):
    resp = client.get(path)
    assert resp.status_code == 200
    assert "£" in resp.get_data(as_text=True) or path.startswith("/schedule") or path.startswith("/projects")


def test_overview_has_dashboard_sections(client):
    html = client.get("/").get_data(as_text=True)
    for text in ("Won this month", "Open pipeline", "Hot deals", "Stage mix", "FY2026/27 Q3", "<svg"):
        assert text in html


def test_post_without_csrf_is_rejected(client):
    assert client.post("/deals", data={"title": "x"}).status_code == 400


def test_create_deal_and_win_it(client, app):
    resp = client.post("/deals", data={"csrf": client.csrf, "title": "Test rollout", "company_id": "1",
                                       "value": "£12,345", "close_date": "2026-11-30", "stage": "Proposal"})
    assert resp.status_code == 302
    with app.app_context():
        from db import get_db
        deal = get_db().execute("SELECT * FROM deals WHERE title='Test rollout'").fetchone()
        assert deal["value"] == 1_234_500 and deal["probability"] == 50
    client.post(f"/deals/{deal['id']}/stage", data={"csrf": client.csrf, "stage": "Won"})
    with app.app_context():
        from db import get_db
        db = get_db()
        assert db.execute("SELECT closed_at FROM deals WHERE id=?", (deal["id"],)).fetchone()[0] == "2026-10-17"
        assert db.execute("SELECT COUNT(*) FROM projects WHERE deal_id=?", (deal["id"],)).fetchone()[0] == 1


def test_create_company_validates_uk_fields(client):
    resp = client.post("/customers", data={"csrf": client.csrf, "name": "Acme", "postcode": "NOPE",
                                           "vat_no": "12", "company_no": ""})
    html = resp.get_data(as_text=True)
    assert resp.status_code == 422
    assert "valid UK postcode" in html and "GB123456789" in html

    resp = client.post("/customers", data={"csrf": client.csrf, "name": "Acme Ltd", "postcode": "sw1a1aa",
                                           "vat_no": "GB123456789", "company_no": "1234567"})
    assert resp.status_code == 302
    page = client.get(resp.headers["Location"]).get_data(as_text=True)
    assert "SW1A 1AA" in page and "01234567" in page


def test_contact_gdpr_export_and_erase(client):
    resp = client.post("/customers/1/contacts", data={"csrf": client.csrf, "first_name": "Ada", "last_name": "Lovelace",
                                                      "email": "ada@example.co.uk", "phone": "07700 900001",
                                                      "lawful_basis": "Consent", "marketing_consent": "on"})
    assert resp.status_code == 302
    page = client.get("/customers/1").get_data(as_text=True)
    assert "Ada Lovelace" in page and "+44 7700 900001" in page and "Marketing opt-in 17/10/2026" in page

    import re
    contact_id = re.findall(r"/contacts/(\d+)/export", page)[-1]
    export = client.get(f"/contacts/{contact_id}/export")
    assert export.json["data_subject"]["email"] == "ada@example.co.uk"
    client.post(f"/contacts/{contact_id}/erase", data={"csrf": client.csrf})
    assert "Ada Lovelace" not in client.get("/customers/1").get_data(as_text=True)


def test_invoice_vat_and_payment(client, app):
    client.post("/invoices", data={"csrf": client.csrf, "company_id": "2", "description": "Consulting",
                                   "net": "1,000.00", "vat_rate": "20"})
    with app.app_context():
        from db import get_db
        inv = get_db().execute("SELECT * FROM invoices ORDER BY id DESC LIMIT 1").fetchone()
    assert (inv["net"], inv["vat"], inv["due_date"]) == (100_000, 20_000, "2026-11-16")
    assert "£1,200.00" in client.get(f"/invoices/{inv['id']}").get_data(as_text=True)
    client.post(f"/invoices/{inv['id']}/paid", data={"csrf": client.csrf})
    with app.app_context():
        from db import get_db
        assert get_db().execute("SELECT paid_date FROM invoices WHERE id=?", (inv["id"],)).fetchone()[0] == "2026-10-17"


def test_activity_and_project_updates(client):
    assert client.post("/activities", data={"csrf": client.csrf, "kind": "Call", "subject": "Ring the FD",
                                            "date": "2026-10-20", "time": "14:30"}).status_code == 302
    assert "Ring the FD" in client.get("/schedule").get_data(as_text=True)
    assert client.post("/projects/1", data={"csrf": client.csrf, "progress": "100", "status": "On track"}).status_code == 302


def test_open_redirect_blocked(client):
    resp = client.post("/activities/1/toggle", data={"csrf": client.csrf, "next": "//evil.example"})
    assert resp.headers["Location"].endswith("/schedule")
