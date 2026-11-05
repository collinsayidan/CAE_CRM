"""The sidebar's Support section (Tickets, Knowledge base) and Business section (Documents)."""

import html
import io
import re

from conftest import first_id, query


def nav_sections(page):
    nav = page[page.index('aria-label="Main"'):page.index("</nav>")]
    return re.findall(r'<p class="nav-heading">([^<]+)</p>', nav), nav


def test_the_sidebar_has_support_and_business_sections(client):
    headings, nav = nav_sections(client.get("/").get_data(as_text=True))
    assert headings == ["CRM", "Support", "Sales and finance", "Marketing", "Business"]
    crm = nav[nav.index(">CRM<"):nav.index(">Support<")]
    support = nav[nav.index(">Support<"):nav.index(">Sales and finance<")]
    assert "Deals" in crm and "Tickets" not in crm
    assert "Tickets" in support and "Knowledge base" in support
    assert "Documents" in nav[nav.index(">Business<"):]


def test_help_articles_moved_out_of_settings(client):
    assert "Help articles" not in client.get("/workspace").get_data(as_text=True)
    assert "Help articles" not in client.get("/settings").get_data(as_text=True)
    # The old address still works.
    assert client.get("/settings/help-articles").status_code == 200


def write(client, title, body, published=True):
    data = {"csrf": client.csrf, "title": title, "body": body} | ({"published": "on"} if published else {})
    assert client.post("/knowledge-base/manage", data=data).status_code == 302


def test_everyone_reads_the_knowledge_base_and_admins_write_it(app, client, member_client):
    write(client, "Opening hours", "We're open **9 to 5**, Monday to Friday.")
    write(client, "New price list", "Not ready yet.", published=False)
    live = query(app, "SELECT id FROM help_articles WHERE title='Opening hours'")[0][0]
    draft = query(app, "SELECT id FROM help_articles WHERE title='New price list'")[0][0]

    page = member_client.get("/knowledge-base").get_data(as_text=True)
    assert "Opening hours" in page and "New price list" not in page and "Write an article" not in page
    assert "9 to 5, Monday to Friday." in page and "**" not in page  # the preview is plain text
    article = member_client.get(f"/knowledge-base/{live}").get_data(as_text=True)
    assert "<strong>9 to 5</strong>" in article and "Edit" not in article
    assert member_client.get(f"/knowledge-base/{draft}").status_code == 404
    assert member_client.get("/knowledge-base/manage").status_code == 403

    admin = client.get("/knowledge-base").get_data(as_text=True)
    assert "New price list" in admin and "Draft" in admin and "Write an article" in admin
    assert client.get(f"/knowledge-base/{draft}").status_code == 200
    # Search covers titles and text.
    found = member_client.get("/knowledge-base?q=monday").get_data(as_text=True)
    assert "Opening hours" in found
    assert "Opening hours" not in member_client.get("/knowledge-base?q=refunds").get_data(as_text=True)


def test_knowledge_base_stays_in_its_workspace(app, client, rival):
    write(client, "Opening hours", "9 to 5.")
    a = query(app, "SELECT id FROM help_articles WHERE title='Opening hours'")[0][0]
    assert rival.get(f"/knowledge-base/{a}").status_code == 404
    assert "Opening hours" not in rival.get("/knowledge-base").get_data(as_text=True)


def attach(client, record_type, record_id, name, data=b"%PDF-1.4 test"):
    resp = client.post("/files", data={"csrf": client.csrf, "record_type": record_type, "record_id": record_id,
                                       "next": "/", "file": (io.BytesIO(data), name)}, content_type="multipart/form-data")
    assert resp.status_code == 302


def test_documents_lists_every_attached_file_with_search_and_filters(app, client, member_client):
    company = first_id(app, "companies", app.ws)
    deal = first_id(app, "deals", app.ws)
    attach(client, "company", company, "master-services-agreement.pdf")
    attach(member_client, "deal", deal, "site-photo.jpg", b"\xff\xd8\xff")
    company_name = query(app, "SELECT name FROM companies WHERE id=?", company)[0][0]

    page = client.get("/documents").get_data(as_text=True)
    assert "master-services-agreement.pdf" in page and "site-photo.jpg" in page
    assert f"/companies/{company}" in page and html.escape(company_name) in page

    def shown(**args):
        html = client.get("/documents", query_string=args).get_data(as_text=True)
        return {n for n in ("master-services-agreement.pdf", "site-photo.jpg") if n in html}

    assert shown(q="agreement") == {"master-services-agreement.pdf"}
    assert shown(q=company_name.lower()) >= {"master-services-agreement.pdf"}
    assert shown(record="deal") == {"site-photo.jpg"}
    assert shown(kind="pdf") == {"master-services-agreement.pdf"}
    assert shown(kind="image") == {"site-photo.jpg"}
    assert shown(by="Test Member") == {"site-photo.jpg"}
    # A member can remove their own file here, not someone else's.
    member_page = member_client.get("/documents").get_data(as_text=True)
    assert member_page.count('title="Remove ') == 1


def test_documents_stay_in_their_workspace(app, client, rival):
    attach(client, "company", first_id(app, "companies", app.ws), "secret-contract.pdf")
    assert "secret-contract.pdf" not in rival.get("/documents").get_data(as_text=True)


def test_documents_is_empty_until_something_is_attached(client):
    assert "No documents yet" in client.get("/documents").get_data(as_text=True)
