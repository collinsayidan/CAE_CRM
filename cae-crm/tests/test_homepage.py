import json
import re



def test_homepage_sections_and_true_claims_only(anon):
    page = anon.get("/welcome").get_data(as_text=True)
    assert page.count("<h1") == 1 and "Win more customers. Serve them better. Get paid faster." in page
    for heading in ("Everything you need in one place", "See your whole business at a glance", "What others charge extra for",
                    "Why businesses choose CAE CRM", "Security built in", "Simple pricing", "Frequently asked questions"):
        assert f">{heading}</h2>" in page, heading
    for anchor in ("features", "pricing", "security", "faq"):
        assert f'id="{anchor}"' in page and f'href="#{anchor}"' in page
    # Nothing invented: no reviews, ratings or uptime figures, and sample figures are labelled.
    for invented in ("★", "⭐", "99.95", "testimonial", "Trusted by"):
        assert invented not in page
    assert "Sample data" in page
    # Nothing loaded from other websites.
    assert not re.search(r'<(script|link)[^>]+(src|href)="https?://(?!localhost)', page)


def test_price_trial_and_vat_come_from_settings(app, anon):
    page = anon.get("/welcome").get_data(as_text=True)
    assert "<b>£15</b> per user a month" in page and "plus VAT" not in page and "14-day free trial" in page
    app.config.update(SEAT_PRICE=1999, STRIPE_TAX_RATE_ID="txr_vat20", TRIAL_DAYS=30)
    page = anon.get("/welcome").get_data(as_text=True)
    assert "<b>£19.99</b> per user a month plus VAT" in page and "30-day free trial" in page
    data = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S).group(1))
    assert data["offers"]["price"] == "19.99" and data["offers"]["priceCurrency"] == "GBP"


def test_book_a_demo_only_with_a_safe_address(app, anon):
    assert "Book a demo" not in anon.get("/welcome").get_data(as_text=True)
    app.config["DEMO_URL"] = "javascript:alert(1)"
    assert "Book a demo" not in anon.get("/welcome").get_data(as_text=True)
    app.config["DEMO_URL"] = "https://example.com/f/abc123"
    page = anon.get("/welcome").get_data(as_text=True)
    assert page.count('href="https://example.com/f/abc123"') == 3  # hero, final call to action, footer


def test_faq_structured_data_and_company_line(app, anon):
    page = anon.get("/welcome").get_data(as_text=True)
    blocks = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)]
    faq = next(b for b in blocks if b["@type"] == "FAQPage")
    assert len(faq["mainEntity"]) == 5 and "Where is my data stored?" not in page
    assert "Collinalitics Ltd." in page and "number" not in page.split("lp-legal-line")[1]
    app.config.update(LEGAL_DATA_REGION="London (eu-west-2)", LEGAL_COMPANY_NUMBER="12345678",
                      LEGAL_ADDRESS="1 High Street, Edinburgh EH1 1AA", LEGAL_EMAIL="hello@example.co.uk")
    page = anon.get("/welcome").get_data(as_text=True)
    assert "In London (eu-west-2)." in page and "number 12345678" in page and "mailto:hello@example.co.uk" in page


def test_signed_in_people_go_to_their_workspace(client):
    assert client.get("/welcome").headers["Location"].endswith("/")


def test_accessibility_statement(anon):
    page = anon.get("/legal/accessibility").get_data(as_text=True)
    assert "WCAG" in page and "2.2" in page
    assert 'href="/legal/accessibility"' in anon.get("/welcome").get_data(as_text=True)
