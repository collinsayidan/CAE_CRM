import json

import pytest

from conftest import query
from db import get_db
from test_helpers import FakeClaude, reply

DRAFT = {"subjects": ["Support that keeps your site running, {{first_name}}", "A calmer month online", "New: monthly support"],
         "preheader": "From £49 a month. Book a 15-minute call.",
         "body": "Hi {{first_name}},\n\nOur new support plan starts at £49 a month.\n\n[Book a call](https://example.co.uk)\n\nThistle Ltd",
         "social_post": "We've launched a monthly support plan for small businesses."}


@pytest.fixture
def claude(app):
    fake = FakeClaude()
    app.config["AI_BACKEND"] = fake
    with app.app_context():
        get_db().execute("UPDATE workspaces SET ai_enabled=1 WHERE id=?", (app.ws,))
        get_db().commit()
    return fake


def new_campaign(client):
    resp = client.post("/email", data={"csrf": client.csrf, "name": "Support plan"})
    return int(resp.headers["Location"].rsplit("/", 1)[1])


def test_drafting_needs_the_assistant_on(app, client):
    cid = new_campaign(client)
    assert "Draft with AI" not in client.get(f"/email/{cid}").get_data(as_text=True)
    assert client.post(f"/email/{cid}/ai", data={"csrf": client.csrf, "brief": "A new support plan"}).status_code == 404


def test_a_draft_from_a_brief_sees_no_contact_details(app, client, claude):
    cid = new_campaign(client)
    assert "Draft with AI" in client.get(f"/email/{cid}").get_data(as_text=True)
    claude.replies.append(reply(json.dumps(DRAFT)))
    resp = client.post(f"/email/{cid}/ai", data={"csrf": client.csrf, "brief": "Our new monthly support plan from £49",
                                                   "tone": "Professional"})
    assert resp.status_code == 302 and resp.headers["Location"].endswith("#ai-draft")
    sent = claude.requests[0]
    prompt = sent["messages"][0]["content"]
    assert "Our new monthly support plan from £49" in prompt and "Tone: Professional" in prompt
    assert sent["output_config"]["format"]["type"] == "json_schema"
    record = json.loads(prompt.split("<record>\n", 1)[1].split("\n</record>", 1)[0])
    assert set(record) == {"business", "products", "audience_stages"} and record["business"]["name"] == "Thistle Ltd"
    emails = [r[0] for r in query(app, "SELECT email FROM contacts WHERE workspace_id=? AND email IS NOT NULL", app.ws)]
    assert emails and not any(e in prompt for e in emails)  # no contact's details leave the CRM
    page = client.get(f"/email/{cid}").get_data(as_text=True)
    assert "A calmer month online" in page and "We&#39;ve launched a monthly support plan" in page
    assert query(app, "SELECT questions FROM ai_usage WHERE workspace_id=?", app.ws)[0][0] == 1


def test_using_the_draft_fills_in_the_campaign(app, client, claude):
    cid = new_campaign(client)
    claude.replies.append(reply(json.dumps(DRAFT)))
    client.post(f"/email/{cid}/ai", data={"csrf": client.csrf, "brief": "Our new monthly support plan"})
    resp = client.post(f"/email/{cid}/ai/use", data={"csrf": client.csrf, "subject": "1"})
    assert resp.status_code == 302
    subject, preheader, body = query(app, "SELECT subject, preheader, body FROM email_campaigns WHERE id=?", cid)[0]
    assert subject == "A calmer month online" and preheader == DRAFT["preheader"] and body == DRAFT["body"]


def test_bad_briefs_and_bad_replies_change_nothing(app, client, claude):
    cid = new_campaign(client)
    client.post(f"/email/{cid}/ai", data={"csrf": client.csrf, "brief": "hi"})
    assert claude.requests == []  # too short to ask about
    claude.replies.append(reply("not json"))
    client.post(f"/email/{cid}/ai", data={"csrf": client.csrf, "brief": "Our new monthly support plan"})
    assert "right shape" in client.get(f"/email/{cid}").get_data(as_text=True)
    assert query(app, "SELECT COUNT(*) FROM ai_outputs WHERE task='campaign'")[0][0] == 0
    resp = client.post(f"/email/{cid}/ai/use", data={"csrf": client.csrf})
    assert "expired" in client.get(resp.headers["Location"]).get_data(as_text=True)
    assert query(app, "SELECT subject FROM email_campaigns WHERE id=?", cid)[0][0] == ""


def test_other_people_cant_use_your_draft(app, client, claude, member_client):
    cid = new_campaign(client)
    claude.replies.append(reply(json.dumps(DRAFT)))
    client.post(f"/email/{cid}/ai", data={"csrf": client.csrf, "brief": "Our new monthly support plan"})
    assert "A calmer month online" not in member_client.get(f"/email/{cid}").get_data(as_text=True)
    member_client.post(f"/email/{cid}/ai/use", data={"csrf": member_client.csrf})
    assert query(app, "SELECT subject FROM email_campaigns WHERE id=?", cid)[0][0] == ""
