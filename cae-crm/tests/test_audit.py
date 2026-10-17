from conftest import ADMIN, first_id, login, query


def trail(app, ws):
    return query(app, "SELECT action, target_type, target_id, summary, user_name FROM audit_events WHERE workspace_id=? "
                      "ORDER BY id", ws)


def test_changes_and_sign_ins_are_recorded(app, client):
    actions = [r[0] for r in trail(app, app.ws)]
    assert "Signed in" in actions
    client.post("/contacts", data={"csrf": client.csrf, "first_name": "Ada", "last_name": "Byron", "lawful_basis": "Contract"})
    last = trail(app, app.ws)[-1]
    assert last[0] == "Added a contact" and last[4] == ADMIN[0]


def test_deleted_records_keep_their_name_in_the_trail(app, client):
    deal = first_id(app, "deals", app.ws, "id NOT IN (SELECT deal_id FROM invoices WHERE deal_id IS NOT NULL)")
    title = query(app, "SELECT title FROM deals WHERE id=?", deal)[0][0]
    client.post(f"/deals/{deal}/delete", data={"csrf": client.csrf})
    action, kind, target_id, summary, _ = trail(app, app.ws)[-1]
    assert (action, kind, target_id, summary) == ("Deleted a deal", "Deal", deal, title)


def test_erased_contacts_leave_no_name(app, client):
    contact = first_id(app, "contacts", app.ws)
    name = query(app, "SELECT first_name || ' ' || last_name FROM contacts WHERE id=?", contact)[0][0]
    client.post(f"/contacts/{contact}/erase", data={"csrf": client.csrf})
    action, kind, target_id, summary, _ = trail(app, app.ws)[-1]
    assert (action, kind, target_id, summary) == ("Erased a contact's personal data", "Contact", contact, None)
    assert not any(name in (r[3] or "") for r in trail(app, app.ws))


def test_failed_changes_are_not_recorded(app, client):
    before = len(trail(app, app.ws))
    client.post("/contacts", data={"csrf": client.csrf, "first_name": "", "last_name": "", "lawful_basis": "Nope"})
    client.post("/team", data={"csrf": client.csrf, "name": "", "email": "bad", "password": "x"})
    assert len(trail(app, app.ws)) == before


def test_only_admins_see_the_trail_and_only_their_own(app, client, member_client, rival):
    assert member_client.get("/audit").status_code == 403
    page = client.get("/audit").get_data(as_text=True)
    assert "Signed in" in page and "Rival Admin" not in page
    csv = client.get("/audit?format=csv")
    assert csv.mimetype == "text/csv" and "Signed in" in csv.get_data(as_text=True)
    assert "Test Admin" not in rival.get("/audit").get_data(as_text=True)
