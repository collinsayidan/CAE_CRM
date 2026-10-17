"""SQLite schema, connection handling and demo seed data for CAE CRM."""

import random
import sqlite3
from datetime import date, datetime, timedelta

from flask import current_app, g

from ukfmt import add_months, vat_amount, STANDARD_VAT_RATE

STAGES = [("Lead", 10), ("Qualified", 30), ("Proposal", 50), ("Negotiation", 70), ("Closing", 90)]
OPEN_STAGES = [name for name, _ in STAGES]
STAGE_PROBABILITY = dict(STAGES) | {"Won": 100, "Lost": 0}
OWNERS = ["Amara Okafor", "James Whitfield", "Priya Nair", "Callum Fraser"]
SOURCES = ["Referral", "Website", "Outbound", "Event", "Partner"]
LAWFUL_BASES = ["Consent", "Contract", "Legitimate interests", "Legal obligation"]
ACTIVITY_KINDS = ["Call", "Meeting", "Email", "Task"]
MONTHLY_TARGET = 15_670_000  # £156,700 in pence

SCHEMA = """
CREATE TABLE companies (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    company_no TEXT,
    vat_no TEXT,
    industry TEXT,
    address TEXT,
    city TEXT,
    postcode TEXT,
    region TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE contacts (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    role TEXT,
    email TEXT,
    phone TEXT,
    lawful_basis TEXT NOT NULL,
    marketing_consent INTEGER NOT NULL DEFAULT 0,
    consent_date TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE deals (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    value INTEGER NOT NULL,
    stage TEXT NOT NULL,
    probability INTEGER NOT NULL,
    owner TEXT NOT NULL,
    source TEXT NOT NULL,
    close_date TEXT NOT NULL,
    closed_at TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE activities (
    id INTEGER PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    deal_id INTEGER REFERENCES deals(id) ON DELETE SET NULL,
    kind TEXT NOT NULL,
    subject TEXT NOT NULL,
    owner TEXT NOT NULL,
    due_at TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE invoices (
    id INTEGER PRIMARY KEY,
    number TEXT NOT NULL UNIQUE,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    net INTEGER NOT NULL,
    vat_rate INTEGER NOT NULL,
    vat INTEGER NOT NULL,
    issue_date TEXT NOT NULL,
    due_date TEXT NOT NULL,
    paid_date TEXT
);
CREATE TABLE projects (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    deal_id INTEGER REFERENCES deals(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    owner TEXT NOT NULL,
    status TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    due_date TEXT NOT NULL
);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(path, today, seed=True):
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    if seed:
        seed_db(conn, today)
    conn.commit()
    conn.close()


def next_invoice_number(conn):
    row = conn.execute("SELECT MAX(id) FROM invoices").fetchone()
    return f"CAE-{(row[0] or 0) + 1001:06d}"


# --- Demo data (fictional UK businesses) -----------------------------------

COMPANIES = [
    ("Thistle & Pine Hotels Ltd", "SC512345", "GB284716590", "Hospitality", "14 Princes Street", "Edinburgh", "EH2 2AN", "Scotland"),
    ("Mersey Freight Ltd", "08451236", "GB193847562", "Logistics", "3 Brunswick Dock", "Liverpool", "L3 4AF", "North West"),
    ("Kestrel Retail Group plc", "04928173", "GB302918476", "Retail", "22 Park Row", "Leeds", "LS1 5JD", "Yorkshire"),
    ("Brightwater Utilities Ltd", "09182736", "GB475610293", "Utilities", "1 Temple Quay", "Bristol", "BS1 6DZ", "South West"),
    ("Harbourline Logistics Ltd", "07364518", "GB561029384", "Logistics", "Ocean Gate, Town Quay", "Southampton", "SO14 3TJ", "South East"),
    ("Oakmoor Health Ltd", "10293847", "GB629384710", "Healthcare", "8 Colmore Row", "Birmingham", "B3 2NS", "West Midlands"),
    ("Clydeside Engineering Ltd", "SC401928", "GB738291045", "Manufacturing", "90 St Vincent Street", "Glasgow", "G2 5UB", "Scotland"),
    ("Pennine Foods Ltd", "06519284", "GB847102938", "Food & Drink", "11 Piccadilly", "Manchester", "M1 3BN", "North West"),
    ("Cardiff Bay Studios Ltd", "11928374", "GB910283746", "Media", "Pierhead Street", "Cardiff", "CF10 4PH", "Wales"),
    ("Fenwick & Shaw LLP", "OC398271", "GB120394857", "Legal", "40 Gresham Street", "London", "EC2V 7BN", "London"),
    ("Northgate Housing Association", "12039485", "GB231049586", "Housing", "5 Grey Street", "Newcastle upon Tyne", "NE1 6EE", "North East"),
    ("Lough Marine Services Ltd", "NI612938", "GB342059687", "Marine", "Airport Road West", "Belfast", "BT3 9ED", "Northern Ireland"),
    ("Cotswold Craft Brewers Ltd", "13048596", "GB453061728", "Food & Drink", "2 Market Place", "Cirencester", "GL7 2PE", "South West"),
    ("Granite City Energy Ltd", "SC623049", "GB564072839", "Energy", "15 Union Street", "Aberdeen", "AB11 6BA", "Scotland"),
]
FIRST_NAMES = ["Eilidh", "Rhys", "Siobhan", "Oliver", "Aisha", "Tom", "Niamh", "Harry", "Zara", "Euan", "Grace", "Dev", "Ffion", "Kwame", "Isla", "Ravi"]
LAST_NAMES = ["MacLeod", "Evans", "O'Neill", "Patel", "Hughes", "Campbell", "Ahmed", "Taylor", "Morgan", "Brown", "Jones", "Doyle"]
ROLES = ["Operations Director", "Head of Procurement", "Finance Director", "IT Manager", "Managing Director", "Commercial Lead"]
DEAL_TITLES = [
    "Fleet licence expansion", "Integration build", "Premium SLA", "Annual renewal", "Seat true-up",
    "Regional expansion", "Data migration", "Onboarding package", "Multi-site rollout", "Analytics add-on",
    "Support uplift", "Pilot programme", "Payroll module", "Compliance pack",
]


def seed_db(conn, today):
    rng = random.Random(42)
    now = datetime.combine(today, datetime.min.time())
    created = (today - timedelta(days=400)).isoformat()

    for c in COMPANIES:
        conn.execute(
            "INSERT INTO companies (name, company_no, vat_no, industry, address, city, postcode, region, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (*c, created),
        )
    company_ids = [r[0] for r in conn.execute("SELECT id FROM companies")]
    domains = {r[0]: r[1] for r in conn.execute("SELECT id, name FROM companies")}

    # Contacts. 07700 900xxx is Ofcom's range reserved for drama, so never a real number.
    for cid in company_ids:
        domain = domains[cid].split()[0].lower().replace("&", "") + ".co.uk"
        for _ in range(rng.randint(1, 2)):
            first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
            consent = rng.random() < 0.6
            conn.execute(
                "INSERT INTO contacts (company_id, first_name, last_name, role, email, phone, lawful_basis,"
                " marketing_consent, consent_date, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (cid, first, last, rng.choice(ROLES),
                 f"{first}.{last}@{domain}".lower().replace("'", ""),
                 f"+44 7700 900{rng.randint(0, 999):03d}",
                 rng.choice(LAWFUL_BASES[:3]), int(consent),
                 (today - timedelta(days=rng.randint(10, 300))).isoformat() if consent else None,
                 created),
            )

    def add_deal(stage, value, close_date, closed_at, created_at):
        cur = conn.execute(
            "INSERT INTO deals (company_id, title, value, stage, probability, owner, source, close_date, closed_at, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (rng.choice(company_ids), rng.choice(DEAL_TITLES), value, stage, STAGE_PROBABILITY[stage],
             rng.choice(OWNERS), rng.choice(SOURCES), close_date.isoformat(),
             closed_at.isoformat() if closed_at else None, created_at.isoformat()),
        )
        return cur.lastrowid

    # Won revenue for each of the last 12 months (the current month is partial).
    this_month = today.replace(day=1)
    won = []
    for back in range(11, -1, -1):
        month = add_months(this_month, -back)
        last_day = (add_months(month, 1) - timedelta(days=1)).day if back else today.day
        goal = MONTHLY_TARGET * rng.uniform(0.45, 1.08) * (today.day / 30 if back == 0 else 1)
        parts = rng.randint(2, 4)
        for _ in range(parts):
            value = int(goal / parts * rng.uniform(0.7, 1.3)) // 1000 * 1000
            closed = month.replace(day=rng.randint(1, last_day))
            deal_id = add_deal("Won", value, closed, closed, closed - timedelta(days=rng.randint(20, 95)))
            won.append((deal_id, value, closed))

    for _ in range(22):
        closed = today - timedelta(days=rng.randint(1, 360))
        add_deal("Lost", rng.randint(80, 600) * 10_000, closed, closed, closed - timedelta(days=rng.randint(15, 80)))

    weights = [14, 11, 9, 7, 6]
    for _ in range(47):
        stage = rng.choices(OPEN_STAGES, weights)[0]
        add_deal(stage, rng.randint(90, 600) * 10_000, today + timedelta(days=rng.randint(3, 100)), None,
                 today - timedelta(days=rng.randint(5, 70)))

    # Invoices for won deals, in issue order so numbers run sequentially.
    rows = conn.execute(
        "SELECT id, company_id, title, value, closed_at FROM deals WHERE stage='Won' ORDER BY closed_at"
    ).fetchall()
    for deal_id, cid, title, value, closed_at in rows:
        issue = date.fromisoformat(closed_at) + timedelta(days=2)
        if issue > today:
            continue
        due = issue + timedelta(days=30)
        paid = None
        if due < today - timedelta(days=10) or (issue < today - timedelta(days=12) and rng.random() < 0.5):
            paid = min(today, issue + timedelta(days=rng.randint(10, 45))).isoformat()
        if due < today and rng.random() < 0.12:
            paid = None  # a few overdue
        conn.execute(
            "INSERT INTO invoices (number, company_id, description, net, vat_rate, vat, issue_date, due_date, paid_date)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (next_invoice_number(conn), cid, title, value, STANDARD_VAT_RATE,
             vat_amount(value, STANDARD_VAT_RATE), issue.isoformat(), due.isoformat(), paid),
        )

    # Delivery projects for recently won deals.
    for deal_id, cid, title, value, closed_at in rows[-14:]:
        progress = rng.choice([100, 100, 85, 60, 40, 20, 5])
        status = "Complete" if progress == 100 else rng.choice(["On track", "On track", "At risk", "Blocked"])
        conn.execute(
            "INSERT INTO projects (company_id, deal_id, name, owner, status, progress, due_date) VALUES (?,?,?,?,?,?,?)",
            (cid, deal_id, f"Deliver: {title}", rng.choice(OWNERS), status, progress,
             (date.fromisoformat(closed_at) + timedelta(days=rng.randint(30, 120))).isoformat()),
        )

    subjects = {
        "Call": ["Discovery call", "Pricing follow-up", "Renewal check-in"],
        "Meeting": ["On-site demo", "Quarterly business review", "Contract walkthrough"],
        "Email": ["Send proposal", "Share case study", "Confirm DPA signed"],
        "Task": ["Update forecast", "Prepare SOW", "Credit check via Companies House"],
    }
    open_deals = conn.execute(f"SELECT id, company_id, owner FROM deals WHERE stage IN ({','.join('?' * len(OPEN_STAGES))})",
                              OPEN_STAGES).fetchall()
    for _ in range(28):
        deal_id, cid, owner = rng.choice(open_deals)
        kind = rng.choice(ACTIVITY_KINDS)
        due = now + timedelta(days=rng.randint(-6, 14), hours=rng.choice([9, 10, 11, 13, 14, 15, 16]),
                              minutes=rng.choice([0, 30]))
        conn.execute(
            "INSERT INTO activities (company_id, deal_id, kind, subject, owner, due_at, done) VALUES (?,?,?,?,?,?,?)",
            (cid, deal_id, kind, rng.choice(subjects[kind]), owner, due.isoformat(timespec="minutes"),
             int(due.date() < today and rng.random() < 0.8)),
        )
