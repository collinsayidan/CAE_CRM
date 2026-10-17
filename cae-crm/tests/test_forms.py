import re

import pytest

from conftest import query

ENQUIRY = {"first_name": "Morag", "last_name": "Campbell", "email": "Morag@Example.co.uk", "phone": "0131 496 0000",
           "company": "Heather Hill Ltd", "message": "Can you quote for 20 seats?"}


@pytest.fixture
def form(app, client):
    app.config["FORM_MIN_SECONDS"] = 0
    client.post("/forms", data={"csrf": client.csrf, "name": "Website enquiries"})
    return query(app, "SELECT id, token FROM web_forms WHERE workspace_id=?", app.ws)[0]


def submit(app, token, ip="198.51.100.7", **changes):
    """Fill in the public form as a website visitor would: no sign-in, no CSRF token."""
    c = app.test_client()
    page = c.get(f"/f/{token}").get_data(as_text=True)
    stamp = re.search(r'name="stamp" value="([^"]+)"', page).group(1)
    return c.post(f"/f/{token}", data={"stamp": stamp, **ENQUIRY, **changes}, headers={"X-Real-IP": ip})


def test_submission_creates_a_contact_company_task_and_timeline_entry(app, form):
    resp = submit(app, form[1], marketing_consent="on")
    assert resp.status_code == 200 and "Thank you" in resp.get_data(as_text=True)
    c = query(app, "SELECT id, lawful_basis, marketing_consent, consent_date, lifecycle_stage, company_id, phone "
                   "FROM contacts WHERE workspace_id=? AND email='morag@example.co.uk'", app.ws)
    assert len(c) == 1
    contact_id, basis, consent, consent_date, stage, company_id, phone = c[0]
    assert (basis, consent, stage, phone) == ("Legitimate interests", 1, "Lead", "+44 1314 960000")
    assert consent_date and company_id
    assert query(app, "SELECT name FROM companies WHERE id=?", company_id)[0][0] == "Heather Hill Ltd"
    assert query(app, "SELECT COUNT(*) FROM form_submissions WHERE contact_id=?", contact_id)[0][0] == 1
    assert query(app, "SELECT COUNT(*) FROM activities WHERE contact_id=? AND done=0", contact_id)[0][0] == 1
    assert query(app, "SELECT body FROM engagements WHERE contact_id=? AND subject LIKE 'Submitted the form%'",
                 contact_id)[0][0].startswith("Can you quote")


def test_repeat_visitor_is_matched_by_email_not_duplicated(app, form):
    submit(app, form[1])
    submit(app, form[1], email="morag@example.co.uk", marketing_consent="on", message="Following up")
    rows = query(app, "SELECT id, marketing_consent FROM contacts WHERE workspace_id=? AND email='morag@example.co.uk'", app.ws)
    assert len(rows) == 1 and rows[0][1] == 1
    assert query(app, "SELECT COUNT(*) FROM form_submissions WHERE contact_id=?", rows[0][0])[0][0] == 2
    assert query(app, "SELECT COUNT(*) FROM companies WHERE workspace_id=? AND name='Heather Hill Ltd'", app.ws)[0][0] == 1


def test_spam_and_bad_input_are_turned_away(app, form):
    before = query(app, "SELECT COUNT(*) FROM contacts WHERE workspace_id=?", app.ws)[0][0]
    assert submit(app, form[1], website="http://spam.example").status_code == 422  # honeypot
    assert submit(app, form[1], stamp="forged").status_code == 422
    resp = submit(app, form[1], email="not-an-email", message="")
    assert resp.status_code == 422
    page = resp.get_data(as_text=True)
    assert "Enter an email address" in page and "Enter your message" in page
    assert query(app, "SELECT COUNT(*) FROM contacts WHERE workspace_id=?", app.ws)[0][0] == before


def test_one_address_is_rate_limited(app, form):
    for n in range(5):
        assert submit(app, form[1], email=f"person{n}@example.co.uk").status_code == 200
    assert submit(app, form[1], email="person6@example.co.uk").status_code == 422


def test_admin_settings_paused_forms_and_member_access(app, client, member_client, form):
    form_id, token = form
    settings = {"csrf": client.csrf, "name": "Website enquiries", "heading": "Talk to us", "button_label": "Send it",
                "thank_you": "Cheers", "owner": "Test Member", "lifecycle_stage": "Subscriber", "field_phone": "required",
                "field_company": "off", "field_job_title": "optional", "field_message": "off", "ask_consent": "on",
                "active": "on"}
    assert client.post(f"/forms/{form_id}", data=settings).status_code == 302
    page = app.test_client().get(f"/f/{token}").get_data(as_text=True)
    assert "Talk to us" in page and 'name="company"' not in page and 'name="job_title"' in page
    # Saving without "active" pauses the form.
    paused = {k: v for k, v in settings.items() if k != "active"}
    assert client.post(f"/forms/{form_id}", data=paused).status_code == 302
    assert app.test_client().get(f"/f/{token}").status_code == 410
    assert member_client.get(f"/forms/{form_id}").status_code == 200
    assert member_client.post(f"/forms/{form_id}", data={**settings, "csrf": member_client.csrf}).status_code == 403
    assert member_client.post("/forms", data={"csrf": member_client.csrf, "name": "Nope"}).status_code == 403


def test_forms_are_private_and_erasure_removes_submissions(app, client, rival, form):
    form_id, token = form
    assert rival.get(f"/forms/{form_id}").status_code == 404
    submit(app, token)
    contact_id = query(app, "SELECT id FROM contacts WHERE workspace_id=? AND email='morag@example.co.uk'", app.ws)[0][0]
    sar = client.get(f"/contacts/{contact_id}/export").get_json()
    assert sar["form_submissions"][0]["data"]["message"] == "Can you quote for 20 seats?"
    client.post(f"/contacts/{contact_id}/erase", data={"csrf": client.csrf})
    assert query(app, "SELECT COUNT(*) FROM form_submissions WHERE form_id=?", form_id)[0][0] == 0
