from monitoring import scrub


def test_error_reports_carry_nothing_personal():
    event = {"request": {"url": "https://example/contacts/4", "data": {"password": "secret", "email": "a@b.co.uk"},
                         "cookies": {"session": "abc"}, "query_string": "token=xyz",
                         "headers": {"Authorization": "Bearer t", "Cookie": "session=abc", "User-Agent": "UA"}},
             "user": {"id": "4", "workspace": "2", "email": "a@b.co.uk", "ip_address": "1.2.3.4"}}
    out = scrub(event)
    req = out["request"]
    assert "data" not in req and "cookies" not in req and "query_string" not in req
    assert req["headers"]["Authorization"] == "[removed]" and req["headers"]["Cookie"] == "[removed]"
    assert req["headers"]["User-Agent"] == "UA" and req["url"].endswith("/contacts/4")
    assert out["user"] == {"id": "4", "workspace": "2"}
