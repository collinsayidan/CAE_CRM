import json

import pytest

from conftest import ADMIN, MEMBER, TODAY, first_id, query
from db import get_db


def run(app, statement, *args):
    with app.app_context():
        get_db().execute(statement, args)
        get_db().commit()


def insert(app, table, **values):
    with app.app_context():
        new_id = get_db().insert(table, **values)
        get_db().commit()
        return new_id


def open_deal(app):
    return first_id(app, "deals", app.ws, "stage NOT IN ('Won','Lost') AND id NOT IN "
                                          "(SELECT deal_id FROM invoices WHERE deal_id IS NOT NULL)")


def make_quiet(app, deal):
    """Nothing logged for a month, no task coming up, and a close date still ahead."""
    run(app, "UPDATE engagements SET occurred_at='2026-09-01T09:00' WHERE deal_id=?", deal)
    run(app, "DELETE FROM activities WHERE deal_id=?", deal)
    run(app, "UPDATE deals SET created_at='2026-08-01', close_date='2026-12-31', owner=?, quiet_since=NULL WHERE id=?",
        ADMIN[0], deal)


# --- Deals gone quiet -------------------------------------------------------------------------------------------------

def test_quiet_deals_are_flagged_until_something_happens(app, client):
    deal = open_deal(app)
    make_quiet(app, deal)
    listing = client.get("/pipeline?view=list&quiet=1").get_data(as_text=True)
    assert f'href="/deals/{deal}"' in listing and "Gone quiet" in listing
    assert "Gone quiet" in client.get(f"/deals/{deal}").get_data(as_text=True)
    client.post("/engagements", data={"csrf": client.csrf, "kind": "note", "deal_id": deal, "body": "Chased by phone"})
    assert f'href="/deals/{deal}"' not in client.get("/pipeline?view=list&quiet=1").get_data(as_text=True)
    run(app, "UPDATE deals SET close_date='2026-10-01' WHERE id=?", deal)  # past its expected close
    assert f'href="/deals/{deal}"' in client.get("/pipeline?view=list&quiet=1").get_data(as_text=True)


def test_owners_are_told_once_by_the_daily_job(app, client):
    app.config["CRON_SECRET"] = "s3cret"
    deal = open_deal(app)
    make_quiet(app, deal)
    cron = app.test_client()
    cron.get("/cron/sync", headers={"Authorization": "Bearer s3cret"})
    cron.get("/cron/sync", headers={"Authorization": "Bearer s3cret"})
    told = query(app, "SELECT n.title FROM notifications n JOIN users u ON u.id=n.user_id WHERE u.email=? AND "
                      "n.title LIKE 'Deal gone quiet%' AND n.url=?", ADMIN[1], f"/deals/{deal}")
    assert len(told) == 1
    client.post("/engagements", data={"csrf": client.csrf, "kind": "note", "deal_id": deal, "body": "Back on track"})
    cron.get("/cron/sync", headers={"Authorization": "Bearer s3cret"})
    assert query(app, "SELECT quiet_since FROM deals WHERE id=?", deal)[0][0] is None


def test_admins_choose_how_many_days(app, client):
    deal = open_deal(app)
    make_quiet(app, deal)
    run(app, "UPDATE engagements SET occurred_at='2026-10-10T09:00' WHERE deal_id=?", deal)  # 6 days ago
    assert f'href="/deals/{deal}"' not in client.get("/pipeline?view=list&quiet=1").get_data(as_text=True)
    form = {"csrf": client.csrf, "name": "Thistle Ltd", "legal_name": "Thistle Ltd", "monthly_target": "100,000",
            "invoice_prefix": "INV", "payment_terms": "30", "vat_registered": "on", "vat_no": "GB123456789",
            "quiet_days": "5"}
    client.post("/settings", data=form)
    assert query(app, "SELECT quiet_days FROM workspaces WHERE id=?", app.ws)[0][0] == 5
    assert f'href="/deals/{deal}"' in client.get("/pipeline?view=list&quiet=1").get_data(as_text=True)


# --- Win and loss reasons ---------------------------------------------------------------------------------------------

