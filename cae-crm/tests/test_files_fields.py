import io
import json

from conftest import MEMBER, first_id, query


def attach(c, record_type, record_id, name="contract.pdf", data=b"%PDF-1.4 test", next_url="/contacts"):
    return c.post("/files", data={"csrf": c.csrf, "record_type": record_type, "record_id": record_id, "next": next_url,
                                  "file": (io.BytesIO(data), name)}, content_type="multipart/form-data")


def attachments(app, ws_id):
    return query(app, "SELECT id, record_type, record_id, filename, uploaded_by FROM attachments WHERE workspace_id=? "
                      "ORDER BY id", ws_id)


def flashes(c, category=None):
    with c.session_transaction() as s:
        return [m for cat, m in s.get("_flashes", []) if category in (None, cat)]


def test_attach_download_and_remove_a_file(app, client, member_client):
    contact = first_id(app, "contacts", app.ws)
    resp = attach(member_client, "contact", contact, next_url=f"/contacts/{contact}")
    assert resp.status_code == 302 and resp.headers["Location"] == f"/contacts/{contact}"
    (file_id, kind, rid, name, by), = attachments(app, app.ws)
    assert (kind, rid, name, by) == ("contact", contact, "contract.pdf", MEMBER[0])
    page = member_client.get(f"/contacts/{contact}").get_data(as_text=True)
    assert "contract.pdf" in page and f"/files/{file_id}" in page
    got = client.get(f"/files/{file_id}")
    assert got.data == b"%PDF-1.4 test"
    assert got.headers["Content-Disposition"].startswith("attachment;") and got.headers["X-Content-Type-Options"] == "nosniff"
    # Someone else's file can be removed by an admin, not by another member.
    attach(client, "contact", contact, name="admin-notes.txt", data=b"notes")
    admins_file = attachments(app, app.ws)[-1][0]
    assert member_client.post(f"/files/{admins_file}/delete", data={"csrf": member_client.csrf}).status_code == 403
    member_client.post(f"/files/{file_id}/delete", data={"csrf": member_client.csrf})
    client.post(f"/files/{admins_file}/delete", data={"csrf": client.csrf})
    assert attachments(app, app.ws) == []
    actions = [r[0] for r in query(app, "SELECT action FROM audit_events WHERE workspace_id=?", app.ws)]
    assert "Attached a file" in actions and "Removed a file" in actions


def test_risky_types_and_big_files_are_refused(app, client):
    deal = first_id(app, "deals", app.ws)
    for name in ("setup.exe", "page.html", "script.js", "noextension"):
        attach(client, "deal", deal, name=name)
    attach(client, "deal", deal, name="huge.pdf", data=b"x" * (4 * 1024 * 1024 + 1))
    assert attachments(app, app.ws) == []
    messages = flashes(client, "error")
    assert any("can't be attached" in m for m in messages) and any("over 4 MB" in m for m in messages)
    # A path in the name is stripped to the file name itself.
    attach(client, "deal", deal, name="..\\..\\quote.pdf")
    assert attachments(app, app.ws)[-1][3] == "quote.pdf"


def test_files_stay_inside_their_business(app, client, rival):
    contact = first_id(app, "contacts", app.ws)
    assert attach(rival, "contact", contact).status_code == 404
    assert attach(client, "nonsense", contact).status_code == 404
    attach(client, "contact", contact)
    file_id = attachments(app, app.ws)[0][0]
    assert rival.get(f"/files/{file_id}").status_code == 404
    assert rival.post(f"/files/{file_id}/delete", data={"csrf": rival.csrf}).status_code == 404
    assert len(attachments(app, app.ws)) == 1


def test_erasing_or_deleting_a_record_removes_its_files(app, client):
    contact = first_id(app, "contacts", app.ws)
    deal = first_id(app, "deals", app.ws, "id NOT IN (SELECT deal_id FROM invoices WHERE deal_id IS NOT NULL)")
    attach(client, "contact", contact, name="passport-scan.jpg", data=b"\xff\xd8")
    attach(client, "deal", deal, name="po.pdf")
    client.post(f"/contacts/{contact}/erase", data={"csrf": client.csrf})
    client.post(f"/deals/{deal}/delete", data={"csrf": client.csrf})
    assert attachments(app, app.ws) == []
    ticket = first_id(app, "tickets", app.ws)
    attach(client, "ticket", ticket, name="screenshot.png", data=b"\x89PNG")
    client.post("/bulk/tickets", data={"csrf": client.csrf, "action": "delete", "ids": [ticket]})
    assert attachments(app, app.ws) == []
    assert not query(app, "SELECT 1 FROM tickets WHERE id=?", ticket)


