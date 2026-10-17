import base64
import hashlib
import hmac
import json
import re
import time

import pytest

from campaigns import body_html
from conftest import ADMIN, query

SECRET = "whsec_" + base64.b64encode(b"test webhook secret").decode()


@pytest.fixture
def outbox(app):
    app.config.update(MAIL_BACKEND="memory", RESEND_WEBHOOK_SECRET=SECRET, MAIL_FROM="hello@mail.example.co.uk")
    app.extensions["outbox"] = []
    return app.extensions["outbox"]


def consenting(app):
    return query(app, "SELECT COUNT(*) FROM contacts WHERE workspace_id=? AND marketing_consent=1 AND email <> '' "
                      "AND unsubscribed_at IS NULL AND email_bounced_at IS NULL", app.ws)[0][0]


def draft(app, client, **changes):
    client.post("/email", data={"csrf": client.csrf})
    cid = query(app, "SELECT MAX(id) FROM email_campaigns WHERE workspace_id=?", app.ws)[0][0]
    data = {"csrf": client.csrf, "name": "Autumn offer", "subject": "Hello {{first_name}}", "preheader": "A quick note",
            "body": "Hi {{first_name}},\n\nWe've a **new** offer.\n\n- One\n- Two\n\n[Book a call](https://example.co.uk/book)",
            **changes}
    client.post(f"/email/{cid}", data=data)
    return cid


def send_all(client, cid):
    client.post(f"/email/{cid}/start", data={"csrf": client.csrf})
    for _ in range(20):
        r = client.post(f"/email/{cid}/deliver", data={"csrf": client.csrf}, headers={"X-Requested-With": "fetch"}).get_json()
        if not r["remaining"]:
            return r


def signed(payload, secret=SECRET):
    body = json.dumps(payload).encode()
    msg_id, stamp = "msg_1", str(int(time.time()))
    key = base64.b64decode(secret.split("_", 1)[1])
    sig = base64.b64encode(hmac.new(key, f"{msg_id}.{stamp}.".encode() + body, hashlib.sha256).digest()).decode()
    return body, {"svix-id": msg_id, "svix-timestamp": stamp, "svix-signature": f"v1,{sig}", "Content-Type": "application/json"}


def test_body_formatting_is_safe():
    html = str(body_html("<script>x</script>\n\n**Bold** and [link](https://ok.example)\n\n- a\n- b"))
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "<strong>Bold</strong>" in html and 'href="https://ok.example"' in html and "<ul" in html
    assert 'href="javascript' not in str(body_html("[x](javascript:alert(1))"))  # stays as plain text


def test_audience_is_only_people_who_opted_in(app, client, outbox):
    cid = draft(app, client)
    r = client.post(f"/email/{cid}", data={"csrf": client.csrf, "name": "x", "subject": "s", "body": "b"},
                    headers={"X-Requested-With": "fetch"}).get_json()
    assert r["audience"] == consenting(app) > 0
    r = client.post(f"/email/{cid}", data={"csrf": client.csrf, "name": "x", "subject": "s", "body": "b", "stages": "Customer"},
                    headers={"X-Requested-With": "fetch"}).get_json()
    customers = query(app, "SELECT COUNT(*) FROM contacts WHERE workspace_id=? AND marketing_consent=1 AND email <> '' "
                           "AND lifecycle_stage='Customer'", app.ws)[0][0]
    assert r["audience"] == customers


def test_preview_and_test_send(app, client, outbox):
    cid = draft(app, client)
    preview = client.get(f"/email/{cid}/preview").get_data(as_text=True)
    assert "Hi Test," in preview and "<strong>new</strong>" in preview and "Unsubscribe" in preview
    client.post(f"/email/{cid}/test", data={"csrf": client.csrf})
    assert len(outbox) == 1 and outbox[0]["to"] == [ADMIN[1]] and outbox[0]["subject"].startswith("[Test]")


