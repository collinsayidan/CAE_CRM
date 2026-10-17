# CAE CRM

A UK-standard sales CRM built in Python with **Flask** and **SQLite**. It has no JavaScript framework, and the charts are rendered as inline SVG on the server.

## Run it

```bash
cd cae-crm
pip install -r requirements.txt
python app.py            # or: flask --app app run
```

Open http://127.0.0.1:5000. On first run the app creates `instance/cae_crm.sqlite3` and fills it with fictional UK demo data. To reset the data, delete that file.

For anything beyond local use, set a fixed secret key: `export CAE_SECRET_KEY=<random string>`.

## Pages

| Page | What it does |
|---|---|
| **Overview** | Shows won this month (compared with the same point last month), open pipeline and win rate. Also has a 6M/12M revenue chart against the monthly target, hot deals ranked by weighted value, the quarter quota gauge, the stage mix and upcoming activities. |
| **Pipeline** | Kanban board from Lead to Closing. You can move deals between stages or mark them Won or Lost, add deals and filter by owner. Winning a deal creates a delivery project automatically. |
| **Customers** | Searchable company list. Each company page shows its details, contacts, deals and invoices. |
| **Schedule** | Calls, meetings, emails and tasks grouped by day, with overdue items highlighted and a tick-off control. |
| **Finance** | Invoices with net, VAT and gross amounts. Shows outstanding, overdue, received this financial year and output VAT for the current VAT quarter. You can raise an invoice, mark it paid and print it. |
| **Growth** | Won revenue and win rate by lead source and by sales rep, plus average deal size and sales cycle. |
| **Projects** | Delivery projects with progress and status. |

## UK standards built in

- **Currency:** GBP (£). Money is stored as integer pence, so there are no floating-point rounding errors.
- **Dates:** DD/MM/YYYY throughout (the page language is en-GB).
- **VAT:** 20% standard, 5% reduced and 0% zero-rated. VAT is calculated per invoice. Invoices show the tax point, VAT numbers, 30-day terms and a note on the Late Payment of Commercial Debts Act.
- **Financial year:** runs 1 April to 31 March (labelled FY2026/27), with quarters for quota tracking. VAT quarters follow the calendar.
- **Validation:** UK postcodes (normalised, e.g. `eh22an` → `EH2 2AN`), Companies House numbers (including the SC, NI and OC prefixes, with a link to the Companies House register), GB VAT numbers and UK phone numbers (normalised to +44).
- **UK GDPR / DPA 2018:** every contact records a lawful basis. Marketing opt-in is recorded separately with a date, as PECR requires. Each contact has a one-click subject access request export (JSON) and a right-to-erasure action.
- **Security:** forms are CSRF-protected and redirects are checked so they cannot be used as open redirects.

## Tests

```bash
python -m pytest -q
```

## Project layout

```
app.py        Flask app factory and routes
db.py         schema, connection handling, demo seed data
ukfmt.py      GBP/date/VAT/postcode/phone helpers and the UK financial year
charts.py     server-side SVG revenue chart and quota gauge
templates/    Jinja templates
static/       stylesheet (light and dark themes)
tests/        pytest suite
```
