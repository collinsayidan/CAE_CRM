import re
from datetime import datetime

import pytest

from conftest import ADMIN, MEMBER, first_id, query
from db import get_db


@pytest.fixture
def outbox(app):
    app.config["MAIL_BACKEND"] = "memory"
    app.extensions["outbox"] = []
    return app.extensions["outbox"]


def run(app, statement, *args):
    with app.app_context():
        get_db().execute(statement, args)
        get_db().commit()


def ticket_with_contact(app, email="customer@example.co.uk"):
    ticket = first_id(app, "tickets", app.ws, "status <> 'Closed' AND contact_id IS NOT NULL")
    contact = query(app, "SELECT contact_id FROM tickets WHERE id=?", ticket)[0][0]
    run(app, "UPDATE contacts SET email=?, first_name='Morag', email_bounced_at=NULL WHERE id=?", email, contact)
    run(app, "UPDATE tickets SET status='New', first_responded_at=NULL WHERE id=?", ticket)
    return ticket, contact


def cron(app):
    app.config["CRON_SECRET"] = "s3cret"
    return app.test_client().get("/cron/sync", headers={"Authorization": "Bearer s3cret"}).get_json()


# --- Replies and saved replies ----------------------------------------------------------------------------------------

def test_replying_to_a_ticket_emails_the_customer(app, client, outbox):
    ticket, contact = ticket_with_contact(app)
    page = client.get(f"/tickets/{ticket}").get_data(as_text=True)
    assert "Reply by email" in page and "customer@example.co.uk" in page
    client.post(f"/tickets/{ticket}/reply", data={"csrf": client.csrf, "subject": "Re: your login",
                                                  "body": "Hi Morag,\n\nThat's fixed now.\n\nThanks"})
    (msg,) = outbox
    assert msg["to"] == ["customer@example.co.uk"] and msg["subject"] == "Re: your login"
    assert "fixed now." in msg["html"] and "request #" in msg["html"]
    status, responded = query(app, "SELECT status, first_responded_at FROM tickets WHERE id=?", ticket)[0]
    assert status == "Waiting on contact" and responded
    kind, body = query(app, "SELECT kind, body FROM engagements WHERE ticket_id=? AND subject='Re: your login'", ticket)[0]
    assert kind == "email" and "fixed" in body


def test_replies_need_a_contact_email_and_text(app, client, outbox):
    ticket, contact = ticket_with_contact(app)
    client.post(f"/tickets/{ticket}/reply", data={"csrf": client.csrf, "body": "  "})
    run(app, "UPDATE contacts SET email=NULL WHERE id=?", contact)
    client.post(f"/tickets/{ticket}/reply", data={"csrf": client.csrf, "body": "Hello"})
    assert not outbox
    assert "Link a contact with an email address" in client.get(f"/tickets/{ticket}").get_data(as_text=True)


def test_unconfirmed_people_cannot_reply(app, client, outbox):
    ticket, _ = ticket_with_contact(app)
    run(app, "UPDATE users SET email_verified_at=NULL WHERE email=?", ADMIN[1])
    client.post(f"/tickets/{ticket}/reply", data={"csrf": client.csrf, "body": "Hello"})
    assert not outbox


def test_saved_replies_fill_in_placeholders(app, client, member_client, outbox):
    assert member_client.get("/settings/saved-replies").status_code == 403
    client.post("/settings/saved-replies", data={"csrf": client.csrf, "title": "Fixed",
                                                 "body": "Hi {{first_name}}, ticket {{ticket_number}} ({{ticket_subject}}) "
                                                         "is sorted. {{your_name}}, {{business_name}}"})
    reply = query(app, "SELECT id FROM saved_replies WHERE workspace_id=?", app.ws)[0][0]
    ticket, _ = ticket_with_contact(app)
    subject = query(app, "SELECT subject FROM tickets WHERE id=?", ticket)[0][0]
    page = client.get(f"/tickets/{ticket}?reply={reply}").get_data(as_text=True)
    assert f"Hi Morag, ticket #{ticket} ({subject}) is sorted. {ADMIN[0]}, Thistle Ltd" in page.replace("&#39;", "'")
    client.post("/settings/saved-replies", data={"csrf": client.csrf, "reply_id": reply, "title": "Fixed", "body": "New text"})
    assert query(app, "SELECT body FROM saved_replies WHERE id=?", reply)[0][0] == "New text"
    client.post("/settings/saved-replies", data={"csrf": client.csrf, "reply_id": reply, "action": "delete"})
    assert not query(app, "SELECT 1 FROM saved_replies WHERE workspace_id=?", app.ws)


