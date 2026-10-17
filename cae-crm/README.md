# CAE CRM

A UK-standard sales CRM built in Python with **Flask**. It uses SQLite locally and PostgreSQL in production, with plain JavaScript for the interactive parts. It doesn't use a front-end framework or a build step.

## Run it

```bash
cd cae-crm
pip install -r requirements.txt
python app.py            # or: flask --app app run
```

Open http://127.0.0.1:5000. The first time you open it, the app asks you to create an admin account. Locally it uses an SQLite file at `instance/cae_crm.sqlite3`, filled with fictional UK demo data. To start again, delete that file.

## Accounts

- Every page needs you to sign in. The first account is an **admin**, created on the setup page, which closes once that account exists.
- Admins add team members from **Team**, with a temporary password, and can reset passwords or remove people. Only admins can erase a contact's personal data.
- Passwords need at least 10 characters and are stored as scrypt hashes. After 5 wrong attempts an account locks for 15 minutes. An admin resetting the password unlocks it.
- Sign-ins last 12 hours. Session cookies are HTTP-only and SameSite=Lax, and are marked Secure when the app is hosted.

## Deploy to Vercel

1. **Root directory.** In the Vercel project, open **Settings → General** and set **Root Directory** to `cae-crm`.
2. **Database.** Open **Storage**, create a **Neon Postgres** database and connect it to the project. This adds `DATABASE_URL` for you. Any PostgreSQL connection string works.
3. **Environment variables.** In **Settings → Environment Variables**, add:
   - `CAE_SECRET_KEY`: a long random value. `python -c "import secrets; print(secrets.token_hex(32))"` makes one.
   - `CAE_SETUP_CODE`: any phrase you choose. The setup page asks for it, so nobody else can claim the admin account before you.
4. **Redeploy.** Then open the site and create your admin account.

The app creates its tables on first start. A Postgres database starts empty. Set `CAE_DEMO_DATA=1` if you want the demo companies and deals in it. If a required setting is missing, the site shows a "Finish setting up" page naming it, rather than running without it.

Vercel finds the app through `wsgi.py`, which `pyproject.toml` names in `[tool.vercel] entrypoint = "wsgi:app"`.

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

- **Colours:** navy and teal on white cards and a light grey background. Amber marks things due soon, and red is used only for overdue items.
- **Stat cards:** each key figure sits on a card with an icon, a change badge and a filled trend line.
- **Charts:**
  - **Revenue:** rounded bars. Months that met the £156,700 target are solid teal, months below it are pale, and the current month is hatched. The target line is labelled, and hovering a bar shows the month's figure.
  - **Pipeline by stage:** a donut on one colour ramp, from light teal (earliest stage) to navy (latest).
  - **Quota:** a teal ring.
- **Typeface:** Plus Jakarta Sans throughout.
- **Contrast:** text meets WCAG AA in both light and dark themes.
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
- **Security:** every page needs a sign-in, forms are CSRF-protected, and redirects are checked so they cannot be used as open redirects.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

To run every test against PostgreSQL as well, point `CAE_TEST_POSTGRES_URL` at a throwaway database. The tests wipe it.

## Project layout

```
app.py        Flask app factory and routes
auth.py       sign-in, first-run setup, team and password management
wsgi.py       hosting entrypoint (module-level `app`)
db.py         schema, SQLite/PostgreSQL connection wrapper, demo seed data
ukfmt.py      GBP/date/VAT/postcode/phone helpers and the UK financial year
charts.py     server-side SVG quota ring and sparklines
templates/    Jinja templates (shared dialogs in _dialogs.html)
static/       style.css (light and dark themes) and app.js (interactions)
tests/        pytest suite
```