def test_losing_a_deal_asks_why(app, client):
    deal = open_deal(app)
    resp = client.post(f"/deals/{deal}/stage", data={"csrf": client.csrf, "stage": "Lost"})
    assert resp.status_code == 302 and f"/deals/{deal}/lost" in resp.headers["Location"]
    assert query(app, "SELECT stage FROM deals WHERE id=?", deal)[0][0] != "Lost"
    fetched = client.post(f"/deals/{deal}/stage", data={"csrf": client.csrf, "stage": "Lost"},
                          headers={"X-Requested-With": "fetch"})
    assert fetched.status_code == 422 and fetched.get_json()["reason_needed"]
    assert "Why was this deal lost?" in client.get(f"/deals/{deal}/lost").get_data(as_text=True)
    assert client.post(f"/deals/{deal}/lost", data={"csrf": client.csrf}).status_code == 422
    client.post(f"/deals/{deal}/lost", data={"csrf": client.csrf, "reason": "Went with a competitor",
                                              "note": "Cheaper quote from Acme"})
    stage, reason, note = query(app, "SELECT stage, outcome_reason, outcome_note FROM deals WHERE id=?", deal)[0]
    assert (stage, reason, note) == ("Lost", "Went with a competitor", "Cheaper quote from Acme")
    body = query(app, "SELECT body FROM engagements WHERE deal_id=? AND subject='Deal lost'", deal)[0][0]
    assert "Went with a competitor" in body and "Acme" in body
    client.post(f"/deals/{deal}/stage", data={"csrf": client.csrf, "stage": "Proposal"})
    assert query(app, "SELECT outcome_reason FROM deals WHERE id=?", deal)[0][0] is None


def test_won_reasons_are_optional_and_reported(app, client):
    deal = open_deal(app)
    client.post(f"/deals/{deal}/stage", data={"csrf": client.csrf, "stage": "Won"})
    assert query(app, "SELECT stage, outcome_reason FROM deals WHERE id=?", deal)[0][0] == "Won"
    client.post(f"/deals/{deal}/reason", data={"csrf": client.csrf, "reason": "Relationship", "note": "Long-time client"})
    assert query(app, "SELECT outcome_reason FROM deals WHERE id=?", deal)[0][0] == "Relationship"
    report = client.get("/reports").get_data(as_text=True)
    assert "Why we win" in report and "Why we lose" in report and "Relationship" in report


# --- Tags -------------------------------------------------------------------------------------------------------------

def test_tagging_filtering_and_bulk(app, client, member_client, rival):
    a, b = (r[0] for r in query(app, "SELECT id FROM contacts WHERE workspace_id=? ORDER BY id LIMIT 2", app.ws))
    member_client.post(f"/tags/contact/{a}", data={"csrf": member_client.csrf, "name": "  VIP  "})
    client.post(f"/tags/contact/{b}", data={"csrf": client.csrf, "name": "vip"})  # same tag, any case
    assert query(app, "SELECT name FROM tags WHERE workspace_id=?", app.ws) == [("VIP",)] or \
        [tuple(r) for r in query(app, "SELECT name FROM tags WHERE workspace_id=?", app.ws)] == [("VIP",)]
    page = client.get("/contacts?tag=VIP").get_data(as_text=True)
    assert f'href="/contacts/{a}"' in page and f'href="/contacts/{b}"' in page
    others = first_id(app, "contacts", app.ws, "id NOT IN (?, ?)", a, b)
    assert f'href="/contacts/{others}"' not in page
    tag = query(app, "SELECT id FROM tags WHERE workspace_id=?", app.ws)[0][0]
    client.post(f"/tags/contact/{a}/remove", data={"csrf": client.csrf, "tag_id": tag})
    assert f'href="/contacts/{a}"' not in client.get("/contacts?tag=VIP").get_data(as_text=True)
    client.post("/bulk/contacts", data={"csrf": client.csrf, "action": "tag_add", "value": "VIP", "ids": [a, others]})
    assert len(query(app, "SELECT 1 FROM record_tags WHERE tag_id=?", tag)) == 3
    client.post("/bulk/contacts", data={"csrf": client.csrf, "action": "tag_remove", "value": "VIP", "ids": [a, b]})
    assert len(query(app, "SELECT 1 FROM record_tags WHERE tag_id=?", tag)) == 1
    # Other businesses can't tag our records or see our tags.
    assert rival.post(f"/tags/contact/{a}", data={"csrf": rival.csrf, "name": "Spy"}).status_code == 404
    assert "VIP" not in rival.get("/contacts").get_data(as_text=True)
    export = client.get("/export/contacts").get_data(as_text=True)
    assert export.splitlines()[0].endswith("Tags") and "VIP" in export