def test_saved_replies_are_private_to_the_workspace(app, client, rival):
    client.post("/settings/saved-replies", data={"csrf": client.csrf, "title": "Secret", "body": "Our wording"})
    reply = query(app, "SELECT id FROM saved_replies WHERE workspace_id=?", app.ws)[0][0]
    assert "Secret" not in rival.get("/settings/saved-replies").get_data(as_text=True)
    assert rival.post("/settings/saved-replies", data={"csrf": rival.csrf, "reply_id": reply, "action": "delete"}).status_code == 404
    rival_ticket = first_id(app, "tickets", app.rival_ws)
    assert "Our wording" not in rival.get(f"/tickets/{rival_ticket}?reply={reply}").get_data(as_text=True)


# --- Satisfaction survey ----------------------------------------------------------------------------------------------

def close(client, ticket):
    client.post(f"/tickets/{ticket}/status", data={"csrf": client.csrf, "status": "Closed"})


def test_no_survey_until_an_admin_switches_it_on(app, client, outbox):
    ticket, _ = ticket_with_contact(app)
    close(client, ticket)
    assert not outbox and not query(app, "SELECT 1 FROM ticket_surveys")


def test_survey_is_sent_once_and_recorded_on_the_page(app, client, outbox):
    run(app, "UPDATE workspaces SET csat_on=1 WHERE id=?", app.ws)
    ticket, _ = ticket_with_contact(app)
    close(client, ticket)
    (msg,) = outbox
    assert msg["subject"].startswith("How did we do?") and msg["to"] == ["customer@example.co.uk"]
    link = re.search(r'href="http://localhost(/survey/[^"?]+)\?r=poor"', msg["html"]).group(1)
    customer = app.test_client()
    page = customer.get(link + "?r=poor")
    assert page.status_code == 200 and "How did we do?" in page.get_data(as_text=True)
    assert query(app, "SELECT rating FROM ticket_surveys")[0][0] is None  # opening a link records nothing
    with customer.session_transaction() as s:
        csrf = s["csrf"]
    done = customer.post(link, data={"csrf": csrf, "rating": "good", "comment": "Quick and friendly"})
    assert "Thank you" in done.get_data(as_text=True)
    rating, comment = query(app, "SELECT rating, comment FROM ticket_surveys")[0]
    assert (rating, comment) == ("good", "Quick and friendly")
    customer.post(link, data={"csrf": csrf, "rating": "poor"})  # can't change it afterwards
    assert query(app, "SELECT rating FROM ticket_surveys")[0][0] == "good"
    assert query(app, "SELECT 1 FROM engagements WHERE ticket_id=? AND subject LIKE 'Customer rated%'", ticket)
    # Reopening and closing again doesn't send a second survey.
    client.post(f"/tickets/{ticket}/status", data={"csrf": client.csrf, "status": "Waiting on us"})
    close(client, ticket)
    assert len(outbox) == 1
    report = client.get("/reports").get_data(as_text=True)
    assert "Customer satisfaction" in report and "100%" in report and "Quick and friendly" in report


def test_survey_settings_and_bad_links(app, client, anon):
    form = {"csrf": client.csrf, "name": "Thistle Ltd", "legal_name": "Thistle Ltd", "monthly_target": "100,000",
            "invoice_prefix": "INV", "payment_terms": "30", "csat_on": "on", "bank_holiday_region": "scotland"}
    client.post("/settings", data=form)
    assert tuple(query(app, "SELECT csat_on, bank_holiday_region FROM workspaces WHERE id=?", app.ws)[0]) == (1, "scotland")
    assert anon.get("/survey/not-a-real-token").status_code == 404