def test_sending_reaches_everyone_once_with_unsubscribe_headers(app, client, outbox):
    cid = draft(app, client)
    expected = consenting(app)
    result = send_all(client, cid)
    assert result["sent"] == expected and len(outbox) == expected
    msg = outbox[0]
    assert msg["from"] == '"Thistle Ltd" <hello@mail.example.co.uk>' or msg["from"] == "Thistle Ltd <hello@mail.example.co.uk>"
    assert msg["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert "/u/" in msg["headers"]["List-Unsubscribe"] and "/u/" in msg["html"]
    assert re.match(r"Hello \w+", msg["subject"])
    assert query(app, "SELECT status FROM email_campaigns WHERE id=?", cid)[0][0] == "Sent"
    send_all(client, cid)
    assert len(outbox) == expected  # nobody gets it twice


def test_members_draft_but_admins_send(app, member_client, outbox):
    cid = draft(app, member_client)
    assert member_client.post(f"/email/{cid}/start", data={"csrf": member_client.csrf}).status_code == 403
    assert member_client.post(f"/email/{cid}/deliver", data={"csrf": member_client.csrf}).status_code == 403
    assert not outbox


def test_nothing_sends_until_email_is_set_up(app, client):
    app.config.update(MAIL_BACKEND=None, RESEND_API_KEY="")
    cid = draft(app, client)
    assert "isn't switched on" in client.get(f"/email/{cid}").get_data(as_text=True)
    client.post(f"/email/{cid}/start", data={"csrf": client.csrf})
    assert query(app, "SELECT status FROM email_campaigns WHERE id=?", cid)[0][0] == "Draft"


def test_unsubscribe_link_and_one_click(app, client, outbox):
    cid = draft(app, client)
    send_all(client, cid)
    links = [re.search(r"<(http[^>]+)>", m["headers"]["List-Unsubscribe"]).group(1) for m in outbox[:2]]
    visitor = app.test_client()
    page = visitor.get(links[0])
    assert page.status_code == 200 and "Stop marketing emails" in page.get_data(as_text=True)
    assert "unsubscribed" in visitor.post(links[0]).get_data(as_text=True)
    assert visitor.post(links[1], data={"List-Unsubscribe": "One-Click"}).status_code == 204
    gone = query(app, "SELECT COUNT(*) FROM contacts WHERE workspace_id=? AND unsubscribed_at IS NOT NULL "
                      "AND marketing_consent=0", app.ws)[0][0]
    assert gone == 2
    assert visitor.get("/u/not-a-real-token").status_code == 404
    assert draft(app, client) and consenting(app) == len(outbox) - 2


def test_resend_webhooks_record_bounces_complaints_and_opens(app, client, outbox):
    cid = draft(app, client)
    send_all(client, cid)
    rows = query(app, "SELECT provider_id, contact_id FROM campaign_recipients WHERE campaign_id=? ORDER BY id", cid)
    body, headers = signed({"type": "email.bounced", "data": {"email_id": rows[0][0]}})
    assert app.test_client().post("/webhooks/resend", data=body, headers={**headers, "svix-signature": "v1,forged"}).status_code == 401
    assert app.test_client().post("/webhooks/resend", data=body, headers=headers).status_code == 204
    assert query(app, "SELECT email_bounced_at IS NOT NULL FROM contacts WHERE id=?", rows[0][1])[0][0]
    body, headers = signed({"type": "email.complained", "data": {"email_id": rows[1][0]}})
    app.test_client().post("/webhooks/resend", data=body, headers=headers)
    assert query(app, "SELECT marketing_consent FROM contacts WHERE id=?", rows[1][1])[0][0] == 0
    body, headers = signed({"type": "email.opened", "data": {"email_id": rows[2][0]}})
    app.test_client().post("/webhooks/resend", data=body, headers=headers)
    page = client.get(f"/email/{cid}").get_data(as_text=True)
    assert "Bounced" in page and "1 bounced, 1 unsubscribed" in page


def test_campaigns_are_private_and_erasure_removes_send_records(app, client, rival, outbox):
    cid = draft(app, client)
    assert rival.get(f"/email/{cid}").status_code == 404
    send_all(client, cid)
    contact_id = query(app, "SELECT contact_id FROM campaign_recipients WHERE campaign_id=? LIMIT 1", cid)[0][0]
    client.post(f"/contacts/{contact_id}/erase", data={"csrf": client.csrf})
    assert query(app, "SELECT COUNT(*) FROM campaign_recipients WHERE contact_id=?", contact_id)[0][0] == 0


def test_quote_can_be_emailed_to_the_customer(app, client, outbox):
    deal = query(app, "SELECT d.id FROM deals d JOIN contacts c ON c.id=d.contact_id WHERE d.workspace_id=? AND c.email <> '' "
                      "AND d.stage NOT IN ('Won','Lost') ORDER BY d.id LIMIT 1", app.ws)[0][0]
    client.post(f"/deals/{deal}/quote", data={"csrf": client.csrf})
    quote_id, token = query(app, "SELECT id, token FROM quotes WHERE deal_id=? ORDER BY id DESC", deal)[0]
    client.post(f"/quotes/{quote_id}/email", data={"csrf": client.csrf})
    assert len(outbox) == 1 and f"/q/{token}" in outbox[0]["html"]
    assert query(app, "SELECT status FROM quotes WHERE id=?", quote_id)[0][0] == "Sent"


def test_form_owner_gets_an_alert(app, client, outbox):
    app.config["FORM_MIN_SECONDS"] = 0
    client.post("/forms", data={"csrf": client.csrf, "name": "Website enquiries"})
    token = query(app, "SELECT token FROM web_forms WHERE workspace_id=? ORDER BY id DESC", app.ws)[0][0]
    v = app.test_client()
    stamp = re.search(r'name="stamp" value="([^"]+)"', v.get(f"/f/{token}").get_data(as_text=True)).group(1)
    v.post(f"/f/{token}", data={"stamp": stamp, "first_name": "Morag", "last_name": "Campbell",
                                "email": "morag@example.co.uk", "message": "Hello there"})
    assert len(outbox) == 1 and outbox[0]["to"] == [ADMIN[1]] and outbox[0]["reply_to"] == "morag@example.co.uk"
