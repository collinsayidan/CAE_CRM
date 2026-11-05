import json
import re


def test_homepage_is_short_and_makes_true_claims_only(anon):
    page = anon.get("/welcome").get_data(as_text=True)
    assert page.count("<h1") == 1
    headline = re.sub(r"<[^>]+>", "", re.search(r"<h1>(.*?)</h1>", page, re.S).group(1))
    assert headline == "The CRM that already knows how UK business works."
    for heading in ("Sales, support and invoicing, working from the same records", "Up and running this afternoon",
                    "What you'd pay extra for elsewhere, included", "Set up your business in two minutes.",
                    "Good to know before you start"):
        assert f">{heading}</h2>" in page, heading
    for tile in ("Contacts, companies and deals", "Support tickets with real service levels", "Invoices HMRC would recognise",
                 "UK GDPR built in", "Create your workspace", "Bring your customers in", "Invite your team"):
        assert f"<h3>{tile}</h3>" in page, tile
    assert page.count("<section") == 6  # hero, features, how it works, comparison, pricing, questions
    # Nothing invented: no reviews, ratings or uptime figures, and sample figures are labelled.
    for invented in ("★", "⭐", "99.95", "testimonial", "Trusted by"):
        assert invented not in page
    assert "Sample data" in page and "Won in October" in page  # the sample tracker shows the current month (tests: 16 Oct)
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


def test_questions_and_calculator_use_real_settings(app, anon):
    page = anon.get("/welcome").get_data(as_text=True)
    # The FAQ works without JavaScript: native details, one open at a time.
    assert page.count('<details class="lp-q" name="faq"') == 7
    assert "No. You get 14 days free" in page and "£15 per user a month, paid monthly" in page
    assert "server in Germany" in page and 'href="/legal/privacy"' in page
    # The team-size calculator starts hidden (it needs JavaScript) and works from the configured price.
    assert 'data-seat="1500"' in page and '<div class="lp-calc" hidden>' in page and "£75.00" in page



def test_launch_film_plays_from_our_own_site_with_captions(anon):
    page = anon.get("/welcome").get_data(as_text=True)
    assert "Watch the film" in page and 'data-lp-film-dialog' in page
    # Without scripts the link still plays the film: it points at the file itself.
    assert re.search(r'<a class="lp-film-link" href="/static/film/cae-crm-launch-60s\.mp4(\?v=\w+)?"', page)
    assert '<track kind="captions" srclang="en"' in page and 'preload="none"' in page
    for path, kind in (("film/cae-crm-launch-60s.mp4", "video/mp4"), ("film/poster.jpg", "image/jpeg"), ("film/captions-en.vtt", "text/vtt")):
        resp = anon.get(f"/static/{path}")
        assert resp.status_code == 200 and resp.mimetype == kind, path
        resp.close()
    captions = anon.get("/static/film/captions-en.vtt").get_data(as_text=True)
    assert captions.startswith("WEBVTT") and "Try it free for 14 days. No card needed." in captions
