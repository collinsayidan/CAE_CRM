# CAE CRM

A UK-standard sales CRM built in Python with **Flask** and **SQLite**, with plain JavaScript for the interactive parts. It doesn't use a front-end framework or a build step.

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
| **Overview** | Opens with the month track: won revenue against target, with a tick for each UK working day and a pace marker showing where you'd be at an even rate. Below that are the key figures with trend lines, a hoverable revenue chart (6 or 12 months), what's coming up next, deals closing in the next 30 days, pipeline by stage and the quarterly quota. |
| **Pipeline** | Drag deals between stages, or drop them on Won or Lost. Each card also has a menu, so you can move deals without dragging. You can filter by owner. Winning a deal creates a delivery project. |
| **Customers** | A sortable list that filters as you type. Each company page has its registered details, account figures, and tabs for people, deals, invoices and activity. |
| **Schedule** | A month calendar (weeks start on Monday, bank holidays marked) next to a day-by-day agenda. You can tick activities off without the page reloading. |
| **Finance** | Unpaid, overdue and received totals, output VAT for the quarter, and an aged-debt breakdown. Invoices can be sorted and filtered. Raising an invoice shows a live VAT preview. Each invoice can be printed. |
| **Growth** | Won revenue and win rate by lead source and by sales rep. |
| **Projects** | A board grouped by status. Progress and status save as you change them. |

Across every page:
- **Search and jump:** press <kbd>Ctrl</kbd>/<kbd>⌘</kbd>+<kbd>K</kbd> (or <kbd>/</kbd>) to search customers, deals and people, or go straight to a page or form.
- **Quick create:** the **New** button opens a deal, customer, activity or invoice form from anywhere.
- **Display:** light and dark themes, and a mobile layout with a slide-out menu.

## Design

- **Colours:** racing green and brass on a sage-white background. Red is used only for overdue items.
- **Pipeline stages:** shown in one green colour ramp, from pale (earliest) to deep (latest).
- **Typeface:** Schibsted Grotesk throughout.
- **Motion:** the month track fills once when the page loads. If your system asks for reduced motion, it doesn't animate.
- **Without JavaScript:** every page still works. Forms post normally, and the pipeline menus stand in for drag and drop.

## UK standards built in

- **Currency:** GBP (£). Money is stored as integer pence, so there are no floating-point rounding errors.
- **Dates:** DD/MM/YYYY throughout (the page language is en-GB).
- **VAT:** 20% standard, 5% reduced and 0% zero-rated. VAT is calculated per invoice. Invoices show the tax point, VAT numbers, 30-day terms and a note on the Late Payment of Commercial Debts Act.
- **Financial year:** runs 1 April to 31 March (labelled FY2026/27), with quarters for quota tracking. VAT quarters follow the calendar.
- **Working days:** the month track and calendar skip weekends and England and Wales bank holidays from 2025 to 2027.
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
charts.py     server-side SVG quota ring and sparklines
templates/    Jinja templates (shared dialogs in _dialogs.html)
static/       style.css (light and dark themes) and app.js (interactions)
tests/        pytest suite
```