def test_admins_rename_merge_and_delete_tags(app, client, member_client):
    company = first_id(app, "companies", app.ws)
    client.post(f"/tags/company/{company}", data={"csrf": client.csrf, "name": "Trade show"})
    client.post(f"/tags/company/{company}", data={"csrf": client.csrf, "name": "Expo 2026"})
    assert member_client.get("/settings/tags").status_code == 403
    show, expo = (query(app, "SELECT id FROM tags WHERE name=?", n)[0][0] for n in ("Trade show", "Expo 2026"))
    client.post("/settings/tags", data={"csrf": client.csrf, "tag_id": show, "name": "Expo 2026"})  # merges
    assert [r[0] for r in query(app, "SELECT name FROM tags WHERE workspace_id=?", app.ws)] == ["Expo 2026"]
    assert len(query(app, "SELECT 1 FROM record_tags WHERE tag_id=?", expo)) == 1
    client.post("/settings/tags", data={"csrf": client.csrf, "tag_id": expo, "action": "delete"})
    assert not query(app, "SELECT 1 FROM tags WHERE workspace_id=?", app.ws)
    assert "Add a tag" in client.get(f"/companies/{company}").get_data(as_text=True)


# --- Duplicates -------------------------------------------------------------------------------------------------------

def duplicate_contacts(app):
    company = first_id(app, "companies", app.ws)
    common = dict(workspace_id=app.ws, lawful_basis="Contract", created_at="2026-10-01", owner=ADMIN[0])
    keep = insert(app, "contacts", first_name="Morag", last_name="Campbell", email="morag@example.co.uk",
                  company_id=company, marketing_consent=1, consent_date="2026-01-01", **common)
    drop = insert(app, "contacts", first_name="Morag", last_name="Campbell", email="MORAG@example.co.uk",
                  phone="+44 7700 900123", unsubscribed_at="2026-05-01", **common)
    return keep, drop


def test_finding_and_merging_duplicate_contacts(app, client, member_client):
    keep, drop = duplicate_contacts(app)
    deal = open_deal(app)
    run(app, "UPDATE deals SET contact_id=? WHERE id=?", drop, deal)
    insert(app, "engagements", workspace_id=app.ws, kind="note", subject="Old note", author=ADMIN[0],
           occurred_at="2026-09-01T09:00", contact_id=drop)
    assert member_client.get("/duplicates/contacts").status_code == 403
    page = client.get("/duplicates/contacts").get_data(as_text=True)
    assert "the same email" in page and f'name="pair" value="{drop}"' in page
    client.post("/duplicates/contacts/merge", data={"csrf": client.csrf, "keep": keep, "pair": [keep, drop]})
    assert not query(app, "SELECT 1 FROM contacts WHERE id=?", drop)
    phone, consent, unsubscribed = query(app, "SELECT phone, marketing_consent, unsubscribed_at FROM contacts WHERE id=?", keep)[0]
    assert phone == "+44 7700 900123" and consent == 0 and unsubscribed == "2026-05-01"  # the unsubscribe wins
    assert query(app, "SELECT contact_id FROM deals WHERE id=?", deal)[0][0] == keep
    subjects = [r[0] for r in query(app, "SELECT subject FROM engagements WHERE contact_id=?", keep)]
    assert "Old note" in subjects and any(s.startswith("Merged with a duplicate") for s in subjects)


def test_not_duplicates_hides_the_pair_and_rivals_cannot_merge(app, client, rival):
    keep, drop = duplicate_contacts(app)
    assert rival.post("/duplicates/contacts/merge", data={"csrf": rival.csrf, "keep": keep, "pair": [keep, drop]}).status_code == 404
    client.post("/duplicates/contacts/dismiss", data={"csrf": client.csrf, "ids": [keep, drop]})
    assert f'name="pair" value="{drop}"' not in client.get("/duplicates/contacts").get_data(as_text=True)


def test_merging_duplicate_companies(app, client):
    common = dict(workspace_id=app.ws, created_at="2026-10-01", postcode="EH2 2AN")
    keep = insert(app, "companies", name="Bramble & Oak Ltd", **common)
    drop = insert(app, "companies", name="Bramble and Oak Limited", website="https://www.brambleoak.co.uk", **common)
    person = insert(app, "contacts", workspace_id=app.ws, first_name="Ada", last_name="Brown", lawful_basis="Contract",
                    created_at="2026-10-01", company_id=drop)
    page = client.get("/duplicates/companies").get_data(as_text=True)
    assert "the same name" in page
    client.post("/duplicates/companies/merge", data={"csrf": client.csrf, "keep": keep, "pair": [keep, drop]})
    assert query(app, "SELECT company_id FROM contacts WHERE id=?", person)[0][0] == keep
    assert query(app, "SELECT website FROM companies WHERE id=?", keep)[0][0] == "https://www.brambleoak.co.uk"


# --- Companies House --------------------------------------------------------------------------------------------------

