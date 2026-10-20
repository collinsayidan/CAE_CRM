import pytest

import legal
from conftest import make_app, query, refresh_csrf

SIGNUP = {"business": "Bramble & Oak Ltd", "name": "Ada Lovelace", "email": "ada@example.co.uk",
          "password": "analytical engine", "confirm": "analytical engine"}


@pytest.mark.parametrize("doc", list(legal.DOCS))
def test_legal_pages_are_public_and_flag_what_needs_confirming(anon, doc):
    page = anon.get(f"/legal/{doc}").get_data(as_text=True)
    assert legal.DOCS[doc] in page and f"Version {legal.VERSION}" in page
    assert "This document is being reviewed by a solicitor" in page
    assert '<mark class="to-confirm">[to confirm: ' in page  # missing company details are flagged, never made up
    assert "Collinalitics Ltd" in page


def test_details_from_settings_and_the_reviewed_switch(app, anon):
    app.config.update(LEGAL_COMPANY_NUMBER="12345678", LEGAL_ADDRESS="1 High Street, Edinburgh EH1 1AA",
                      LEGAL_ICO_NUMBER="ZA123456", LEGAL_EMAIL="privacy@example.co.uk", LEGAL_LAW="Scotland",
                      LEGAL_DATA_REGION="London (eu-west-2)", LEGAL_REVIEWED=True)
    page = anon.get("/legal/privacy").get_data(as_text=True)
    assert "ZA123456" in page and "London (eu-west-2)" in page and "privacy@example.co.uk" in page
    assert "being reviewed by a solicitor" not in page and "to confirm: ICO" not in page
    assert "The law of Scotland applies" in anon.get("/legal/terms").get_data(as_text=True)
    app.config["LEGAL_ADDRESS"] = "<script>alert(1)</script>"
    assert "<script>alert(1)" not in anon.get("/legal/terms").get_data(as_text=True)
    assert anon.get("/legal/nonsense").status_code == 404


def test_links_from_public_pages(anon):
    for path in ("/welcome", "/login", "/signup", "/legal"):
        page = anon.get(path).get_data(as_text=True)
        assert 'href="/legal/terms"' in page and 'href="/legal/privacy"' in page, path


def test_signing_up_records_the_terms_agreed(database):
    app = make_app(database)
    c = app.test_client()
    page = c.get("/signup").get_data(as_text=True)
    assert "you agree to the" in page and 'href="/legal/dpa"' in page
    refresh_csrf(c)
    assert c.post("/signup", data=SIGNUP | {"csrf": c.csrf}).status_code == 302
    (version, at, by), = query(app, "SELECT terms_version, terms_accepted_at, terms_accepted_by FROM workspaces")
    assert version == legal.VERSION and at and by == "Ada Lovelace <ada@example.co.uk>"
    index = c.get("/legal").get_data(as_text=True)
    assert f"agreed to version {legal.VERSION}" in index and "Ada Lovelace" in index


def test_settings_links_to_legal_pages_for_everyone(client, member_client):
    for c in (client, member_client):
        assert "Legal and privacy" in c.get("/workspace").get_data(as_text=True)
    assert "set up before acceptance of the terms was recorded" in client.get("/legal").get_data(as_text=True)
    assert "set up before acceptance" not in member_client.get("/legal").get_data(as_text=True)


def test_hosting_provider_is_named_correctly(anon):
    for doc in ("privacy", "dpa"):
        page = anon.get(f"/legal/{doc}").get_data(as_text=True)
        assert "Hetzner Online GmbH" in page and "Vercel" not in page, doc