# --- Daily summary ----------------------------------------------------------------------------------------------------

def test_daily_summary_lists_what_needs_each_person(app, outbox):
    member = query(app, "SELECT id FROM users WHERE email=?", MEMBER[1])[0][0]
    run(app, "UPDATE activities SET owner=?, done=0, due_at='2026-10-15T09:00' WHERE id=(SELECT MIN(id) FROM activities "
             "WHERE workspace_id=?)", MEMBER[0], app.ws)
    out = cron(app)
    assert out["summaries_sent"] >= 1
    to_member = [m for m in outbox if m["to"] == [MEMBER[1]]]
    assert len(to_member) == 1 and "Your tasks" in to_member[0]["html"] and "overdue" in to_member[0]["html"]
    assert "List-Unsubscribe" in to_member[0].get("headers", {})
    assert not any("Overdue invoices" in m["html"] for m in to_member)  # members don't get the money section
    admin = [m for m in outbox if m["to"] == [ADMIN[1]]]
    assert admin and "Overdue invoices" in admin[0]["html"]
    cron(app)  # once a day
    assert len([m for m in outbox if m["to"] == [MEMBER[1]]]) == 1
    # One click turns it off, without signing in.
    link = re.search(r'href="http://localhost(/summary/off/[^"]+)"', to_member[0]["html"]).group(1)
    visitor = app.test_client()
    assert "Turn off daily summaries?" in visitor.get(link).get_data(as_text=True)
    assert query(app, "SELECT summary_off FROM users WHERE id=?", member)[0][0] == 0
    visitor.post(link)  # a mail app's one-click unsubscribe has no session
    assert query(app, "SELECT summary_off FROM users WHERE id=?", member)[0][0] == 1


def test_no_summary_on_bank_holidays_or_when_switched_off(app, member_client, outbox):
    member_client.post("/account/summary", data={"csrf": member_client.csrf})
    assert query(app, "SELECT summary_off FROM users WHERE email=?", MEMBER[1])[0][0] == 1
    cron(app)
    assert not [m for m in outbox if m["to"] == [MEMBER[1]]]
    run(app, "UPDATE users SET summary_off=0, summary_sent_on=NULL")
    app.config["TODAY"] = app.config["TODAY"].replace(day=17)  # a Saturday
    cron(app)
    assert not [m for m in outbox if m["to"] == [MEMBER[1]]]


# --- Bank holidays ----------------------------------------------------------------------------------------------------

def test_service_levels_follow_the_workspace_nation(app, client):
    from ukfmt import add_working_hours
    import ukholidays
    with app.app_context():
        scotland = ukholidays.for_region("scotland")
        england = ukholidays.for_region("england-and-wales")
    from datetime import date
    assert date(2026, 11, 30) in scotland and date(2026, 11, 30) not in england  # St Andrew's Day
    friday = datetime(2026, 11, 27, 16, 0)
    assert add_working_hours(friday, 2, england) == datetime(2026, 11, 30, 10, 0)
    assert add_working_hours(friday, 2, scotland) == datetime(2026, 12, 1, 10, 0)
    # The Tasks calendar marks St Andrew's Day only for a Scottish business.
    assert 'title="Bank holiday">30<' not in client.get("/tasks?month=2026-11").get_data(as_text=True)
    run(app, "UPDATE workspaces SET bank_holiday_region='scotland' WHERE id=?", app.ws)
    assert 'title="Bank holiday">30<' in client.get("/tasks?month=2026-11").get_data(as_text=True)


def test_bank_holidays_refresh_from_gov_uk(app):
    app.config["HOLIDAYS_BACKEND"] = lambda: {"scotland": {"division": "scotland", "events": [
        {"title": "Extra day", "date": "2029-01-02", "notes": "", "bunting": False}]}}
    cron(app)
    assert query(app, "SELECT region, day FROM bank_holidays") == [("scotland", "2029-01-02")] or \
        [tuple(r) for r in query(app, "SELECT region, day FROM bank_holidays")] == [("scotland", "2029-01-02")]
    cron(app)
    assert len(query(app, "SELECT 1 FROM bank_holidays")) == 1
