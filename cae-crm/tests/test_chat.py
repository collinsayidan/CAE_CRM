import json
from datetime import timedelta

import pytest

from conftest import MEMBER, TODAY, query
from db import get_db
from test_helpers import FakeClaude, reply


def run(app, statement, *args):
    with app.app_context():
        get_db().execute(statement, args)
        get_db().commit()


def answer(text, sources=(), offer=False):
    return reply(json.dumps({"reply": text, "sources": list(sources), "offer_person": offer}))


def add_article(client, title, body, published=True):
    data = {"csrf": client.csrf, "title": title, "body": body}
    if published:
        data["published"] = "on"
    assert client.post("/settings/help-articles", data=data).status_code == 302


def article_id(app, title):
    return query(app, "SELECT id FROM help_articles WHERE title=?", title)[0][0]


def site_token(app, ws_id=None):
    return query(app, "SELECT site_token FROM workspaces WHERE id=?", ws_id or app.ws)[0][0]


@pytest.fixture
def claude(app):
    fake = FakeClaude()
    app.config.update(AI_BACKEND=fake, MAIL_BACKEND="memory")
    app.extensions["outbox"] = []
    return fake


@pytest.fixture
def chat_on(app, client, claude):
    add_article(client, "Opening hours", "We're open Monday to Friday, 9am to 5pm.")
    add_article(client, "Delivery", "We deliver across Scotland in 2 working days.")
    add_article(client, "Secret discounts", "Staff get 40% off.", published=False)
    resp = client.post("/settings/website-chat", data={"csrf": client.csrf, "enabled": "on", "owner": MEMBER[0],
                                                       "domains": "https://www.thistle.co.uk/contact\nnot a site",
                                                       "greeting": "Hello from Thistle!", "cap": "300"})
    assert resp.status_code == 302
    return site_token(app)


@pytest.fixture
def visitor(app):
    return app.test_client()  # someone on the business's website: no account, no cookies


def say(visitor, token, message, session=None, fetch=True):
    data = {"message": message}
    if session:
        data["session"] = session
    headers = {"X-Requested-With": "fetch"} if fetch else {}
    return visitor.post(f"/chat/{token}/message", data=data, headers=headers)


# --- Help articles ----------------------------------------------------------------------------------------------------

def test_help_articles_have_public_pages_for_published_ones_only(app, client, visitor):
    add_article(client, "Opening hours", "We're open **Monday to Friday**.\n\n- 9am to 5pm\n\n[Find us](https://thistle.co.uk/map)")
    add_article(client, "Draft prices", "Not ready yet.", published=False)
    token = site_token(app)
    page = visitor.get(f"/help/{token}").get_data(as_text=True)
    assert "Opening hours" in page and "Draft prices" not in page
    shown = visitor.get(f"/help/{token}/{article_id(app, 'Opening hours')}").get_data(as_text=True)
    assert "<strong>Monday to Friday</strong>" in shown and "<li>9am to 5pm</li>" in shown
    assert '<a target="_blank" rel="noopener noreferrer" href="https://thistle.co.uk/map">Find us</a>' in shown
    assert '<p style=' not in shown
    assert visitor.get(f"/help/{token}/{article_id(app, 'Draft prices')}").status_code == 404
    assert visitor.get("/help/not-a-token").status_code == 404


def test_admins_edit_and_delete_articles(app, client, member_client):
    add_article(client, "Returns", "30 days.")
    a = article_id(app, "Returns")
    client.post("/settings/help-articles", data={"csrf": client.csrf, "article_id": a, "title": "Returns policy",
                                                 "body": "You have 30 days."})
    assert tuple(query(app, "SELECT title, published FROM help_articles WHERE id=?", a)[0]) == ("Returns policy", 0)
    assert member_client.get("/settings/help-articles").status_code == 403
    assert member_client.post("/settings/help-articles", data={"csrf": member_client.csrf, "title": "X",
                                                               "body": "Y"}).status_code == 403
    client.post("/settings/help-articles", data={"csrf": client.csrf, "article_id": a, "action": "delete"})
    assert not query(app, "SELECT 1 FROM help_articles")


