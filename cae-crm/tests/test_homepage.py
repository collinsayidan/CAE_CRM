import json
import re


def test_homepage_is_short_and_makes_true_claims_only(anon):
    page = anon.get("/welcome").get_data(as_text=True)
    assert page.count("<h1") == 1 and "The CRM that already knows how UK business works." in page
    for heading in ("Contacts, companies and deals", "Support tickets with real service levels", "Invoices HMRC would recognise",
                    "UK GDPR built in", "What you'd pay extra for elsewhere, included", "Set up your business in two minutes."):
        assert f">{heading}</h2>" in page, heading
    assert page.count("<section") == 4  # hero, features, comparison, call to action
    # Nothing invented: no reviews, ratings or uptime figures, and sample figures are labelled.
    for invented in ("★", "⭐", "99.95", "testimonial", "Trusted by"):
        assert invented not in page
    assert "Sample data" in page
    # Nothing loaded from other websites.
    assert not re.search(r'<(script|link)[^>]+(src|href)="https?://(?!localhost)', page)


def test_price_trial_and_vat_come_from_settings(app, anon):
    page = anon.get("/welcome").get_data(as_text=True)
    assert "£15 per user a month" in page and "plus VAT" not in page and "14 days free" in page
    app.config.update(SEAT_PRICE=1999, STRIPE_TAX_RATE_ID="txr_vat20", TRIAL_DAYS=30)
    page = anon.get("/welcome").get_data(as_text=True)
    assert "£19.99 per user a month plus VAT" in page and "30 days free" in page and "30-day trial" in page
    data = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S).group(1))
    assert data["offers"]["price"] == "19.99" and data["offers"]["priceCurrency"] == "GBP"


def test_book_a_demo_only_with_a_safe_address(app, anon):
    assert "Book a demo" not in anon.get("/welcome").get_data(as_text=True)
    app.config["DEMO_URL"] = "javascript:alert(1)"
    assert "Book a demo" not in anon.get("/welcome").get_data(as_text=True)
    app.config["DEMO_URL"] = "https://example.com/f/abc123"
    page = anon.get("/welcome").get_data(as_text=True)
    assert page.count('href="https://example.com/f/abc123"') == 2  # hero and the final call to action


def test_footer_company_line_and_legal_links(app, anon):
    page = anon.get("/welcome").get_data(as_text=True)
    line = page.split('class="lp-wrap lp-legal-line"')[1]
    assert "Collinalitics Ltd." in line and "number" not in line
    for doc in ("terms", "privacy", "dpa", "cookies", "accessibility"):
        assert f'href="/legal/{doc}"' in page
    app.config.update(LEGAL_COMPANY_NUMBER="12345678", LEGAL_ADDRESS="1 High Street, Edinburgh EH1 1AA",
                      LEGAL_EMAIL="hello@example.co.uk")
    page = anon.get("/welcome").get_data(as_text=True)
    assert "number 12345678" in page and "1 High Street" in page and "mailto:hello@example.co.uk" in page


def test_signed_in_people_go_to_their_workspace(client):
    assert client.get("/welcome").headers["Location"].endswith("/")


def test_accessibility_statement(anon):
    page = anon.get("/legal/accessibility").get_data(as_text=True)
    assert "WCAG" in page and "2.2" in page
