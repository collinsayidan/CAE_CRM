"""Database access for CAE CRM: SQLite locally, PostgreSQL in production.

Every business record belongs to a workspace (one subscribing business). Queries
must always filter on workspace_id; see core.py for the scoped helpers.
"""

import re
import sqlite3
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flask import current_app, g

try:
    import psycopg
except ImportError:  # only needed when DATABASE_URL points at PostgreSQL
    psycopg = None

STAGES = [("Lead", 10), ("Qualified", 30), ("Proposal", 50), ("Negotiation", 70), ("Closing", 90)]
OPEN_STAGES = [name for name, _ in STAGES]
STAGE_PROBABILITY = dict(STAGES) | {"Won": 100, "Lost": 0}
SOURCES = ["Referral", "Website", "Outbound", "Event", "Partner"]
LAWFUL_BASES = ["Consent", "Contract", "Legitimate interests", "Legal obligation"]
ACTIVITY_KINDS = ["Call", "Meeting", "Email", "Task"]
LIFECYCLE_STAGES = ["Subscriber", "Lead", "Marketing qualified lead", "Sales qualified lead",
                    "Opportunity", "Customer", "Evangelist", "Other"]
LEAD_STATUSES = ["New", "Attempted to contact", "Connected", "Open deal", "Unqualified", "Bad timing"]
CALL_OUTCOMES = ["Connected", "Left voicemail", "No answer", "Wrong number", "Busy"]
TICKET_STATUSES = ["New", "Waiting on us", "Waiting on contact", "Closed"]
TICKET_PRIORITIES = ["Low", "Medium", "High", "Urgent"]
TICKET_SOURCES = ["Email", "Phone", "Web form", "Chat"]
TICKET_CATEGORIES = ["Billing", "Product question", "Problem", "Feature request", "Other"]
# Service levels in UK working hours (09:00-17:00, Mon-Fri, excluding bank holidays):
# (first response, resolution)
TICKET_SLA_HOURS = {"Urgent": (1, 4), "High": (4, 8), "Medium": (8, 24), "Low": (16, 40)}
BILLING_PERIODS = ["One-off", "Monthly", "Annual"]
DEFAULT_MONTHLY_TARGET = 15_670_000  # £156,700 in pence

SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces (
    id {pk},
    name TEXT NOT NULL,
    legal_name TEXT,
    address TEXT,
    city TEXT,
    postcode TEXT,
    company_no TEXT,
    vat_no TEXT,
    vat_registered INTEGER NOT NULL DEFAULT 1,
    monthly_target BIGINT NOT NULL DEFAULT 15670000,
    invoice_prefix TEXT NOT NULL DEFAULT 'INV',
    payment_terms INTEGER NOT NULL DEFAULT 30,
    created_at TEXT NOT NULL,
    reply_to TEXT,
    plan_status TEXT,
    trial_ends TEXT,
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    seats INTEGER,
    period_end TEXT,
    cancel_at_period_end INTEGER NOT NULL DEFAULT 0,
    logo TEXT,
    logo_updated TEXT,
    bank_account_name TEXT,
    bank_sort_code TEXT,
    bank_account_number TEXT,
    payment_link TEXT,
    reminders_on INTEGER NOT NULL DEFAULT 0,
    onboarding_done INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS users (
    id {pk},
    workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    failed_logins INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    created_at TEXT NOT NULL,
    job_title TEXT,
    department TEXT,
    phone TEXT,
    location TEXT,
    linkedin TEXT,
    bio TEXT,
    photo TEXT,
    photo_updated TEXT,
    totp_secret TEXT,
    totp_enabled_at TEXT,
    totp_last_step INTEGER,
    recovery_codes TEXT
);
CREATE TABLE IF NOT EXISTS companies (
    id {pk},
    workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    company_no TEXT,
    vat_no TEXT,
    industry TEXT,
    address TEXT,
    city TEXT,
    postcode TEXT,
    region TEXT,
    website TEXT,
    phone TEXT,
    owner TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contacts (
    id {pk},
    workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE,
    company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    role TEXT,
    email TEXT,
    phone TEXT,
    lawful_basis TEXT NOT NULL,
    marketing_consent INTEGER NOT NULL DEFAULT 0,
    consent_date TEXT,
    lifecycle_stage TEXT,
    lead_status TEXT,
    owner TEXT,
    created_at TEXT NOT NULL,
    unsubscribed_at TEXT,
    email_bounced_at TEXT
);
CREATE TABLE IF NOT EXISTS deals (
    id {pk},
    workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    value BIGINT NOT NULL,
    stage TEXT NOT NULL,
    probability INTEGER NOT NULL,
    owner TEXT NOT NULL,
    source TEXT NOT NULL,
    close_date TEXT NOT NULL,
    closed_at TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS activities (
    id {pk},
    workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    deal_id INTEGER REFERENCES deals(id) ON DELETE SET NULL,
    ticket_id INTEGER,
    kind TEXT NOT NULL,
    subject TEXT NOT NULL,
    owner TEXT NOT NULL,
    due_at TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS invoices (
    id {pk},
    workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE,
    number TEXT NOT NULL,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    deal_id INTEGER REFERENCES deals(id) ON DELETE SET NULL,
    description TEXT NOT NULL,
    net BIGINT NOT NULL,
    vat_rate INTEGER NOT NULL,
    vat BIGINT NOT NULL,
    issue_date TEXT NOT NULL,
    due_date TEXT NOT NULL,
    paid_date TEXT,
    xero_invoice_id TEXT,
    sent_at TEXT,
    sent_to TEXT,
    UNIQUE (workspace_id, number)
);
CREATE TABLE IF NOT EXISTS invoice_lines (
    id {pk},
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price BIGINT NOT NULL,
    discount_pct INTEGER NOT NULL DEFAULT 0,
    vat_rate INTEGER NOT NULL,
    net BIGINT NOT NULL,
    vat BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS projects (
    id {pk},
    workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    deal_id INTEGER REFERENCES deals(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    owner TEXT NOT NULL,
    status TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    due_date TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
    id {pk},
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    sku TEXT,
    description TEXT,
    unit_price BIGINT NOT NULL,
    vat_rate INTEGER NOT NULL,
    billing TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS line_items (
    id {pk},
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    deal_id INTEGER NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price BIGINT NOT NULL,
    discount_pct INTEGER NOT NULL DEFAULT 0,
    vat_rate INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS tickets (
    id {pk},
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
    contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    subject TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL,
    priority TEXT NOT NULL,
    category TEXT NOT NULL,
    source TEXT NOT NULL,
    owner TEXT NOT NULL,
    created_at TEXT NOT NULL,
    first_response_due TEXT NOT NULL,
    resolution_due TEXT NOT NULL,
    first_responded_at TEXT,
    closed_at TEXT
);
CREATE TABLE IF NOT EXISTS engagements (
    id {pk},
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    subject TEXT,
    body TEXT,
    outcome TEXT,
    author TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    contact_id INTEGER REFERENCES contacts(id) ON DELETE CASCADE,
    deal_id INTEGER REFERENCES deals(id) ON DELETE CASCADE,
    ticket_id INTEGER REFERENCES tickets(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS saved_views (
    id {pk},
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    object TEXT NOT NULL,
    name TEXT NOT NULL,
    query TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS imports (
    id {pk},
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    object TEXT NOT NULL,
    filename TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS quotes (
    id {pk},
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    number TEXT NOT NULL,
    deal_id INTEGER REFERENCES deals(id) ON DELETE SET NULL,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    terms TEXT,
    status TEXT NOT NULL,
    token TEXT NOT NULL UNIQUE,
    net BIGINT NOT NULL,
    vat BIGINT NOT NULL,
    issue_date TEXT NOT NULL,
    expiry_date TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    sent_at TEXT,
    viewed_at TEXT,
    decided_at TEXT,
    signer_name TEXT,
    signer_position TEXT,
    signer_ip TEXT,
    signer_agent TEXT,
    decline_reason TEXT,
    invoice_id INTEGER REFERENCES invoices(id) ON DELETE SET NULL,
    UNIQUE (workspace_id, number)
);
CREATE TABLE IF NOT EXISTS quote_lines (
    id {pk},
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    quote_id INTEGER NOT NULL REFERENCES quotes(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price BIGINT NOT NULL,
    discount_pct INTEGER NOT NULL DEFAULT 0,
    vat_rate INTEGER NOT NULL,
    net BIGINT NOT NULL,
    vat BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS web_forms (
    id {pk},
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    token TEXT NOT NULL UNIQUE,
    heading TEXT NOT NULL,
    intro TEXT,
    fields TEXT NOT NULL,
    button_label TEXT NOT NULL,
    thank_you TEXT NOT NULL,
    lifecycle_stage TEXT NOT NULL,
    owner TEXT NOT NULL,
    ask_consent INTEGER NOT NULL DEFAULT 1,
    consent_text TEXT,
    privacy_url TEXT,
    follow_up_task INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS form_submissions (
    id {pk},
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    form_id INTEGER NOT NULL REFERENCES web_forms(id) ON DELETE CASCADE,
    contact_id INTEGER REFERENCES contacts(id) ON DELETE CASCADE,
    data TEXT NOT NULL,
    ip TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS email_campaigns (
    id {pk},
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    subject TEXT NOT NULL,
    preheader TEXT,
    body TEXT NOT NULL,
    audience TEXT NOT NULL,
    status TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    sent_at TEXT,
    recipients INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS campaign_recipients (
    id {pk},
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    campaign_id INTEGER NOT NULL REFERENCES email_campaigns(id) ON DELETE CASCADE,
    contact_id INTEGER REFERENCES contacts(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    first_name TEXT,
    status TEXT NOT NULL,
    provider_id TEXT,
    error TEXT,
    sent_at TEXT,
    delivered_at TEXT,
    opened_at TEXT,
    clicked_at TEXT,
    bounced_at TEXT,
    unsubscribed_at TEXT
);
CREATE TABLE IF NOT EXISTS connections (
    id {pk},
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    account TEXT,
    tenant_id TEXT,
    access_token TEXT,
    refresh_token TEXT,
    expires_at TEXT,
    sync_cursor TEXT,
    last_sync_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS synced_emails (
    id {pk},
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    connection_id INTEGER NOT NULL REFERENCES connections(id) ON DELETE CASCADE,
    message_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (connection_id, message_id)
);
CREATE TABLE IF NOT EXISTS vat_returns (
    id {pk},
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    period_key TEXT NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    boxes TEXT NOT NULL,
    receipt TEXT,
    submitted_by TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    UNIQUE (workspace_id, period_key)
);
CREATE TABLE IF NOT EXISTS password_resets (
    id {pk},
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    ip TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
    id {pk},
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    user_name TEXT,
    action TEXT NOT NULL,
    target_type TEXT,
    target_id INTEGER,
    summary TEXT,
    ip TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS invoice_reminders (
    id {pk},
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    stage INTEGER NOT NULL,
    sent_to TEXT,
    sent_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notifications (
    id {pk},
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    body TEXT,
    url TEXT,
    created_at TEXT NOT NULL,
    read_at TEXT
);
"""

# Columns added after the first release. Databases created by an earlier version gain them on start-up.
ADDED_COLUMNS = {
    "users": ["workspace_id INTEGER", "job_title TEXT", "department TEXT", "phone TEXT", "location TEXT",
              "linkedin TEXT", "bio TEXT", "photo TEXT", "photo_updated TEXT", "totp_secret TEXT", "totp_enabled_at TEXT",
              "totp_last_step INTEGER", "recovery_codes TEXT"],
    "companies": ["workspace_id INTEGER", "website TEXT", "phone TEXT", "owner TEXT"],
    "contacts": ["workspace_id INTEGER", "lifecycle_stage TEXT", "lead_status TEXT", "owner TEXT", "unsubscribed_at TEXT",
                 "email_bounced_at TEXT"],
    "workspaces": ["reply_to TEXT", "plan_status TEXT", "trial_ends TEXT", "stripe_customer_id TEXT",
                   "stripe_subscription_id TEXT", "seats INTEGER", "period_end TEXT",
                   "cancel_at_period_end INTEGER NOT NULL DEFAULT 0", "logo TEXT", "logo_updated TEXT",
                   "bank_account_name TEXT", "bank_sort_code TEXT", "bank_account_number TEXT", "payment_link TEXT",
                   "reminders_on INTEGER NOT NULL DEFAULT 0", "onboarding_done INTEGER NOT NULL DEFAULT 0"],
    "deals": ["workspace_id INTEGER", "contact_id INTEGER"],
    "activities": ["workspace_id INTEGER", "contact_id INTEGER", "ticket_id INTEGER"],
    "invoices": ["workspace_id INTEGER", "deal_id INTEGER", "xero_invoice_id TEXT", "sent_at TEXT", "sent_to TEXT"],
    "projects": ["workspace_id INTEGER"],
}
SCOPED_TABLES = ["users", "companies", "contacts", "deals", "activities", "invoices", "projects"]


class Row(tuple):
    """A result row readable by position or by column name, like sqlite3.Row."""

    def __new__(cls, values, names):
        row = super().__new__(cls, values)
        row._names = names
        return row

    def keys(self):
        return self._names

    def __getitem__(self, key):
        if isinstance(key, str):
            return tuple.__getitem__(self, self._names.index(key))
        return tuple.__getitem__(self, key)


def _pg_rows(cursor):
    names = [c.name for c in cursor.description] if cursor.description else []
    return lambda values: Row(values, names)


def is_postgres(target):
    return str(target).startswith(("postgres://", "postgresql://"))


# Query settings some hosts add to their connection strings that libpq rejects
# (Vercel's Supabase integration adds supa=..., Prisma-style strings add pgbouncer=true).
_FOREIGN_PARAMS = {"supa", "pgbouncer", "connection_limit", "pool_timeout"}


def clean_postgres_url(url):
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in _FOREIGN_PARAMS]
    return urlunsplit(parts._replace(query=urlencode(query)))


class Database:
    """One connection to SQLite or PostgreSQL. Queries use SQLite-style ? placeholders everywhere."""

    def __init__(self, target):
        self.postgres = is_postgres(target)
        if self.postgres:
            if psycopg is None:
                raise RuntimeError("Install psycopg to use a PostgreSQL DATABASE_URL.")
            # No prepared statements: connection poolers in transaction mode (Supabase on port 6543,
            # PgBouncer) hand each transaction a different server connection, where they don't exist.
            self.conn = psycopg.connect(clean_postgres_url(target), row_factory=_pg_rows,
                                        prepare_threshold=None, connect_timeout=10)
            self.pk = "INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY"
        else:
            self.conn = sqlite3.connect(target)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.pk = "INTEGER PRIMARY KEY"

    def execute(self, sql, params=()):
        if self.postgres:
            sql = sql.replace("%", "%%").replace("?", "%s")
        return self.conn.execute(sql, tuple(params))

    def executescript(self, sql):
        if self.postgres:
            self.conn.execute(sql)  # psycopg runs several statements when there are no parameters
        else:
            self.conn.executescript(sql)

    def insert(self, table, **values):
        """INSERT a row and return its new id."""
        cols = ", ".join(values)
        marks = ", ".join("?" * len(values))
        return self.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks}) RETURNING id",
                            list(values.values())).fetchone()[0]

    def columns(self, table):
        if self.postgres:
            rows = self.execute("SELECT column_name FROM information_schema.columns "
                                "WHERE table_schema = current_schema() AND table_name=?", (table,))
            return {r[0] for r in rows}
        return {r[1] for r in self.execute(f"PRAGMA table_info({table})")}

    def days_between(self, later, earlier):
        """SQL for the number of days between two ISO date columns."""
        if self.postgres:
            return f"(CAST({later} AS DATE) - CAST({earlier} AS DATE))"
        return f"(julianday({later}) - julianday({earlier}))"

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()


def get_db():
    if "db" not in g:
        g.db = Database(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def migrate(db, today):
    """Bring any database up to the current schema. Safe to run on every start."""
    if db.postgres:
        # Serverless cold starts can race; one migrator at a time.
        db.execute("SELECT pg_advisory_xact_lock(4242)")
    existing = {t: db.columns(t) for t in ADDED_COLUMNS}
    upgrading = bool(existing["companies"]) and "workspace_id" not in existing["companies"]
    for table, cols in ADDED_COLUMNS.items():
        if not existing[table]:
            continue  # the table is new, and CREATE below makes it whole
        for col in cols:
            if col.split()[0] not in existing[table]:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {col}")
    if upgrading:
        # Before the new tables exist, so renaming invoices can't rewrite their references.
        _relax_v1_constraints(db)
    db.executescript(SCHEMA.format(pk=db.pk))
    # Records from the single-business version move into one workspace.
    orphans = any(db.execute(f"SELECT 1 FROM {t} WHERE workspace_id IS NULL LIMIT 1").fetchone() for t in SCOPED_TABLES)
    if orphans:
        ws = db.execute("SELECT id FROM workspaces ORDER BY id LIMIT 1").fetchone()
        ws_id = ws[0] if ws else db.insert("workspaces", name="My business", created_at=today.isoformat())
        for t in SCOPED_TABLES:
            db.execute(f"UPDATE {t} SET workspace_id=? WHERE workspace_id IS NULL", (ws_id,))
        db.execute("UPDATE contacts SET lifecycle_stage='Customer' WHERE lifecycle_stage IS NULL "
                   "AND company_id IN (SELECT company_id FROM deals WHERE stage='Won')")
        db.execute("UPDATE contacts SET lifecycle_stage='Lead' WHERE lifecycle_stage IS NULL")
    for sql in (
        "CREATE INDEX IF NOT EXISTS ix_companies_ws ON companies (workspace_id)",
        "CREATE INDEX IF NOT EXISTS ix_contacts_ws ON contacts (workspace_id)",
        "CREATE INDEX IF NOT EXISTS ix_deals_ws ON deals (workspace_id, stage)",
        "CREATE INDEX IF NOT EXISTS ix_engagements_company ON engagements (company_id)",
        "CREATE INDEX IF NOT EXISTS ix_engagements_contact ON engagements (contact_id)",
        "CREATE INDEX IF NOT EXISTS ix_engagements_deal ON engagements (deal_id)",
        "CREATE INDEX IF NOT EXISTS ix_tickets_ws ON tickets (workspace_id, status)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_invoices_number ON invoices (workspace_id, number)",
        "CREATE INDEX IF NOT EXISTS ix_quotes_ws ON quotes (workspace_id, status)",
        "CREATE INDEX IF NOT EXISTS ix_quotes_deal ON quotes (deal_id)",
        "CREATE INDEX IF NOT EXISTS ix_submissions_form ON form_submissions (form_id, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_recipients_campaign ON campaign_recipients (campaign_id, status)",
        "CREATE INDEX IF NOT EXISTS ix_recipients_provider ON campaign_recipients (provider_id)",
        "CREATE INDEX IF NOT EXISTS ix_connections_ws ON connections (workspace_id, provider)",
        "CREATE INDEX IF NOT EXISTS ix_audit_ws ON audit_events (workspace_id, id)",
        "CREATE INDEX IF NOT EXISTS ix_notifications_user ON notifications (user_id, id)",
    ):
        db.execute(sql)
    if db.postgres:
        # Supabase publishes every table in the public schema through its Data API to anyone holding the
        # project's public key. Row level security with no policies shuts that door; the app connects as
        # the tables' owner, which isn't subject to it.
        for table in re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", SCHEMA):
            db.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def _relax_v1_constraints(db):
    """Undo two rules from the single-business release: invoice numbers were unique across the whole
    database (now per workspace), and every contact had to belong to a company (leads can now stand alone)."""
    if db.postgres:
        db.execute("ALTER TABLE invoices DROP CONSTRAINT IF EXISTS invoices_number_key")
        db.execute("ALTER TABLE contacts ALTER COLUMN company_id DROP NOT NULL")
        return
    # SQLite can't change constraints in place, so rebuild both tables from the new schema.
    copies = {
        "invoices": "id, workspace_id, number, company_id, deal_id, description, net, vat_rate, vat, "
                    "issue_date, due_date, paid_date",
        "contacts": "id, workspace_id, company_id, first_name, last_name, role, email, phone, lawful_basis, "
                    "marketing_consent, consent_date, lifecycle_stage, lead_status, owner, created_at",
    }
    db.execute("PRAGMA foreign_keys = OFF")
    db.execute("PRAGMA legacy_alter_table = ON")  # keep other tables pointing at the new tables by name
    for table in copies:
        db.execute(f"ALTER TABLE {table} RENAME TO {table}_v1")
    db.executescript(SCHEMA.format(pk=db.pk))
    for table, cols in copies.items():
        db.execute(f"INSERT INTO {table} ({cols}) SELECT {cols} FROM {table}_v1")
        db.execute(f"DROP TABLE {table}_v1")
    db.execute("PRAGMA legacy_alter_table = OFF")
    db.execute("PRAGMA foreign_keys = ON")


def init_db(target, today):
    db = Database(target)
    try:
        migrate(db, today)
        db.commit()
    finally:
        db.close()


def next_quote_number(db, workspace_id):
    count = db.execute("SELECT COUNT(*) FROM quotes WHERE workspace_id=?", (workspace_id,)).fetchone()[0]
    return f"Q-{count + 1001:06d}"


def next_invoice_number(db, workspace_id, prefix):
    count = db.execute("SELECT COUNT(*) FROM invoices WHERE workspace_id=?", (workspace_id,)).fetchone()[0]
    return f"{prefix}-{count + 1001:06d}"
