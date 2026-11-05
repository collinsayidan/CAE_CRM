"""Accessibility basics from the November 2026 site audit, checked on every page kind that has them."""


def test_every_signed_in_page_has_a_skip_link_and_unique_landmarks(client):
    for path in ("/", "/contacts", "/settings"):
        page = client.get(path).get_data(as_text=True)
        assert '<a class="skip-link" href="#content">Skip to main content</a>' in page, path
        assert '<main id="content" tabindex="-1">' in page, path
        assert 'aria-label="Sidebar"' in page and 'aria-label="Admin"' in page, path
    assert 'aria-label="Settings sections"' in client.get("/settings").get_data(as_text=True)


def test_record_side_columns_are_named(app, client):
    from conftest import first_id
    for kind, path in (("contacts", "/contacts/{}"), ("companies", "/companies/{}"), ("deals", "/deals/{}"),
                       ("tickets", "/tickets/{}")):
        page = client.get(path.format(first_id(app, kind, app.ws))).get_data(as_text=True)
        assert '<aside class="record-left" aria-label="Record details">' in page, kind


def test_tables_have_no_empty_header_cells(client):
    for path in ("/documents", "/products", "/invoices/recurring", "/settings/recycle-bin", "/settings/tags"):
        resp = client.get(path)
        assert resp.status_code == 200 and "<th" in resp.get_data(as_text=True), path
        assert "<th></th>" not in resp.get_data(as_text=True), path