class FakeRegister:
    def __init__(self):
        self.calls = []

    def request(self, path, params):
        self.calls.append((path, params))
        if path == "/search/companies":
            return {"items": [{"title": "BRAMBLE & OAK LTD", "company_number": "SC512345", "company_status": "active",
                               "address_snippet": "1 George St, Edinburgh, EH2 2AN",
                               "address": {"premises": "1", "address_line_1": "George Street", "locality": "Edinburgh",
                                           "postal_code": "EH2 2AN"}}]}
        if path == "/company/SC512345":
            return {"company_name": "BRAMBLE & OAK LTD", "company_number": "SC512345", "company_status": "liquidation",
                    "sic_codes": ["62020", "70229"],
                    "registered_office_address": {"premises": "1", "address_line_1": "George Street",
                                                  "locality": "Edinburgh", "postal_code": "EH2 2AN"}}
        return None


def test_companies_house_is_hidden_without_a_key(app, client):
    assert client.get("/companies-house/search?q=bramble").status_code == 404
    assert "data-ch-lookup" not in client.get("/companies").get_data(as_text=True)


def test_companies_house_search_and_refresh(app, client):
    register = FakeRegister()
    app.config["CH_BACKEND"] = register
    assert "data-ch-lookup" in client.get("/companies").get_data(as_text=True)
    (found,) = client.get("/companies-house/search?q=bramble").get_json()["results"]
    assert found["number"] == "SC512345" and found["address"] == "1 George Street" and found["postcode"] == "EH2 2AN"
    company = first_id(app, "companies", app.ws)
    run(app, "UPDATE companies SET company_no='SC512345', address=NULL WHERE id=?", company)
    client.post(f"/companies/{company}/companies-house", data={"csrf": client.csrf})
    status, sic, address = query(app, "SELECT ch_status, ch_sic, address FROM companies WHERE id=?", company)[0]
    assert (status, sic, address) == ("liquidation", "62020, 70229", "1 George Street")
    page = client.get(f"/companies/{company}").get_data(as_text=True)
    assert "In liquidation" in page
    assert query(app, "SELECT 1 FROM engagements WHERE company_id=? AND subject LIKE 'Companies House status%'", company)
    run(app, "UPDATE companies SET company_no='99999999' WHERE id=?", company)
    client.post(f"/companies/{company}/companies-house", data={"csrf": client.csrf})
    assert query(app, "SELECT ch_status FROM companies WHERE id=?", company)[0][0] == "not-found"


# --- Recycle bin ------------------------------------------------------------------------------------------------------

def test_deleting_and_restoring_a_company(app, client):
    company = first_id(app, "companies", app.ws, "id NOT IN (SELECT company_id FROM invoices) AND "
                                                 "id IN (SELECT company_id FROM deals) AND id IN (SELECT company_id FROM contacts)")
    people = sorted(r[0] for r in query(app, "SELECT id FROM contacts WHERE company_id=?", company))
    deals = query(app, "SELECT COUNT(*) FROM deals WHERE company_id=?", company)[0][0]
    lines = query(app, "SELECT COUNT(*) FROM line_items WHERE deal_id IN (SELECT id FROM deals WHERE company_id=?)", company)[0][0]
    client.post(f"/tags/company/{company}", data={"csrf": client.csrf, "name": "Key account"})
    client.post(f"/companies/{company}/delete", data={"csrf": client.csrf})
    assert not query(app, "SELECT 1 FROM companies WHERE id=?", company)
    assert all(query(app, "SELECT company_id FROM contacts WHERE id=?", p)[0][0] is None for p in people)
    (entry,) = query(app, "SELECT id, label FROM recycle_bin WHERE workspace_id=?", app.ws)
    assert client.get("/settings/recycle-bin").status_code == 200
    resp = client.post(f"/settings/recycle-bin/{entry[0]}/restore", data={"csrf": client.csrf})
    assert resp.status_code == 302
    new_id = query(app, "SELECT id FROM companies WHERE workspace_id=? AND name=?", app.ws, entry[1])[0][0]
    assert sorted(r[0] for r in query(app, "SELECT id FROM contacts WHERE company_id=?", new_id)) == people
    assert query(app, "SELECT COUNT(*) FROM deals WHERE company_id=?", new_id)[0][0] == deals
    assert query(app, "SELECT COUNT(*) FROM line_items WHERE deal_id IN (SELECT id FROM deals WHERE company_id=?)",
                 new_id)[0][0] == lines
    assert "Key account" in client.get(f"/companies/{new_id}").get_data(as_text=True)
    assert not query(app, "SELECT 1 FROM recycle_bin WHERE workspace_id=?", app.ws)