def test_articles_stay_in_their_own_workspace(app, client, rival, visitor):
    add_article(client, "Opening hours", "9 to 5.")
    a = article_id(app, "Opening hours")
    assert rival.post("/settings/help-articles", data={"csrf": rival.csrf, "article_id": a, "action": "delete"}).status_code == 404
    assert rival.get(f"/settings/help-articles?edit={a}").get_data(as_text=True).count("9 to 5.") == 0
    add_article(rival, "Rival hours", "Never open.")
    assert visitor.get(f"/help/{site_token(app, app.rival_ws)}/{a}").status_code == 404
    assert "Opening hours" not in visitor.get(f"/help/{site_token(app, app.rival_ws)}").get_data(as_text=True)


# --- Settings ---------------------------------------------------------------------------------------------------------

def test_website_chat_needs_an_api_key_and_an_admin(app, client, member_client, visitor):
    add_article(client, "Opening hours", "9 to 5.")
    assert client.get("/settings/website-chat").status_code == 404
    assert "Website chat" not in client.get("/settings").get_data(as_text=True)
    app.config["AI_BACKEND"] = FakeClaude()
    assert "Website chat" in client.get("/settings").get_data(as_text=True)
    assert member_client.get("/settings/website-chat").status_code == 403
    assert visitor.get(f"/chat/{site_token(app)}").status_code == 404  # not switched on yet


def test_settings_save_clean_domains_and_show_the_snippet(app, client, chat_on):
    w = query(app, "SELECT chat_on, chat_domains, chat_greeting, chat_owner, chat_daily_cap FROM workspaces WHERE id=?", app.ws)[0]
    assert tuple(w) == (1, "www.thistle.co.uk", "Hello from Thistle!", MEMBER[0], 300)
    page = client.get("/settings/website-chat").get_data(as_text=True)
    assert f'data-chat="{chat_on}"' in page and "/chat/widget.js" in page
    client.post("/settings/website-chat", data={"csrf": client.csrf, "enabled": "on", "cap": "5000", "owner": "Nobody"})
    assert tuple(query(app, "SELECT chat_daily_cap, chat_owner FROM workspaces WHERE id=?", app.ws)[0]) == (300, "Test Admin")
    client.post("/settings/website-chat", data={"csrf": client.csrf, "enabled": "on", "cap": "25"})
    assert query(app, "SELECT chat_daily_cap FROM workspaces WHERE id=?", app.ws)[0][0] == 25


def test_widget_script_is_public_and_points_back_here(visitor):
    resp = visitor.get("/chat/widget.js")
    assert resp.status_code == 200 and resp.mimetype == "application/javascript"
    assert "http://localhost" in resp.get_data(as_text=True)


# --- Chatting ---------------------------------------------------------------------------------------------------------

def test_chat_page_says_its_an_ai_and_can_only_be_framed_by_the_business(app, chat_on, visitor):
    resp = visitor.get(f"/chat/{chat_on}?embed=1")
    page = resp.get_data(as_text=True)
    assert resp.status_code == 200 and "chatting with an AI" in page and "Hello from Thistle!" in page
    assert resp.headers["Content-Security-Policy"] == "frame-ancestors 'self' https://www.thistle.co.uk"
    assert resp.headers["Cache-Control"] == "no-store"
    assert "Secret discounts" not in page


def test_visitor_gets_an_answer_from_published_articles(app, chat_on, claude, visitor):
    hours = article_id(app, "Opening hours")
    claude.replies.append(answer("We're open **9am to 5pm**, Monday to Friday.", [hours, 9999]))
    resp = say(visitor, chat_on, "When are you open?")
    data = resp.get_json()
    assert "<strong>9am to 5pm</strong>" in data["reply"] and data["offer_person"] is False
    assert data["links"] == [{"title": "Opening hours", "url": f"/help/{chat_on}/{hours}"}]  # made-up ids dropped
    request = claude.requests[0]
    assert request["model"] == "claude-opus-5-5"
    library = request["system"][1]
    assert library["cache_control"] == {"type": "ephemeral"}
    assert "Monday to Friday, 9am to 5pm" in library["text"] and "Staff get 40% off" not in library["text"]
    assert request["messages"] == [{"role": "user", "content": "When are you open?"}]

    claude.replies.append(answer("Yes, across Scotland."))
    second = say(visitor, chat_on, "Do you deliver?", session=data["session"]).get_json()
    assert second["session"] == data["session"]
    assert [m["role"] for m in claude.requests[1]["messages"]] == ["user", "assistant", "user"]
    assert query(app, "SELECT messages FROM chat_sessions")[0][0] == 2
    assert [r[0] for r in query(app, "SELECT role FROM chat_messages ORDER BY id")] == ["visitor", "bot", "visitor", "bot"]


