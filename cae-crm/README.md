# CAE CRM

A CRM for UK businesses, built in Python with **Flask**. Many businesses can use one installation: each signs up for its own workspace, and nobody sees another business's records. It covers contacts, companies, deals with products and line items, a help desk with service levels, tasks, VAT invoices, delivery projects and reports.

It uses SQLite locally and PostgreSQL in production, with plain JavaScript for the interactive parts. There's no front-end framework or build step.

## Run it

```bash
cd cae-crm
pip install -r requirements.txt
python app.py            # or: flask --app app run
```

Open http://127.0.0.1:5000 and choose **Create a workspace**. Leave the sample data box ticked to look around with fictional UK companies, deals and tickets, or leave it empty and import your own. Locally the data lives in `instance/cae_crm.sqlite3`. Delete that file to start again.

## Workspaces and accounts

- **Sign-up:** whoever creates a workspace becomes its first **admin**. Set `CAE_SETUP_CODE` and sign-up asks for that code, so only people you invite can open a workspace.
- **Teams:** admins add people from **Team** with a temporary password, and can reset passwords, change roles or remove people.
- **Roles:** members do the everyday work. Only admins can change settings, manage the team, import, export lists, delete records or erase a contact's personal data.
- **Separation:** every record carries its workspace. Every query is filtered by it, and links between records are checked against it, so one business can't read or reference another's data. `tests/test_isolation.py` checks this page by page.
- **Passwords:** at least 10 characters, stored as scrypt hashes. After 5 wrong attempts an account locks for 15 minutes. Sign-ins last 12 hours, and session cookies are HTTP-only, SameSite=Lax and Secure when hosted.

## Deploy to Vercel

1. **Root directory.** In the Vercel project, open **Settings → General** and set **Root Directory** to `cae-crm`.
2. **Database (Supabase).** In the Supabase project, click **Connect** and copy the **Transaction pooler** string (port 6543), with your database password in place of `[YOUR-PASSWORD]` and no square brackets. Use the pooler, not the direct connection: Vercel can't reach Supabase's direct address. Any PostgreSQL connection string works, and strings from Vercel's Supabase integration (`POSTGRES_URL`) are accepted as they are.
3. **Environment variables.** In **Settings → Environment Variables**, add these for Production and Preview (`.env.example` lists them):
   - `DATABASE_URL`: the Supabase pooler string from step 2.
   - `CAE_SECRET_KEY`: a long random value. `python -c "import secrets; print(secrets.token_hex(32))"` makes one.
   - `CAE_SETUP_CODE`: an invite code of your choosing. People need it to create a workspace.
4. **Redeploy.** Then open the site and create your workspace.

To run locally against Supabase, copy `.env.example` to `.env`, fill it in and run `python app.py` (after `pip install -r requirements-dev.txt`). `.env` is never committed.

The app creates and upgrades its tables when it starts. On PostgreSQL it also turns on row level security for every table, so Supabase's public Data API can't read or change CRM data; the app connects as the tables' owner and isn't affected. A database from the first release is upgraded in place, and its records move into a workspace called "My business". If a required setting is missing, the site shows a "Finish setting up" page naming it, rather than running without it.

Vercel finds the app through `wsgi.py`, which `pyproject.toml` names in `[tool.vercel] entrypoint = "wsgi:app"`.

## What's in it

The sidebar groups pages the way a business works: **CRM** (Contacts, Companies, Deals, Tickets), **Sales** (Tasks, Products), **Finance** (Invoices), **Delivery** (Projects), **Insight** (Reports) and **Workspace** (Team). Admins also get **Settings** and **Import**.

**Team and profiles.** Everyone has a profile with a photo, job title, team, phone, location, LinkedIn and a short bio, edited under **Profile and password**. Photos are cropped to a 256px square WebP, stripped of location data and stored in the database. The Team page lists everyone; a profile shows that person's open deals, tickets and tasks. Admins can edit anyone's profile, change roles, reset passwords and remove people from the profile page.

| Page | What it does |
|---|---|
| **Home** | The month track (won revenue against target, paced by UK working days), key figures including open tickets and service-level breaches, the revenue chart, what's next, deals closing soon, pipeline by stage and the quarterly quota. |
| **Contacts** | People, with lifecycle stage (Subscriber → Lead → MQL → SQL → Opportunity → Customer → Evangelist), lead status, owner and consent. Lifecycle moves on automatically when a contact joins a deal or a deal is won. |
| **Companies** | Businesses, with Companies House and VAT numbers, lifetime revenue, open pipeline and open tickets. |
| **Deals** | A drag-and-drop board by stage, or a list you can filter and sort. Winning a deal starts a delivery project. |
| **Tickets** | A help desk board (New, Waiting on us, Waiting on contact, Closed) and list. Each priority has a first-response and resolution target counted in UK working hours. |
| **Tasks** | Calls, emails, meetings and to-dos on a month calendar with bank holidays, for everyone or just you. |
| **Products** | Your price list with SKU, billing period (one-off, monthly, annual) and VAT rate. Archive what you no longer sell. |
| **Invoices** | Aged debt, VAT for the quarter and every invoice. Each invoice prints with your business details. |
| **Projects** | Delivery work from won deals, by status. |
| **Reports** | Lifecycle funnel, service levels and tickets by category, won revenue by source, the leaderboard and products in the open pipeline. |