def test_restoring_a_deal_and_a_contact(app, client):
    deal = open_deal(app)
    contact = query(app, "SELECT contact_id FROM deals WHERE id=?", deal)[0][0]
    client.post("/bulk/contacts", data={"csrf": client.csrf, "action": "delete", "ids": [contact]})
    assert query(app, "SELECT contact_id FROM deals WHERE id=?", deal)[0][0] is None
    client.post(f"/deals/{deal}/delete", data={"csrf": client.csrf})
    entries = {r[1]: r[0] for r in query(app, "SELECT id, record_type FROM recycle_bin WHERE workspace_id=?", app.ws)}
    client.post(f"/settings/recycle-bin/{entries['deal']}/restore", data={"csrf": client.csrf})
    client.post(f"/settings/recycle-bin/{entries['contact']}/restore", data={"csrf": client.csrf})
    restored_contact = query(app, "SELECT MAX(id) FROM contacts WHERE workspace_id=?", app.ws)[0][0]
    restored_deal = query(app, "SELECT MAX(id) FROM deals WHERE workspace_id=?", app.ws)[0][0]
    assert query(app, "SELECT contact_id FROM deals WHERE id=?", restored_deal)[0][0] == restored_contact


def test_a_deal_waits_for_its_company(app, client):
    company = first_id(app, "companies", app.ws, "id NOT IN (SELECT company_id FROM invoices) AND "
                                                 "id IN (SELECT company_id FROM deals WHERE id NOT IN "
                                                 "(SELECT deal_id FROM invoices WHERE deal_id IS NOT NULL))")
    deal = first_id(app, "deals", app.ws, "company_id=?", company)
    client.post(f"/deals/{deal}/delete", data={"csrf": client.csrf})
    client.post(f"/companies/{company}/delete", data={"csrf": client.csrf})
    deal_entry = query(app, "SELECT id FROM recycle_bin WHERE record_type='deal'")[0][0]
    client.post(f"/settings/recycle-bin/{deal_entry}/restore", data={"csrf": client.csrf})
    assert "first" in client.get("/settings/recycle-bin").get_data(as_text=True)
    assert query(app, "SELECT 1 FROM recycle_bin WHERE id=?", deal_entry)
    # Once the company is back (with a new id), the deal follows it.
    company_entry = query(app, "SELECT id FROM recycle_bin WHERE record_type='company'")[0][0]
    client.post(f"/settings/recycle-bin/{company_entry}/restore", data={"csrf": client.csrf})
    client.post(f"/settings/recycle-bin/{deal_entry}/restore", data={"csrf": client.csrf})
    new_company = query(app, "SELECT MAX(id) FROM companies WHERE workspace_id=?", app.ws)[0][0]
    new_deal = query(app, "SELECT MAX(id) FROM deals WHERE workspace_id=?", app.ws)[0][0]
    assert query(app, "SELECT company_id FROM deals WHERE id=?", new_deal)[0][0] == new_company
    assert not query(app, "SELECT 1 FROM recycle_bin WHERE workspace_id=?", app.ws)


def test_the_bin_is_private_and_emptied_after_30_days(app, client, member_client, rival):
    app.config["CRON_SECRET"] = "s3cret"
    ticket = first_id(app, "tickets", app.ws)
    client.post("/bulk/tickets", data={"csrf": client.csrf, "action": "delete", "ids": [ticket]})
    entry = query(app, "SELECT id FROM recycle_bin")[0][0]
    assert member_client.get("/settings/recycle-bin").status_code == 403
    assert rival.post(f"/settings/recycle-bin/{entry}/restore", data={"csrf": rival.csrf}).status_code == 404
    run(app, "UPDATE recycle_bin SET deleted_at='2026-09-01T09:00'")
    out = app.test_client().get("/cron/sync", headers={"Authorization": "Bearer s3cret"}).get_json()
    assert out["recycle_bin_emptied"] == 1 and not query(app, "SELECT 1 FROM recycle_bin")


def test_deleting_permanently(app, client):
    contact = first_id(app, "contacts", app.ws)
    client.post("/bulk/contacts", data={"csrf": client.csrf, "action": "delete", "ids": [contact]})
    entry = query(app, "SELECT id, snapshot FROM recycle_bin")[0]
    assert json.loads(entry[1])["rows"]["contacts"][0]["id"] == contact
    client.post(f"/settings/recycle-bin/{entry[0]}/delete", data={"csrf": client.csrf})
    assert not query(app, "SELECT 1 FROM recycle_bin")