def test_chat_works_without_javascript(app, chat_on, claude, visitor):
    claude.replies.append(answer("We're open 9 to 5.", [article_id(app, "Opening hours")]))
    resp = say(visitor, chat_on, "When are you open?", fetch=False)
    assert resp.status_code == 302 and resp.headers["Location"].endswith("#latest")
    page = visitor.get(resp.headers["Location"].split("#")[0]).get_data(as_text=True)
    assert "When are you open?" in page and "open 9 to 5." in page and "Opening hours" in page


def test_bad_or_failed_answers_offer_a_person(app, chat_on, claude, visitor):
    claude.replies += [reply("not json"), RuntimeError("Anthropic is down"), reply("", stop="refusal")]
    for _ in range(3):
        data = say(visitor, chat_on, "Hello?").get_json()
        assert data["offer_person"] is True and "Sorry" in data["reply"]


def test_visitor_messages_are_escaped(app, chat_on, claude, visitor):
    claude.replies.append(answer("<script>alert(1)</script>"))
    data = say(visitor, chat_on, "<img src=x onerror=alert(1)>", fetch=True).get_json()
    assert "<script>" not in data["reply"]
    page = visitor.get(f"/chat/{chat_on}?s={data['session']}").get_data(as_text=True)
    assert "<img src=x" not in page and "<script>alert" not in page


def test_chat_is_off_for_unknown_tokens_and_needs_a_message(app, chat_on, claude, visitor):
    assert say(visitor, "nope", "Hi").status_code == 404
    assert say(visitor, chat_on, "   ").get_json() == {"error": "Type a message first."}
    assert not claude.requests


# --- Limits -----------------------------------------------------------------------------------------------------------

def test_daily_cap_stops_calls_to_claude(app, client, chat_on, claude, visitor):
    client.post("/settings/website-chat", data={"csrf": client.csrf, "enabled": "on", "cap": "2"})
    claude.replies += [answer("One."), answer("Two.")]
    session = say(visitor, chat_on, "One?").get_json()["session"]
    say(visitor, chat_on, "Two?", session=session)
    data = say(visitor, chat_on, "Three?", session=session).get_json()
    assert "very busy today" in data["notice"] and data["offer_person"] is True
    assert len(claude.requests) == 2


def test_long_chats_and_fast_visitors_are_limited(app, chat_on, claude, visitor):
    claude.replies.append(answer("Hello."))
    session = say(visitor, chat_on, "Hi").get_json()["session"]
    run(app, "UPDATE chat_sessions SET messages=40")
    assert "getting long" in say(visitor, chat_on, "More?", session=session).get_json()["notice"]
    visitor_key = query(app, "SELECT visitor FROM chat_sessions")[0][0]
    with app.app_context():
        db = get_db()
        stamp = "2026-10-16T10:58"
        sid = db.insert("chat_sessions", workspace_id=app.ws, token="other-chat", visitor=visitor_key, started_at=stamp,
                        last_at=stamp, messages=0)
        for _ in range(30):
            db.insert("chat_messages", workspace_id=app.ws, session_id=sid, role="visitor", body="spam", created_at=stamp)
        db.commit()
    assert "sending messages quickly" in say(visitor, chat_on, "New chat").get_json()["notice"]
    assert len(claude.requests) == 1


# --- Handing over to a person -----------------------------------------------------------------------------------------