def test_admin_adds_custom_fields_and_members_cannot(app, client, member_client):
    assert member_client.get("/custom-fields").status_code == 403
    assert member_client.post("/custom-fields", data={"csrf": member_client.csrf, "object": "contacts", "label": "X",
                                                      "field_type": "text"}).status_code == 403
    client.post("/custom-fields", data={"csrf": client.csrf, "object": "contacts", "label": "Tier", "field_type": "choice",
                                        "options": "Bronze"})
    assert query(app, "SELECT COUNT(*) FROM custom_fields")[0][0] == 0  # a dropdown needs two options
    client.get("/custom-fields")  # show, and so clear, the error
    client.post("/custom-fields", data={"csrf": client.csrf, "object": "contacts", "label": "Tier", "field_type": "choice",
                                        "options": "Bronze, Silver, Gold"})
    client.post("/custom-fields", data={"csrf": client.csrf, "object": "deals", "label": "PO number", "field_type": "text"})
    page = client.get("/custom-fields").get_data(as_text=True)
    assert "Tier" in page and "Bronze, Silver, Gold" in page and "PO number" in page
    assert query(app, "SELECT action FROM audit_events WHERE action='Added a custom field'")


def add_contact_fields(app, client):
    for label, kind, options in (("Tier", "choice", "Bronze, Silver, Gold"), ("Renewal", "date", ""),
                                 ("Seats", "number", ""), ("VIP", "yes_no", "")):
        client.post("/custom-fields", data={"csrf": client.csrf, "object": "contacts", "label": label, "field_type": kind,
                                            "options": options})
    return {r[1]: r[0] for r in query(app, "SELECT id, label FROM custom_fields WHERE workspace_id=?", app.ws)}


def edit_contact(c, contact, **custom):
    data = {"csrf": c.csrf, "first_name": "Grace", "last_name": "Hopper", "lawful_basis": "Consent", "cf_present": "1"}
    data.update(custom)
    return c.post(f"/contacts/{contact}/edit", data=data)


def saved_custom(app, contact):
    return json.loads(query(app, "SELECT custom FROM contacts WHERE id=?", contact)[0][0] or "{}")


def test_custom_values_are_saved_shown_and_exported(app, client):
    ids = add_contact_fields(app, client)
    contact = first_id(app, "contacts", app.ws)
    page = client.get(f"/contacts/{contact}").get_data(as_text=True)
    assert f'name="cf_{ids["Tier"]}"' in page and 'name="cf_present"' in page
    edit_contact(client, contact, **{f"cf_{ids['Tier']}": "Gold", f"cf_{ids['Renewal']}": "2027-03-31",
                                     f"cf_{ids['Seats']}": "1,200", f"cf_{ids['VIP']}": "on"})
    assert saved_custom(app, contact) == {str(ids["Tier"]): "Gold", str(ids["Renewal"]): "2027-03-31",
                                          str(ids["Seats"]): 1200, str(ids["VIP"]): True}
    page = client.get(f"/contacts/{contact}").get_data(as_text=True)
    assert "31/03/2027" in page and "Gold" in page
    header, *lines = client.get("/export/contacts").get_data(as_text=True).splitlines()
    assert header.endswith("Tier,Renewal,Seats,VIP")
    assert any(line.endswith("Gold,31/03/2027,1200,Yes") for line in lines)


def test_bad_values_are_flagged_and_other_posts_leave_fields_alone(app, client):
    ids = add_contact_fields(app, client)
    contact = first_id(app, "contacts", app.ws)
    edit_contact(client, contact, **{f"cf_{ids['VIP']}": "on", f"cf_{ids['Seats']}": "lots", f"cf_{ids['Tier']}": "Platinum"})
    assert any("Seats must be a number" in m and "Tier" in m for m in flashes(client, "error"))
    saved = saved_custom(app, contact)
    assert saved[str(ids["VIP"])] is True and str(ids["Seats"]) not in saved
    client.get("/")  # clear the flashed messages
    # A post to the same page without the Edit window's fields changes nothing.
    client.post(f"/contacts/{contact}/edit", data={"csrf": client.csrf, "first_name": "Grace", "last_name": "Hopper",
                                                   "lawful_basis": "Consent"})
    assert saved_custom(app, contact)[str(ids["VIP"])] is True
    # A failed edit saves nothing.
    edit_contact(client, contact, first_name="")
    assert saved_custom(app, contact)[str(ids["VIP"])] is True


def test_custom_fields_belong_to_one_business(app, client, rival):
    ids = add_contact_fields(app, client)
    assert "Tier" not in rival.get("/custom-fields").get_data(as_text=True)
    rival.post(f"/custom-fields/{ids['Tier']}/delete", data={"csrf": rival.csrf})
    assert query(app, "SELECT COUNT(*) FROM custom_fields WHERE workspace_id=?", app.ws)[0][0] == 4
    client.post(f"/custom-fields/{ids['Tier']}/delete", data={"csrf": client.csrf})
    assert query(app, "SELECT COUNT(*) FROM custom_fields WHERE workspace_id=?", app.ws)[0][0] == 3
