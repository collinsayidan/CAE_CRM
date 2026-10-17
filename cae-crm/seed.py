"""Sample data for a new workspace, so a business can explore CAE CRM before adding its own records.
Every company, person and number here is fictional."""

import random
from datetime import date, datetime, timedelta

from db import (ACTIVITY_KINDS, CALL_OUTCOMES, LAWFUL_BASES, OPEN_STAGES, SOURCES, STAGE_PROBABILITY,
                TICKET_PRIORITIES, TICKET_SLA_HOURS, TICKET_SOURCES, next_invoice_number)
from ukfmt import add_months, add_working_hours, vat_amount

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
FIRST_NAMES = ["Eilidh", "Rhys", "Siobhan", "Oliver", "Aisha", "Tom", "Niamh", "Harry", "Zara", "Euan", "Grace", "Dev",
               "Ffion", "Kwame", "Isla", "Ravi"]
LAST_NAMES = ["MacLeod", "Evans", "O'Neill", "Patel", "Hughes", "Campbell", "Ahmed", "Taylor", "Morgan", "Brown", "Jones", "Doyle"]
ROLES = ["Operations Director", "Head of Procurement", "Finance Director", "IT Manager", "Managing Director", "Commercial Lead"]
COLLEAGUES = ["Amara Okafor", "James Whitfield", "Priya Nair"]
# (name, sku, unit price in pence, VAT rate, billing)
PRODUCTS = [
    ("Platform licence (per site)", "LIC-SITE", 450_000, 20, "Annual"),
    ("Additional user seat", "LIC-SEAT", 4_500, 20, "Monthly"),
    ("Onboarding package", "SVC-ONB", 650_000, 20, "One-off"),
    ("Data migration", "SVC-MIG", 380_000, 20, "One-off"),
    ("Premium support SLA", "SUP-PREM", 120_000, 20, "Monthly"),
    ("On-site training day", "SVC-TRN", 95_000, 20, "One-off"),
    ("Analytics add-on", "ADD-ANL", 210_000, 20, "Annual"),
    ("Printed user guides (box of 20)", "MAT-GUIDE", 18_000, 0, "One-off"),
]
DEAL_TITLES = ["Fleet licence expansion", "Integration build", "Premium SLA", "Annual renewal", "Seat true-up",
               "Regional expansion", "Data migration", "Onboarding package", "Multi-site rollout", "Analytics add-on",
               "Support uplift", "Pilot programme", "Payroll module", "Compliance pack"]
NOTES = ["Budget confirmed for Q1. Finance Director wants a phased rollout.",
         "Asked for references from another {industry} customer.",
         "Procurement need our DPA and ISO certificate before signing.",
         "Champion is moving roles in January; introduce the new Ops lead.",
         "Competitor quoted 15% lower but without on-site training."]
TICKET_SUBJECTS = [("Can't export the monthly report", "Problem"), ("Invoice shows the wrong PO number", "Billing"),
                   ("How do we add a new site?", "Product question"), ("Users locked out after password reset", "Problem"),
                   ("Request: dark mode on mobile", "Feature request"), ("VAT missing from last invoice", "Billing"),
                   ("Slow loading on Monday mornings", "Problem"), ("Change of billing address", "Billing")]


