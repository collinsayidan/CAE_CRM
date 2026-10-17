"""UK formatting and validation helpers: GBP, en-GB dates, postcodes, VAT,
Companies House numbers, phone numbers and the April-March financial year."""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

POSTCODE_RE = re.compile(
    r"^(GIR0AA|[A-PR-UWYZ][A-HK-Y]?\d[A-Z\d]?\d[ABD-HJLNP-UW-Z]{2})$"
)
VAT_RE = re.compile(r"^GB(\d{9}|\d{12}|GD\d{3}|HA\d{3})$")
COMPANY_NO_RE = re.compile(r"^([A-Z]{2}\d{6}|\d{8})$")
PHONE_RE = re.compile(r"^(?:\+44|0)\d{9,10}$")

STANDARD_VAT_RATE = 20  # per cent
VAT_RATES = (20, 5, 0)  # standard, reduced, zero


# --- Money (stored as integer pence) -------------------------------------

def money(pence, pennies=False):
    pence = int(pence or 0)
    sign = "-" if pence < 0 else ""
    pounds = abs(pence) / 100
    return f"{sign}£{pounds:,.2f}" if pennies else f"{sign}£{round(pounds):,}"


def money_short(pence):
    pounds = int(pence or 0) / 100
    if abs(pounds) >= 1_000_000:
        return f"£{pounds / 1_000_000:.1f}M"
    if abs(pounds) >= 1_000:
        return f"£{pounds / 1_000:.1f}K".replace(".0K", "K")
    return f"£{pounds:,.0f}"


def parse_money(raw):
    """'£12,500.50' -> 1250050 pence. Returns None when invalid or not positive."""
    cleaned = (raw or "").replace("£", "").replace(",", "").strip()
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    if value <= 0:
        return None
    return int((value * 100).quantize(Decimal("1")))


def vat_amount(net_pence, rate):
    return int((Decimal(net_pence) * Decimal(rate) / 100).quantize(Decimal("1")))


# --- Dates ----------------------------------------------------------------

def to_date(value):
    if value is None or isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value)[:10])


def uk_date(value):
    d = to_date(value)
    return d.strftime("%d/%m/%Y") if d else ""


def uk_date_short(value):
    d = to_date(value)
    return f"{d.day} {d.strftime('%b')}" if d else ""


def uk_datetime(value):
    if not value:
        return ""
    dt = datetime.fromisoformat(str(value))
    return dt.strftime("%d/%m/%Y %H:%M")


def add_months(d, n):
    month = d.month - 1 + n
    return d.replace(year=d.year + month // 12, month=month % 12 + 1, day=1)


def fy_quarter(d):
    """UK financial year runs 1 April - 31 March. Returns (label, q, start, end)."""
    fy_start_year = d.year if d.month >= 4 else d.year - 1
    q = (d.month - 4) % 12 // 3 + 1
    start = add_months(date(fy_start_year, 4, 1), (q - 1) * 3)
    end = add_months(start, 3)
    label = f"FY{fy_start_year}/{str(fy_start_year + 1)[-2:]}"
    return label, q, start, end


def vat_quarter(d):
    """Calendar VAT quarter (stagger 3: periods ending Mar/Jun/Sep/Dec)."""
    start = date(d.year, (d.month - 1) // 3 * 3 + 1, 1)
    return start, add_months(start, 3)


# --- Identifiers ------------------------------------------------------------

def normalise_postcode(raw):
    compact = re.sub(r"\s+", "", (raw or "").upper())
    if not POSTCODE_RE.match(compact):
        return None
    return f"{compact[:-3]} {compact[-3:]}"


def normalise_vat(raw):
    compact = re.sub(r"[\s-]+", "", (raw or "").upper())
    if not compact:
        return ""
    if not compact.startswith("GB"):
        compact = "GB" + compact
    return compact if VAT_RE.match(compact) else None


def normalise_company_no(raw):
    compact = re.sub(r"\s+", "", (raw or "").upper())
    if not compact:
        return ""
    if compact.isdigit() and len(compact) < 8:
        compact = compact.zfill(8)
    return compact if COMPANY_NO_RE.match(compact) else None


def normalise_phone(raw):
    compact = re.sub(r"[\s()-]+", "", raw or "")
    if not compact:
        return ""
    if not PHONE_RE.match(compact):
        return None
    national = "0" + compact[3:] if compact.startswith("+44") else compact
    return f"+44 {national[1:5]} {national[5:]}"
