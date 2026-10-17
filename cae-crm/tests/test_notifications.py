import re

from conftest import ADMIN, MEMBER, first_id, query


def inbox(app, email):
    return query(app, "SELECT n.title, n.url, n.read_at FROM notifications n JOIN users u ON u.id=n.user_id "
                      "WHERE u.email=? ORDER BY n.id", email)


def test_mentions_in_notes_notify_and_are_highlighted(app, client, member_client):
    contact = first_id(app, "contacts", app.ws)
    client.post("/engagements", data={"csrf": client.csrf, "kind": "note", "contact_id": contact,
                                      "body": "Can @Test Member call them back? @Test Admin is away.",
                                      "next": f"/contacts/{contact}"})
    notes = inbox(app, MEMBER[1])
    assert len(notes) == 1 and notes[0][0] == f"{ADMIN[0]} mentioned you in a note" and notes[0][1] == f"/contacts/{contact}"
    assert not inbox(app, ADMIN[1])  # mentioning yourself doesn't notify you
    page = member_client.get(f"/contacts/{contact}").get_data(as_text=True)
    assert '<mark class="mention">@Test Member</mark>' in page


def test_giving_someone_a_task_or_ticket_notifies_them(app, client):
    contact = first_id(app, "contacts", app.ws)
    client.post("/activities", data={"csrf": client.csrf, "kind": "Call", "subject": "Ring back about renewal",
                                     "date": "2026-10-20", "time": "10:00", "owner": MEMBER[0], "contact_id": contact})
    client.post("/tickets", data={"csrf": client.csrf, "subject": "Login problem", "priority": "High", "owner": MEMBER[0],
                                  "contact_id": contact})
    titles = [n[0] for n in inbox(app, MEMBER[1])]
    assert any("gave you a task: Ring back about renewal" in t for t in titles)
    assert any("gave you ticket #" in t and "Login problem" in t for t in titles)
    client.post("/activities", data={"csrf": client.csrf, "kind": "Call", "subject": "My own task",
                                     "date": "2026-10-20", "time": "10:00", "owner": ADMIN[0], "contact_id": contact})
    assert not inbox(app, ADMIN[1])


def test_quote_decisions_and_enquiries_notify_the_owner(app, client):
    app.config["FORM_MIN_SECONDS"] = 0
    deal = query(app, "SELECT d.id FROM deals d WHERE d.workspace_id=? AND d.owner=? AND d.stage NOT IN ('Won','Lost') AND "
                      "EXISTS (SELECT 1 FROM line_items l WHERE l.deal_id=d.id) ORDER BY d.id LIMIT 1", app.ws, ADMIN[0])[0][0]
    client.post(f"/deals/{deal}/quote", data={"csrf": client.csrf})
    quote_id, token = query(app, "SELECT id, token FROM quotes WHERE deal_id=? ORDER BY id DESC", deal)[0]
    client.post(f"/quotes/{quote_id}/send", data={"csrf": client.csrf})
    customer = app.test_client()
    customer.get(f"/q/{token}")
    with customer.session_transaction() as s:
        csrf = s["csrf"]
    customer.post(f"/q/{token}/accept", data={"csrf": csrf, "signer_name": "Jo Bloggs", "agree": "on"})
    client.post("/forms", data={"csrf": client.csrf, "name": "Website enquiries"})
    form_token = query(app, "SELECT token FROM web_forms WHERE workspace_id=? ORDER BY id DESC", app.ws)[0][0]
    v = app.test_client()
    stamp = re.search(r'name="stamp" value="([^"]+)"', v.get(f"/f/{form_token}").get_data(as_text=True)).group(1)
    v.post(f"/f/{form_token}", data={"stamp": stamp, "first_name": "Morag", "last_name": "Campbell",
                                     "email": "morag@example.co.uk", "message": "Hello"})
    titles = [n[0] for n in inbox(app, ADMIN[1])]
    assert any(t.startswith("Quote Q-") and "accepted by Jo Bloggs" in t for t in titles)
    assert "New enquiry from Morag Campbell" in titles


def test_bell_count_opening_and_marking_read(app, client, member_client, rival):
    contact = first_id(app, "contacts", app.ws)
    for n in range(2):
        client.post("/engagements", data={"csrf": client.csrf, "kind": "note", "contact_id": contact,
                                          "body": f"@Test Member note {n}", "next": f"/contacts/{contact}"})
    page = member_client.get("/contacts").get_data(as_text=True)
    assert '<span class="bell-count">2</span>' in page
    first = query(app, "SELECT n.id FROM notifications n JOIN users u ON u.id=n.user_id WHERE u.email=? ORDER BY n.id",
                  MEMBER[1])[0][0]
    assert rival.get(f"/notifications/{first}").status_code == 404
    resp = member_client.get(f"/notifications/{first}")
    assert resp.status_code == 302 and resp.headers["Location"] == f"/contacts/{contact}"
    assert '<span class="bell-count">1</span>' in member_client.get("/contacts").get_data(as_text=True)
    member_client.post("/notifications/read", data={"csrf": member_client.csrf})
    assert 'class="bell-count"' not in member_client.get("/contacts").get_data(as_text=True)


def test_getting_started_checklist(app, client, member_client):
    page = client.get("/").get_data(as_text=True)
    assert "Getting started" in page and "Upload your logo" in page
    assert "Getting started" not in member_client.get("/").get_data(as_text=True)
    client.post("/getting-started/dismiss", data={"csrf": client.csrf})
    assert "Getting started" not in client.get("/").get_data(as_text=True)
