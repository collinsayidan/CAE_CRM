from datetime import date

import ukfmt


def test_money():
    assert ukfmt.money(113_910_000) == "£1,139,100"
    assert ukfmt.money(123456, pennies=True) == "£1,234.56"
    assert ukfmt.money_short(15_670_000) == "£156.7K"
    assert ukfmt.money_short(20_000_000) == "£200K"


def test_parse_money():
    assert ukfmt.parse_money("£12,500.50") == 1_250_050
    assert ukfmt.parse_money("0") is None
    assert ukfmt.parse_money("abc") is None


def test_vat():
    assert ukfmt.vat_amount(10_000, 20) == 2_000
    assert ukfmt.normalise_vat("gb 123 4567 89") == "GB123456789"
    assert ukfmt.normalise_vat("123") is None
    assert ukfmt.normalise_vat("") == ""


def test_postcodes():
    for raw, want in [("eh22an", "EH2 2AN"), ("EC2V 7BN", "EC2V 7BN"), ("m1 3bn", "M1 3BN"), ("BT3 9ED", "BT3 9ED")]:
        assert ukfmt.normalise_postcode(raw) == want
    assert ukfmt.normalise_postcode("12345") is None
    assert ukfmt.normalise_postcode("QQ1 1QQ") is None


def test_company_and_phone():
    assert ukfmt.normalise_company_no("8451236") == "08451236"
    assert ukfmt.normalise_company_no("sc512345") == "SC512345"
    assert ukfmt.normalise_company_no("ABC") is None
    assert ukfmt.normalise_phone("07700 900123") == "+44 7700 900123"
    assert ukfmt.normalise_phone("+44 131 496 0000") == "+44 1314 960000"
    assert ukfmt.normalise_phone("555-1234") is None


def test_dates_and_financial_year():
    assert ukfmt.uk_date("2026-10-17") == "17/10/2026"
    assert ukfmt.fy_quarter(date(2026, 10, 17))[:2] == ("FY2026/27", 3)
    assert ukfmt.fy_quarter(date(2027, 2, 1))[:2] == ("FY2026/27", 4)
    assert ukfmt.fy_quarter(date(2026, 4, 1))[:2] == ("FY2026/27", 1)
    assert ukfmt.vat_quarter(date(2026, 10, 17)) == (date(2026, 10, 1), date(2027, 1, 1))