def test_talk_to_a_person_opens_a_ticket_with_the_chat(app, chat_on, claude, visitor):
    claude.replies.append(answer("I don't know, sorry. Shall I pass you to the team?", offer=True))
    session = say(visitor, chat_on, "Can I change my order?").get_json()["session"]
    resp = visitor.post(f"/chat/{chat_on}/person", headers={"X-Requested-With": "fetch"},
                        data={"session": session, "name": "morag campbell", "email": "Morag@Bramble.co.uk",
                              "message": "Please change order 1042 to blue."})
    assert "Morag" in resp.get_json()["done"]
    ticket = query(app, "SELECT id, subject, source, owner, contact_id, workspace_id FROM tickets WHERE subject LIKE 'Website chat:%'")[0]
    assert ticket[1].startswith("Website chat: Please change order") and ticket[3] == MEMBER[0] and ticket[5] == app.ws
    contact = query(app, "SELECT first_name, last_name, email, marketing_consent, lawful_basis FROM contacts WHERE id=?", ticket[4])[0]
    assert tuple(contact) == ("Morag", "Campbell", "morag@bramble.co.uk", 0, "Legitimate interests")
    transcript = query(app, "SELECT body FROM engagements WHERE ticket_id=? AND subject='Website chat transcript'", ticket[0])[0][0]
    assert "Visitor: Can I change my order?" in transcript and "Chatbot: I don't know" in transcript
    assert query(app, "SELECT ticket_id FROM chat_sessions WHERE token=?", session)[0][0] == ticket[0]
    again = visitor.post(f"/chat/{chat_on}/person", headers={"X-Requested-With": "fetch"},
                         data={"session": session, "name": "Morag", "email": "morag@bramble.co.uk", "message": "Hello?"})
    assert "already has your details" in again.get_json()["done"]
    assert len(query(app, "SELECT 1 FROM tickets WHERE subject LIKE 'Website chat:%'")) == 1


def test_handover_matches_an_existing_contact_and_checks_details(app, chat_on, visitor):
    existing = query(app, "SELECT id, email FROM contacts WHERE workspace_id=? AND email IS NOT NULL ORDER BY id LIMIT 1", app.ws)[0]
    before = query(app, "SELECT COUNT(*) FROM contacts")[0][0]
    bad = visitor.post(f"/chat/{chat_on}/person", headers={"X-Requested-With": "fetch"},
                       data={"name": "A", "email": "not-an-email", "message": "Hi"})
    assert bad.status_code == 400
    page = visitor.post(f"/chat/{chat_on}/person", data={"name": "A Person", "email": existing[1].upper(),
                                                          "message": "Call me back please."})
    assert page.status_code == 200 and "The team has your message" in page.get_data(as_text=True)
    assert query(app, "SELECT COUNT(*) FROM contacts")[0][0] == before
    assert query(app, "SELECT contact_id FROM tickets WHERE subject LIKE 'Website chat:%'")[0][0] == existing[0]


def test_chats_stay_in_their_own_workspace(app, chat_on, claude, rival, visitor):
    claude.replies.append(answer("Hello."))
    session = say(visitor, chat_on, "Thistle visitor question").get_json()["session"]
    rival.post("/settings/website-chat", data={"csrf": rival.csrf, "enabled": "on"})
    rival_token = site_token(app, app.rival_ws)
    page = visitor.get(f"/chat/{rival_token}?s={session}").get_data(as_text=True)
    assert "Thistle visitor question" not in page
    visitor.post(f"/chat/{rival_token}/person", data={"session": session, "name": "Sneaky", "email": "s@example.co.uk",
                                                      "message": "Hello"})
    assert query(app, "SELECT ticket_id FROM chat_sessions WHERE token=?", session)[0][0] is None
    assert query(app, "SELECT workspace_id FROM tickets WHERE subject LIKE 'Website chat:%'")[0][0] == app.rival_ws
    assert "Thistle visitor question" not in rival.get("/settings/website-chat").get_data(as_text=True)


# --- Retention and legal ----------------------------------------------------------------------------------------------

def test_old_chats_without_tickets_are_deleted(app, chat_on, claude, visitor):
    claude.replies += [answer("One."), answer("Two."), answer("Three.")]
    old = say(visitor, chat_on, "Old").get_json()["session"]
    kept = say(visitor, chat_on, "Old but ticketed").get_json()["session"]
    recent = say(visitor, chat_on, "Recent").get_json()["session"]
    visitor.post(f"/chat/{chat_on}/person", data={"session": kept, "name": "Morag", "email": "m@bramble.co.uk",
                                                  "message": "Help"})
    long_ago = (TODAY - timedelta(days=31)).isoformat() + "T10:00"
    run(app, "UPDATE chat_sessions SET last_at=? WHERE token IN (?, ?)", long_ago, old, kept)
    import chat
    with app.app_context():
        assert chat.purge() == 1
    assert sorted(r[0] for r in query(app, "SELECT token FROM chat_sessions")) == sorted([kept, recent])
    assert query(app, "SELECT COUNT(*) FROM chat_messages")[0][0] == 4


def test_legal_pages_cover_website_chat(client):
    assert "website chat" in client.get("/legal/dpa").get_data(as_text=True)
    assert "AI assistant and website chat" in client.get("/legal/privacy").get_data(as_text=True)
