from datetime import timedelta

from conftest import TODAY, first_id, query, refresh_csrf


def deal_with_lines(app):
    """An open deal in the sample data that has line items."""
    rows = query(app, "SELECT d.id FROM deals d WHERE d.workspace_id=? AND d.stage NOT IN ('Won','Lost') AND "
                      "EXISTS (SELECT 1 FROM line_items li WHERE li.deal_id=d.id) ORDER BY d.id LIMIT 1", app.ws)
    assert rows, "sample data should have an open deal with line items"
    return rows[0][0]


def make_quote(app, client, send=True):
    deal = deal_with_lines(app)
    resp = client.post(f"/deals/{deal}/quote", data={"csrf": client.csrf})
    assert resp.status_code == 302
    q = query(app, "SELECT id, token, net, vat FROM quotes WHERE deal_id=? ORDER BY id DESC", deal)[0]
    if send:
        client.post(f"/quotes/{q[0]}/send", data={"csrf": client.csrf})
    return deal, q


def visitor(app, path):
    c = app.test_client()
    c.get(path)
    return refresh_csrf(c)


def test_quote_is_priced_from_the_deal_and_hidden_until_sent(app, client):
    deal, (quote_id, token, net, vat) = make_quote(app, client, send=False)
    lines = query(app, "SELECT SUM(net), SUM(vat), COUNT(*) FROM quote_lines WHERE quote_id=?", quote_id)[0]
    deal_lines = query(app, "SELECT COUNT(*) FROM line_items WHERE deal_id=?", deal)[0][0]
    assert (lines[0], lines[1], lines[2]) == (net, vat, deal_lines)
    assert app.test_client().get(f"/q/{token}").status_code == 404  # drafts aren't public
    page = client.get(f"/quotes/{quote_id}").get_data(as_text=True)
    assert "Mark as sent" in page and "Draft" in page
    client.post(f"/quotes/{quote_id}/send", data={"csrf": client.csrf})
    assert query(app, "SELECT status FROM quotes WHERE id=?", quote_id)[0][0] == "Sent"
    assert app.test_client().get(f"/q/{token}").status_code == 200


def test_customer_views_and_accepts_with_a_typed_signature(app, client):
    deal, (quote_id, token, net, vat) = make_quote(app, client)
    client.get(f"/q/{token}")  # the team looking doesn't count as the customer opening it
    assert query(app, "SELECT viewed_at FROM quotes WHERE id=?", quote_id)[0][0] is None
    customer = visitor(app, f"/q/{token}")
    assert query(app, "SELECT viewed_at FROM quotes WHERE id=?", quote_id)[0][0]

    bad = customer.post(f"/q/{token}/accept", data={"csrf": customer.csrf, "signer_name": "Jo"})
    assert bad.status_code == 422 and "Type your full name" in bad.get_data(as_text=True)
    ok = customer.post(f"/q/{token}/accept", data={"csrf": customer.csrf, "signer_name": "Jo Bloggs",
                                                   "signer_position": "Director", "agree": "on"},
                       headers={"User-Agent": "Test browser", "X-Real-IP": "203.0.113.9"})
    assert ok.status_code == 302
    status, signer, ip = query(app, "SELECT status, signer_name, signer_ip FROM quotes WHERE id=?", quote_id)[0]
    assert (status, signer, ip) == ("Accepted", "Jo Bloggs", "203.0.113.9")
    assert query(app, "SELECT stage FROM deals WHERE id=?", deal)[0][0] == "Won"
    assert query(app, "SELECT COUNT(*) FROM activities WHERE deal_id=? AND subject LIKE 'Raise the invoice%'", deal)[0][0] == 1
    assert "Quote accepted" in customer.get(f"/q/{token}").get_data(as_text=True)
    # The signature can't be replaced afterwards.
    customer.post(f"/q/{token}/accept", data={"csrf": customer.csrf, "signer_name": "Someone Else", "agree": "on"})
    assert query(app, "SELECT signer_name FROM quotes WHERE id=?", quote_id)[0][0] == "Jo Bloggs"


def test_accepted_quote_becomes_one_invoice_and_is_kept(app, client):
    _, (quote_id, token, net, vat) = make_quote(app, client)
    customer = visitor(app, f"/q/{token}")
    customer.post(f"/q/{token}/accept", data={"csrf": customer.csrf, "signer_name": "Jo Bloggs", "agree": "on"})
    assert client.post(f"/quotes/{quote_id}/invoice", data={"csrf": client.csrf}).status_code == 302
    invoice_id = query(app, "SELECT invoice_id FROM quotes WHERE id=?", quote_id)[0][0]
    assert tuple(query(app, "SELECT net, vat FROM invoices WHERE id=?", invoice_id)[0]) == (net, vat)
    client.post(f"/quotes/{quote_id}/invoice", data={"csrf": client.csrf})
    assert query(app, "SELECT COUNT(*) FROM invoices WHERE id >= ?", invoice_id)[0][0] == 1
    client.post(f"/quotes/{quote_id}/delete", data={"csrf": client.csrf})
    assert query(app, "SELECT COUNT(*) FROM quotes WHERE id=?", quote_id)[0][0] == 1


def test_customer_can_decline_and_expired_quotes_cannot_be_accepted(app, client):
    _, (quote_id, token, _, _) = make_quote(app, client)
    customer = visitor(app, f"/q/{token}")
    customer.post(f"/q/{token}/decline", data={"csrf": customer.csrf, "reason": "Budget moved to next year"})
    assert tuple(query(app, "SELECT status, decline_reason FROM quotes WHERE id=?", quote_id)[0]) == \
        ("Declined", "Budget moved to next year")

    _, (quote_id, token, _, _) = make_quote(app, client)
    with app.app_context():
        from db import get_db
        get_db().execute("UPDATE quotes SET expiry_date=? WHERE id=?", ((TODAY - timedelta(days=1)).isoformat(), quote_id))
        get_db().commit()
    customer = visitor(app, f"/q/{token}")
    assert "expired" in customer.get(f"/q/{token}").get_data(as_text=True)
    customer.post(f"/q/{token}/accept", data={"csrf": customer.csrf, "signer_name": "Jo Bloggs", "agree": "on"})
    assert query(app, "SELECT status FROM quotes WHERE id=?", quote_id)[0][0] == "Sent"


def test_quotes_are_private_to_the_workspace(app, client, rival):
    _, (quote_id, _, _, _) = make_quote(app, client)
    assert rival.get(f"/quotes/{quote_id}").status_code == 404
    assert rival.post(f"/quotes/{quote_id}/delete", data={"csrf": rival.csrf}).status_code == 404
    assert f"/quotes/{quote_id}\"" not in rival.get("/quotes").get_data(as_text=True)
    deal = first_id(app, "deals", app.ws)
    assert rival.post(f"/deals/{deal}/quote", data={"csrf": rival.csrf}).status_code == 404


def test_draft_quote_can_be_deleted(app, client):
    _, (quote_id, _, _, _) = make_quote(app, client, send=False)
    client.post(f"/quotes/{quote_id}/delete", data={"csrf": client.csrf})
    assert query(app, "SELECT COUNT(*) FROM quotes WHERE id=?", quote_id)[0][0] == 0