def seed_workspace(db, ws, today, owner_name, monthly_target):
    """Fill workspace `ws` with a year of believable UK sales history."""
    rng = random.Random(42)
    now = datetime.combine(today, datetime.min.time()).replace(hour=11)
    created = (today - timedelta(days=400)).isoformat()
    owners = [owner_name] + COLLEAGUES

    companies = []
    for name, company_no, vat_no, industry, address, city, postcode, region in COMPANIES:
        slug = name.split()[0].lower().replace("&", "")
        cid = db.insert("companies", workspace_id=ws, name=name, company_no=company_no, vat_no=vat_no, industry=industry,
                        address=address, city=city, postcode=postcode, region=region, website=f"https://{slug}.co.uk",
                        phone=f"+44 7700 900{rng.randint(0, 999):03d}", owner=rng.choice(owners), created_at=created)
        companies.append((cid, name, industry, slug))

    # People. 07700 900xxx is Ofcom's range reserved for drama, so never a real number.
    contacts = {}
    for cid, name, industry, slug in companies:
        contacts[cid] = []
        for _ in range(rng.randint(1, 3)):
            first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
            consent = rng.random() < 0.6
            contacts[cid].append(db.insert(
                "contacts", workspace_id=ws, company_id=cid, first_name=first, last_name=last, role=rng.choice(ROLES),
                email=f"{first}.{last}@{slug}.co.uk".lower().replace("'", ""), phone=f"+44 7700 900{rng.randint(0, 999):03d}",
                lawful_basis=rng.choice(LAWFUL_BASES[:3]), marketing_consent=int(consent),
                consent_date=(today - timedelta(days=rng.randint(10, 300))).isoformat() if consent else None,
                lifecycle_stage="Lead", lead_status=rng.choice(["New", "Attempted to contact", "Connected"]),
                owner=rng.choice(owners), created_at=created))
    # A few unattached leads, as from a web form.
    for first, last in [("Callum", "Fraser"), ("Megan", "Lloyd"), ("Sanjay", "Mehta")]:
        db.insert("contacts", workspace_id=ws, company_id=None, first_name=first, last_name=last, role="",
                  email=f"{first}.{last}@example.co.uk".lower(), phone="", lawful_basis="Consent", marketing_consent=1,
                  consent_date=(today - timedelta(days=3)).isoformat(), lifecycle_stage="Subscriber",
                  lead_status="New", owner=owner_name, created_at=(today - timedelta(days=3)).isoformat())

    products = []
    for name, sku, price, rate, billing in PRODUCTS:
        products.append((db.insert("products", workspace_id=ws, name=name, sku=sku, description="", unit_price=price,
                                   vat_rate=rate, billing=billing, active=1, created_at=created), name, price, rate))

    def add_deal(stage, value, close_date, closed_at, created_at):
        cid = rng.choice(companies)[0]
        contact = rng.choice(contacts[cid])
        deal_id = db.insert("deals", workspace_id=ws, company_id=cid, contact_id=contact, title=rng.choice(DEAL_TITLES),
                            value=value, stage=stage, probability=STAGE_PROBABILITY[stage], owner=rng.choice(owners),
                            source=rng.choice(SOURCES), close_date=close_date.isoformat(),
                            closed_at=closed_at.isoformat() if closed_at else None, created_at=created_at.isoformat())
        db.insert("engagements", workspace_id=ws, kind="system", subject="Deal created", body=None, outcome=None,
                  author="CAE CRM", occurred_at=f"{created_at.isoformat()}T09:00", company_id=cid, contact_id=contact,
                  deal_id=deal_id, ticket_id=None)
        return deal_id, cid, contact

    # Won revenue for each of the last 12 months (the current month is partial).
    this_month = today.replace(day=1)
    for back in range(11, -1, -1):
        month = add_months(this_month, -back)
        last_day = (add_months(month, 1) - timedelta(days=1)).day if back else today.day
        goal = monthly_target * rng.uniform(0.45, 1.08) * (today.day / 30 if back == 0 else 1)
        parts = rng.randint(2, 4)
        for _ in range(parts):
            value = int(goal / parts * rng.uniform(0.7, 1.3)) // 1000 * 1000
            closed = month.replace(day=rng.randint(1, last_day))
            _, cid, contact = add_deal("Won", value, closed, closed, closed - timedelta(days=rng.randint(20, 95)))
            db.execute("UPDATE contacts SET lifecycle_stage='Customer' WHERE id=?", (contact,))

    for _ in range(22):
        closed = today - timedelta(days=rng.randint(1, 360))
        add_deal("Lost", rng.randint(80, 600) * 10_000, closed, closed, closed - timedelta(days=rng.randint(15, 80)))

    # Open deals are built from line items, so their values add up.
    for _ in range(40):
        stage = rng.choices(OPEN_STAGES, [14, 11, 9, 7, 6])[0]
        deal_id, cid, contact = add_deal(stage, 0, today + timedelta(days=rng.randint(3, 100)), None,
                                         today - timedelta(days=rng.randint(5, 70)))
        total = 0
        for pid, pname, price, rate in rng.sample(products, rng.randint(1, 3)):
            qty = rng.choice([1, 1, 2, 3, 5, 10]) if price < 50_000 else rng.choice([1, 1, 2, 3])
            discount = rng.choice([0, 0, 0, 5, 10])
            db.insert("line_items", workspace_id=ws, deal_id=deal_id, product_id=pid, name=pname, quantity=qty,
                      unit_price=price, discount_pct=discount, vat_rate=rate)
            total += qty * price * (100 - discount) // 100
        db.execute("UPDATE deals SET value=? WHERE id=?", (total, deal_id))
        db.execute("UPDATE contacts SET lifecycle_stage='Opportunity', lead_status='Open deal' "
                   "WHERE id=? AND lifecycle_stage <> 'Customer'", (contact,))

    # Invoices for won deals, in issue order so numbers run sequentially.
    won = db.execute("SELECT id, company_id, title, value, closed_at FROM deals WHERE workspace_id=? AND stage='Won' "
                     "ORDER BY closed_at", (ws,)).fetchall()
    for deal_id, cid, title, value, closed_at in won:
        issue = date.fromisoformat(closed_at) + timedelta(days=2)
        if issue > today:
            continue
        due = issue + timedelta(days=30)
        paid = None
        if due < today - timedelta(days=10) or (issue < today - timedelta(days=12) and rng.random() < 0.5):
            paid = min(today, issue + timedelta(days=rng.randint(10, 45))).isoformat()
        if due < today and rng.random() < 0.12:
            paid = None  # a few overdue
        vat = vat_amount(value, 20)
        inv = db.insert("invoices", workspace_id=ws, number=next_invoice_number(db, ws, "INV"), company_id=cid,
                        deal_id=deal_id, description=title, net=value, vat_rate=20, vat=vat, issue_date=issue.isoformat(),
                        due_date=due.isoformat(), paid_date=paid)
        db.insert("invoice_lines", workspace_id=ws, invoice_id=inv, description=title, quantity=1, unit_price=value,
                  discount_pct=0, vat_rate=20, net=value, vat=vat)

    # Delivery projects for recently won deals.
    for deal_id, cid, title, value, closed_at in won[-14:]:
        progress = rng.choice([100, 100, 85, 60, 40, 20, 5])
        status = "Complete" if progress == 100 else rng.choice(["On track", "On track", "At risk", "Blocked"])
        db.insert("projects", workspace_id=ws, company_id=cid, deal_id=deal_id, name=f"Deliver: {title}",
                  owner=rng.choice(owners), status=status, progress=progress,
                  due_date=(date.fromisoformat(closed_at) + timedelta(days=rng.randint(30, 120))).isoformat())

    # Tasks and meetings around today.
    subjects = {
        "Call": ["Discovery call", "Pricing follow-up", "Renewal check-in"],
        "Meeting": ["On-site demo", "Quarterly business review", "Contract walkthrough"],
        "Email": ["Send proposal", "Share case study", "Confirm DPA signed"],
        "Task": ["Update forecast", "Prepare SOW", "Credit check via Companies House"],
    }
    open_deals = db.execute(f"SELECT id, company_id, contact_id, owner FROM deals WHERE workspace_id=? "
                            f"AND stage IN ({','.join('?' * len(OPEN_STAGES))})", [ws, *OPEN_STAGES]).fetchall()
    for _ in range(28):
        deal_id, cid, contact, owner = rng.choice(open_deals)
        kind = rng.choice(ACTIVITY_KINDS)
        due = now + timedelta(days=rng.randint(-6, 14), hours=rng.choice([-2, -1, 0, 2, 3, 4, 5]), minutes=rng.choice([0, 30]))
        db.insert("activities", workspace_id=ws, company_id=cid, contact_id=contact, deal_id=deal_id, ticket_id=None,
                  kind=kind, subject=rng.choice(subjects[kind]), owner=owner, due_at=due.isoformat(timespec="minutes"),
                  done=int(due.date() < today and rng.random() < 0.8))

    # Logged notes, calls, emails and meetings, so record timelines aren't empty.
    for deal_id, cid, contact, owner in open_deals[:24]:
        industry = next(c[2] for c in companies if c[0] == cid)
        for _ in range(rng.randint(1, 3)):
            kind = rng.choice(["note", "call", "email", "meeting"])
            when = now - timedelta(days=rng.randint(1, 50), hours=rng.randint(0, 5))
            subject, body, outcome = None, rng.choice(NOTES).format(industry=industry.lower()), None
            if kind == "call":
                outcome = rng.choice(CALL_OUTCOMES)
                subject = "Call"
            elif kind == "email":
                subject = rng.choice(["Proposal attached", "Following up on pricing", "Next steps"])
            elif kind == "meeting":
                subject = rng.choice(["Discovery meeting", "Demo", "Commercial review"])
            db.insert("engagements", workspace_id=ws, kind=kind, subject=subject, body=body, outcome=outcome,
                      author=owner, occurred_at=when.isoformat(timespec="minutes"), company_id=cid,
                      contact_id=contact, deal_id=deal_id, ticket_id=None)

    # Support tickets, some inside their service levels and some breached.
    for i, (subject, category) in enumerate(TICKET_SUBJECTS * 2):
        cid = rng.choice(companies)[0]
        priority = rng.choice(TICKET_PRIORITIES)
        # Customers get in touch during the working day.
        opened = (now - timedelta(days=rng.randint(0, 12))).replace(hour=rng.randint(9, 16), minute=rng.choice([5, 20, 35, 50]))
        while opened.weekday() > 4:
            opened -= timedelta(days=1)
        opened = min(opened, now - timedelta(minutes=30))
        first_hours, resolve_hours = TICKET_SLA_HOURS[priority]
        status = rng.choice(["New", "Waiting on us", "Waiting on contact", "Closed", "Closed"]) if i > 3 else "New"
        responded = min(now, add_working_hours(opened, first_hours * rng.uniform(0.3, 1.4))) if status != "New" else None
        closed = min(now, add_working_hours(opened, resolve_hours * rng.uniform(0.4, 1.3))) if status == "Closed" else None
        tid = db.insert("tickets", workspace_id=ws, company_id=cid, contact_id=rng.choice(contacts[cid]), subject=subject,
                        description="", status=status, priority=priority, category=category,
                        source=rng.choice(TICKET_SOURCES), owner=rng.choice(owners), created_at=opened.isoformat(timespec="minutes"),
                        first_response_due=add_working_hours(opened, first_hours).isoformat(timespec="minutes"),
                        resolution_due=add_working_hours(opened, resolve_hours).isoformat(timespec="minutes"),
                        first_responded_at=responded.isoformat(timespec="minutes") if responded else None,
                        closed_at=closed.isoformat(timespec="minutes") if closed else None)
        db.insert("engagements", workspace_id=ws, kind="system", subject="Ticket opened", body=None, outcome=None,
                  author="CAE CRM", occurred_at=opened.isoformat(timespec="minutes"), company_id=cid, contact_id=None,
                  deal_id=None, ticket_id=tid)