### Record pages

Contacts, companies, deals and tickets each open as a three-column record page:
- **Left:** the record's key details, with quick actions for Note, Email, Call, Task and Meeting.
- **Middle:** a box for logging notes, emails, calls (with an outcome) and meetings, or setting a task. Below it is one timeline of everything that happened, grouped by month, which you can filter by type. Changes such as a stage move or a new owner are logged on the timeline automatically.
- **Right:** the linked records.

Deal pages add a **stage path** and **line items**. Add products from your list or a custom line with quantity, discount and VAT rate. The deal's amount is the total of its lines, and **Invoice this deal** raises an invoice from them with VAT summarised by rate.

Ticket pages add the status path and the two service-level clocks.

### Lists, views and data

- **Views:** filter any list, then save the filters as a view tab. Built-in views include My contacts, New leads, Open tickets and Urgent.
- **Bulk actions:** tick rows to assign an owner, set a lifecycle stage or ticket status, or delete.
- **Import:** upload a CSV of contacts or companies, match its columns (common headings are matched for you), then choose whether duplicates are skipped or updated. Files saved by Excel in Windows-1252 are read correctly.
- **Export:** any filtered list downloads as CSV that opens cleanly in Excel. Cells that could run as spreadsheet formulas are neutralised.
- **Search:** press <kbd>Ctrl</kbd>/<kbd>⌘</kbd>+<kbd>K</kbd> (or <kbd>/</kbd>) to search contacts, companies, deals and tickets, or jump to any page or form.
- **New:** create a contact, company, deal, ticket, task or invoice from any page. On a record page the form is already linked to that record.

## Design

- **Colours:** navy and teal on white cards and a light grey background, with light and dark themes. Amber marks things due soon, and red marks only what is overdue or breached.
- **Typeface:** Plus Jakarta Sans throughout.
- **Contrast:** text meets WCAG AA in both themes.
- **Layout:** works down to phone width. Boards scroll sideways a column at a time, and record pages stack.
- **Without JavaScript:** every page still works. Forms post normally, and card menus stand in for drag and drop.

## UK standards built in

- **Currency:** GBP (£), stored as integer pence so there are no rounding errors.
- **Dates:** DD/MM/YYYY throughout (the page language is en-GB).
- **VAT:** 20% standard, 5% reduced and 0% zero-rated, set per line.
  - Invoices summarise VAT by rate, show the tax point and both parties' VAT numbers, use your payment terms and refer to the Late Payment of Commercial Debts Act.
  - A business that isn't VAT registered charges no VAT, and its invoices say so.
- **Record keeping:** companies and deals with invoices can't be deleted, because HMRC requires records to be kept for six years.
- **Financial year:** runs 1 April to 31 March (labelled FY2026/27), with quarters for quota tracking. VAT quarters follow the calendar.
- **Working hours:** ticket service levels count 09:00 to 17:00, Monday to Friday, skipping England and Wales bank holidays from 2025 to 2027.
- **Validation:**
  - UK postcodes are normalised, e.g. `eh22an` becomes `EH2 2AN`.
  - Companies House numbers are checked, including the SC, NI and OC prefixes, and link to the register.
  - GB VAT numbers are checked.
  - UK phone numbers are normalised to +44.
- **UK GDPR / DPA 2018:**
  - Every contact records a lawful basis.
  - Marketing opt-in is recorded separately with a date, as PECR requires.
  - Each contact has a subject access export (JSON) and a right-to-erasure action.
- **Security:** sign-in on every page, CSRF protection on every form, and redirects that can't send people off-site.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

To run every test against PostgreSQL as well, point `CAE_TEST_POSTGRES_URL` at a throwaway database. The tests wipe it.

## Project layout

```
app.py        app factory, navigation, filters and request guard
core.py       workspace-scoped query helpers, timeline logging, service-level states
auth.py       sign-up, sign-in, team and password management
home.py       landing page, Home dashboard, search and Reports
crm.py        contacts, companies, deal pages, timeline, list views and bulk actions
sales.py      deals board, line items, products, tasks and projects
service.py    tickets and service levels
finance.py    invoices, VAT and aged debt
dataio.py     CSV import and export, saved views
settings.py   business details, VAT and invoice settings
db.py         schema, migrations, SQLite/PostgreSQL connection wrapper
seed.py       sample data for a new workspace
ukfmt.py      GBP, dates, VAT, postcodes, phone numbers, working hours, financial year
charts.py     server-side SVG charts
wsgi.py       hosting entrypoint (module-level `app`)
templates/    Jinja templates
static/       style.css and app.js
tests/        pytest suite, including cross-workspace isolation tests
```
