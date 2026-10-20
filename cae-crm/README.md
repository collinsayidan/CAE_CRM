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
- **Teams:** admins invite people from **Team**. With email set up, the colleague gets a link (valid 7 days) to choose their own password; without it, the admin sets a temporary password to share. Admins can resend or cancel invites, reset passwords, change roles or remove people.
- **Confirming email:** whoever signs up gets a link to confirm their email address. Until they do, they can use the CRM but can't send emails (campaigns, invoices, reminders, quotes) or invite colleagues, and a banner offers a new link. Accepting an invite or resetting a password also confirms the address. People who signed up before this existed count as confirmed.
- **Roles:** members do the everyday work. Only admins can change settings, manage the team, import, export lists, delete records or erase a contact's personal data.
- **Separation:** every record carries its workspace. Every query is filtered by it, and links between records are checked against it, so one business can't read or reference another's data. `tests/test_isolation.py` checks this page by page.
- **Passwords:** at least 10 characters, stored as scrypt hashes, and checked against Have I Been Pwned's breach data (only the first 5 characters of a SHA-1 hash are sent; if the service is down the password is allowed; `CAE_BREACH_CHECK=0` turns it off). After 5 wrong attempts an account locks for 15 minutes, and after 20 failed sign-ins in 15 minutes an IP address has to wait.
- **Sessions:** each sign-in is recorded on the server. **Profile and password** lists where you're signed in, with **Sign out** for each device and **Sign out everywhere else**. Signing out, changing your password, or an admin resetting it ends sessions for real. A sign-in ends after 12 hours unused. Session cookies are HTTP-only, SameSite=Lax and Secure when hosted.
- **New sign-in alerts:** a sign-in from a browser the person hasn't used before (recognised by the `cae_device` cookie) sends them an email with the device, IP address and time.

## Deploy to Vercel

**CAE CRM now runs on Coolify** at https://cae.collinalitics.co.uk (see the next section). The Vercel project only redirects: `vercel.json` sends every address to the same path on the new domain. That keeps quotes, payment links, web forms and unsubscribe links already sent working. Delete the Vercel project once those links have aged out, about 3–6 months after the switch. The steps below are for running the app itself on Vercel again; you'd also need to restore `vercel.json`'s region and daily job.

1. **Root directory.** In the Vercel project, open **Settings → General** and set **Root Directory** to `cae-crm`.
2. **Database (Supabase).** In the Supabase project, click **Connect** and copy the **Transaction pooler** string (port 6543), with your database password in place of `[YOUR-PASSWORD]` and no square brackets. Use the pooler, not the direct connection: Vercel can't reach Supabase's direct address. Any PostgreSQL connection string works, and strings from Vercel's Supabase integration (`POSTGRES_URL`) are accepted as they are.
3. **Environment variables.** In **Settings → Environment Variables**, add these for Production (`.env.example` lists them):
   - `DATABASE_URL`: the Supabase pooler string from step 2.
   - `CAE_SECRET_KEY`: a long random value. `python -c "import secrets; print(secrets.token_hex(32))"` makes one.
   - `CAE_SETUP_CODE`: an invite code of your choosing. People need it to create a workspace.
   - `RESEND_API_KEY`, `CAE_MAIL_FROM` and optionally `RESEND_WEBHOOK_SECRET`: to send email. See **Email** below.
   - The `STRIPE_…` settings and `CAE_BILLING_EXEMPT`: to charge for CAE CRM. See **Billing** below.
   - `STRIPE_CONNECT_CLIENT_ID` and `STRIPE_CONNECT_WEBHOOK_SECRET`: to let businesses take card payments on their invoices. See **Getting paid** below.
   - The integration settings and `CRON_SECRET`: for Gmail, Outlook, Xero and HMRC. See **Integrations** below.
   - Optionally `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` and `CAE_STORAGE_BUCKET`: to keep attached files in a private Supabase Storage bucket rather than the database. See **Files and custom fields** below.
4. **Redeploy.** Then open the site and create your workspace.
5. **Previews.** Vercel builds a preview of every pull request. Previews never use `DATABASE_URL`, so new code can't touch live data before it's reviewed. Create a second (free) Supabase project for previews and add its Transaction pooler string as `PREVIEW_DATABASE_URL` for the **Preview** environment only, along with `CAE_SECRET_KEY`. Until then, previews show the "Finish setting up" page.

To run locally against Supabase, copy `.env.example` to `.env`, fill it in and run `python app.py` (after `pip install -r requirements-dev.txt`). `.env` is never committed.

The app creates and upgrades its tables when it starts. On PostgreSQL it also turns on row level security for every table as an extra safeguard (on Supabase, it stops the public Data API reading CRM data); the app connects as the tables' owner and isn't affected. A database from the first release is upgraded in place, and its records move into a workspace called "My business". If a required setting is missing, the site shows a "Finish setting up" page naming it, rather than running without it.

**Speed.** Keep the app and the database close together. Every page runs a few dozen small queries, and a round trip across the Atlantic adds about 80ms to each. On Coolify the app and its database run on the same server, so queries never leave the machine. The app also skips its schema check on start-up when nothing has changed, and keeps its database connection open between requests on the same server.

Vercel finds the app through `wsgi.py`, which `pyproject.toml` names in `[tool.vercel] entrypoint = "wsgi:app"`.

## Deploy to Coolify (or any Docker host)

The `Dockerfile` runs the app with gunicorn on port 8000, as an ordinary user, with a health check at `/healthz`. It sets `CAE_HOSTED=1`, so the app:
- uses secure cookies;
- refuses to start without its key and database;
- trusts the proxy's `X-Forwarded-*` headers for the visitor's scheme, host and address.

1. **Add the app.** In Coolify, open your project and choose **+ Add Resource → Public/Private repository** (GitHub App or deploy key for a private repository). Pick this repository and branch `main`.
   - **Build pack:** Dockerfile.
   - **Base directory:** `/cae-crm`.
   - **Port:** 8000.
2. **Domain.** Set it, for example `https://cae.collinalitics.co.uk`, and point an `A` record for that name at the server. Coolify gets the HTTPS certificate.
3. **Environment variables.** Use the same ones as on Vercel (`.env.example` lists them):
   - `DATABASE_URL`: the internal URL of a PostgreSQL database in the same Coolify project (**+ Add Resource → PostgreSQL**, no public port). Turn on its scheduled backups.
   - `CAE_SECRET_KEY`. Use the **same** secret key as Vercel, so people stay signed in when you switch.
   - Email, Stripe, integrations, `CRON_SECRET`, and the `LEGAL_…` settings.
   - `CAE_BASE_URL`: the public address, for example `https://cae.collinalitics.co.uk`. The daily job uses it to build links in emails.
   - Optionally `CAE_WORKERS`: gunicorn processes, default 2.
4. **Daily job.** Under the application's **Scheduled Tasks**, add `python cron.py` at `0 6 * * *`. Run it **once a day only**, because each run sends a reminder for every overdue invoice. Turn it on only after Vercel's cron has stopped, or reminders will go out twice.
5. **Preview deployments.** Leave them **off**, unless they have their own database. A preview runs unreviewed code, and would otherwise use the live `DATABASE_URL`.
6. **Switching over.**
   - Deploy and check the app at its new address.
   - Update the web addresses registered with integrations (Google, Microsoft, Xero, HMRC, Stripe and Resend webhooks) to the new domain.
   - Then remove the Vercel project, or its cron and domain.

### Moving to another database

`move_database.py` copies every table, plus any files kept in Supabase Storage, from `DATABASE_URL` into the new, empty database named by `TARGET_DATABASE_URL`. Run it in the app's container (in Coolify, the application's **Terminal**):

```bash
python move_database.py --check
python move_database.py
```

- `--check` compares row counts and changes nothing.
- Without it, the script copies everything. It then checks that every table matches, and that no file is left outside the database.
- The source is only ever read. Switch `DATABASE_URL` to the new address only once the counts match. Then remove `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`, because files are now served from the database.
- CAE CRM moved off Supabase this way in October 2026. Its data and files now live in `cae-crm-db` on the Coolify server, backed up nightly.

## Email

CAE CRM sends through [Resend](https://resend.com). Every business sends from the one address in `CAE_MAIL_FROM`, shown with the business's own name, and replies go to the reply-to email in **Settings**.

1. Create a Resend account and, under **Domains**, add a sending domain such as `mail.yourdomain.co.uk`. Add the DNS records Resend shows (SPF, DKIM and a DMARC record) at your domain host and wait for them to verify.
2. Under **API Keys**, create a key with sending access. Add it to Vercel as `RESEND_API_KEY`, and add `CAE_MAIL_FROM` (for example `hello@mail.yourdomain.co.uk`).
3. Optional: under **Webhooks**, add `https://<your site>/webhooks/resend` for the email events, and add its signing secret to Vercel as `RESEND_WEBHOOK_SECRET`. Turn on open and click tracking for the domain if you want those figures.
4. Redeploy. Until a domain is verified, Resend only delivers to your own account's address, which is enough for a test.

## Billing

Each business gets a 14-day free trial without a card, then pays per user a month, plus VAT, through [Stripe](https://stripe.com). The number of users billed follows the team: adding or removing someone updates the subscription, and Stripe prorates the change. When a trial ends unpaid or a subscription lapses, the workspace becomes read-only. People can still sign in, view and export everything, and erase personal data, but can't add or change records until an admin subscribes. Web forms and quote acceptance keep working, so no leads are lost. Admins subscribe through Stripe Checkout (with VAT number collection) and manage cards, invoices and cancellation in Stripe's billing portal.

Without `STRIPE_SECRET_KEY`, billing is off and every workspace has full access.

1. In Stripe, create a product "CAE CRM" with a **recurring monthly price per unit** in GBP, and copy its `price_…` id to `STRIPE_PRICE_ID`. Set `CAE_SEAT_PRICE` to the same amount in pence so the app shows it.
2. If you're VAT registered, create a 20% **exclusive** tax rate and copy its `txr_…` id to `STRIPE_TAX_RATE_ID`.
3. Under **Developers → Webhooks**, add `https://<your site>/webhooks/stripe` for `checkout.session.completed` and `customer.subscription.created`, `.updated` and `.deleted`. Copy the signing secret to `STRIPE_WEBHOOK_SECRET`.
4. Turn on the **customer portal** (Settings → Billing → Customer portal) so customers can update cards, see invoices and cancel.
5. Add `STRIPE_SECRET_KEY` (start with a `sk_test_…` key), set `CAE_BILLING_EXEMPT` to your own workspace's id, and redeploy.

## Getting paid

Each invoice has a private payment page (`/pay/<token>`) showing what's left to pay, the bank details and the PDF. Invoice emails, reminders and PDFs link to it.

- **Card payments** use [Stripe Connect](https://docs.stripe.com/connect/oauth-standard-accounts). Each business clicks **Connect Stripe** under Settings, Payments and signs in to its own Stripe account; CAE CRM keeps only the account id. The payment page then opens Stripe Checkout on that account, so the money goes straight to the business and Stripe's fees are theirs. The payment is recorded on the invoice when the customer comes back, and by the webhook, once either way. To set it up once:
  1. In Stripe, open **Settings → Connect**, choose to build a platform, and under **Onboarding options → OAuth** turn on OAuth for Standard accounts. Add `https://<your site>/settings/payments/stripe/return` as a redirect URI, and copy the `ca_…` client id to `STRIPE_CONNECT_CLIENT_ID`.
  2. Under **Developers → Webhooks**, add an endpoint that listens to **events on connected accounts**: `https://<your site>/webhooks/stripe-connect`, for `checkout.session.completed`, `checkout.session.async_payment_succeeded` and `account.application.deauthorized`. Copy its signing secret to `STRIPE_CONNECT_WEBHOOK_SECRET`.
  3. `STRIPE_SECRET_KEY` is the same key billing uses. Redeploy.
- **Part payments:** **Record payment** on an invoice (bank transfer, card, cash, cheque or other). It's marked paid once nothing is left, and aged debt counts only what's left. Admins can remove a payment entered by mistake.
- **Credit notes** (CN-0001, CN-0002…) against an invoice, for some or all of it, with a reason and a PDF. The VAT is credited in the same proportion as the invoice and comes off the VAT quarter's total.
- **Recurring invoices** (Invoices, Recurring): monthly, quarterly or yearly, raised by the daily cron job and emailed to the chosen contact with the PDF attached. The owner is notified each time. A schedule on the 31st uses the last day of shorter months, and a paused one carries on from its next date rather than catching up.
- **Reminders:** besides 3, 14 and 30 days late, one goes 3 days before the due date (admins can switch it off). Admins can change the wording of each under Settings, Payments, with `{first_name}`, `{number}`, `{amount_due}`, `{due_date}`, `{days_late}` and `{business}`.
- **Late payment charges:** overdue invoices show the interest (8% over the Bank of England reference rate, a day at a time) and fixed compensation (£40, £70 or £100) that the Late Payment of Commercial Debts (Interest) Act 1998 allows, and **Add late payment charges** adds them to the invoice without VAT. The reference rate is a setting (default 3.75%); check it each January and July.

## Integrations

Under **Workspace → Integrations**. Each one is an OAuth sign-in with the service; tokens are encrypted in the database with a key derived from `CAE_SECRET_KEY` (or `CAE_TOKEN_KEY`), so changing that key means reconnecting. A service only appears once its client id and secret are set. Register this redirect URI with each one: `https://<your site>/integrations/<name>/callback`, where `<name>` is `google`, `microsoft`, `xero` or `hmrc`.

- **Gmail and Outlook** (each person connects their own mailbox). Emails to or from people already in your contacts are logged to their timelines with the subject and a short preview; nothing else is kept. A daily Vercel Cron job (`vercel.json`, authorised by `CRON_SECRET`) syncs every mailbox, and **Sync now** works any time. Vercel's Hobby plan runs cron jobs once a day; Pro can run them more often.
  - Google: create an OAuth client (web application) in Google Cloud, enable the Gmail API, and add the `gmail.readonly` scope. Reading mail is a restricted scope, so until Google verifies the app (including a security assessment), only test users you list can connect.
  - Microsoft: register an app in Microsoft Entra ID for "accounts in any organisational directory and personal Microsoft accounts", add a client secret and the delegated `Mail.Read`, `User.Read` and `offline_access` permissions.
- **Xero** (an admin connects the business). **Send to Xero** on an invoice, or **Send invoices to Xero** for everything not yet sent, creates approved sales invoices with UK tax types; the sync marks invoices paid here once they're paid in Xero. Create a Web app at developer.xero.com. If Xero's scopes have changed for your app, set `XERO_SCOPES`.
- **HMRC Making Tax Digital for VAT** (an admin connects the business). **VAT returns** lists your VAT periods from HMRC and works out boxes 1 and 6 from your invoices by tax point; you enter purchases (boxes 4 and 7) from your own records, tick HMRC's declaration and submit. HMRC's fraud prevention headers are sent with every call. Register an application at developer.service.hmrc.gov.uk, subscribe it to the VAT (MTD) API, and test in the sandbox (`HMRC_ENV=sandbox`). Live submissions need HMRC's production approval, which includes checking the fraud prevention headers with HMRC's test API.

## AI assistant

An assistant that answers questions about a workspace's own records, explains how to use CAE CRM, and drafts emails and notes. It can **suggest** a task, a timeline note or a deal stage change, which shows up as a form with a **Confirm** button. Nothing changes until the person presses it, and the change then goes through the normal page, so permissions, timelines, workflows, webhooks and the audit trail all apply.

- It runs on Claude through Anthropic's API, called from the server. Pages still load nothing from other websites.
- It's hidden until `ANTHROPIC_API_KEY` is set. Then each workspace's admin turns it on under **Settings → AI assistant**, after reading what's shared with Anthropic.
- Everyone in the workspace can then use it from **Assistant** in the sidebar, which works without JavaScript, or from the sparkle button in the top bar, which opens a side panel that knows which record you're on.
- Every lookup is limited to the signed-in workspace. It has no tools for admin areas (billing, API keys, the audit trail). Record contents go to the model as data it's told never to take instructions from.
- Each person can ask `CAE_AI_DAILY_LIMIT` questions a day (default 50). Token use is recorded per person per day.
- Conversations are private to the person who had them, deleted after 30 days by the daily cron job, and deleted sooner on request. Erasing a contact deletes conversations that mention them.
- `CAE_AI_MODEL` (default `claude-opus-5-5`) and `CAE_AI_EFFORT` (default `medium`) choose the model and how hard it thinks. If Claude declines a request, Anthropic's server-side fallback retries it on another Claude model.
- An answer that needs several lookups can take 10 to 30 seconds. The assistant stops after 8 model calls or about 50 seconds, so check the function time limit on your Vercel plan allows at least 60 seconds.

### Email-to-ticket

Customers' emails to a business's support address become tickets, and their replies thread back into the same ticket.

- **Set up once (whoever runs CAE CRM):** in Resend, open Emails, Receiving, and either use your account's free `<id>.resend.app` address or add a receiving domain (for example `inbound.yourdomain.co.uk`) with the MX record Resend shows. Set `CAE_INBOUND_DOMAIN` to that domain, and tick the **email.received** event on the Resend webhook you already use (`/webhooks/resend`).
- **Each business:** an admin switches it on under Settings, Support email, picks who owns new email tickets, and forwards their own support mailbox to the private address shown (`support-<token>@<domain>`). The page gives the steps for Microsoft 365 and Gmail.
- **New emails:** become tickets (source Email, Medium priority) with the message as the description, quoted history trimmed. A sender who isn't a contact is added (lawful basis "Legitimate interests", no marketing consent), linked to a company whose website matches their email domain unless it's a free provider such as Gmail. Workflow rules, webhooks and AI triage run as for any new ticket.
- **Replies:** emails sent from a ticket carry that ticket's signed reply address and `[#214]` in the subject, so the customer's answer is added to the ticket's timeline, moves it to Waiting on us and tells the owner. A reply to a ticket closed in the last 14 days reopens it; older ones start a new ticket that links back.
- **Attachments** go to the ticket's Files under the usual rules (4 MB, safe types); others are listed on the timeline.
- **Safety:** webhooks are signature-checked and each email is handled once. Auto-replies, bounces and our own email are ignored. There's a limit of 20 new tickets an hour per sender and 500 a day per business, and emails that fail SPF/DKIM/DMARC are flagged on the ticket.

### AI helpers

Where the assistant is on, everyday pages get four helpers. Each sends one record's details to Claude, marked as data rather than instructions:

- **Summarise** (contacts, companies, deals, tickets): a few bullet points on where things stand, what's agreed, open problems and a next step.
- **Brief me** (contacts, companies, deals): a one-page brief before a meeting or call.
- **Draft with AI** (ticket replies): a reply written from the ticket, put in the box to check and edit. Nothing is sent until you press Send.
- **Triage** (new tickets): a suggested category, priority and owner, with flags if the customer sounds upset or it looks urgent. It loads in the background when a new ticket is opened (or with **Suggest triage**), once per ticket, and a person presses **Apply** or **Dismiss**.

Summaries, briefings and drafts count as daily questions; triage doesn't. Outputs are visible only to the person who asked, shown for an hour on the page and deleted after 30 days, or when a contact they mention is erased.

### Help articles and website chat

- **Help articles** (Settings, Help articles): short answers a business writes for its customers, as drafts or published. Published articles get plain public pages at `/help/<token>`, using the same simple formatting as email campaigns.
- **Website chat** (Settings, Website chat, shown once `ANTHROPIC_API_KEY` is set): a chat window the business adds to its website with one line of script. It answers visitors only from the published articles, links to the ones it used, says when it doesn't know, and offers **Talk to a person**, which opens a ticket (source Chat) with the whole chat on it and adds the visitor as a contact (lawful basis "Legitimate interests", no marketing consent).
- **Adding it:** the settings page shows the snippet to paste before `</body>`, and a link to a standalone chat page for businesses without a website editor. The chat only appears on the website addresses the admin lists (the page sends a `frame-ancestors` policy), needs no cookies, and works without JavaScript on the standalone page.
- **Limits:** each business allows up to 300 visitor messages a day (admins can set lower), each visitor 30 messages in 10 minutes and each chat 40 messages. After that, visitors are asked to leave their details instead. Each message costs about 1p with Claude Opus 5.5, as the articles are cached between messages.
- **Safety:** the chatbot never sees CRM records and has no tools, so it can only reply. It's told to treat visitors' messages as questions, not instructions, and never to guess prices or policies. Visitors are told they're chatting with an AI, and chats that don't become tickets are deleted after 30 days by the daily cron job.

## What's in it

The sidebar groups pages the way a business works: **CRM** (Contacts, Companies, Deals, Tickets), **Sales** (Tasks, Quotes, Products), **Marketing** (Email, Forms), **Finance** (Invoices), **Delivery** (Projects), **Insight** (Reports) and **Workspace** (Team, Integrations). Admins also get **Settings** and **Import**.

**Invoices your customers receive.** Upload your logo and add your bank details and an optional pay-online link under **Settings → Business details**; they appear on invoices, quotes, public pages and emails. Every invoice and quote downloads as a PDF. **Email invoice** sends it with the PDF attached, and with reminders switched on, unpaid invoices you've emailed are chased politely 3, 14 and 30 days after the due date by the daily job, or straight away with **Send a reminder now**. Reminders stop once an invoice is marked paid.

**Quotes.** Create a quote from a deal's line items, mark it as sent and share its private link. The customer reads it, then accepts by typing their name (the time, IP address and browser are recorded as evidence) or declines with a reason. Accepting wins the deal and sets a task to invoice it; one click turns the accepted quote into a VAT invoice. Typed-name e-signatures are valid for most UK commercial contracts under the Electronic Communications Act 2000.

**Email campaigns.** Write a campaign in plain text (blank lines for paragraphs, `- ` for lists, `**bold**`, `[links](https://…)` and `{{first_name}}`), choose who gets it by lifecycle stage and owner, preview it and send yourself a test. Only contacts with recorded marketing consent who haven't unsubscribed or bounced are included, as PECR requires. Admins send; the page sends in batches of 100 so no request runs too long on Vercel. Every email names the business, says why the person is getting it and has a one-click unsubscribe, also in the `List-Unsubscribe` headers Gmail and Yahoo expect. With the Resend webhook set up, deliveries, opens, clicks, bounces and spam complaints are recorded; a bounce stops future sends to that address and a complaint unsubscribes the person. Quotes can be emailed to the customer from the quote page, and a form's owner gets an email for each new enquiry.

**Web forms.** Build a contact form, then share its link or paste the embed code into your website. Each submission becomes a contact (matched by email, so repeat visitors aren't duplicated), with the company, a timeline entry and a follow-up task for the owner. Marketing consent is an unticked box and its wording is saved with the date, as PECR requires. A hidden honeypot field, a minimum fill-in time and a limit of five submissions per address in ten minutes keep spam out without a CAPTCHA. Erasing a contact deletes their submissions too.

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
- **Right:** the linked records, and the record's files.

Deal pages add a **stage path** and **line items**. Add products from your list or a custom line with quantity, discount and VAT rate. The deal's amount is the total of its lines, and **Invoice this deal** raises an invoice from them with VAT summarised by rate.

Ticket pages add the status path and the two service-level clocks.

### Files and custom fields

- **Files:** attach contracts, purchase orders and photos to any contact, company, deal or ticket (up to 4 MB each: PDFs, images, Office and OpenDocument files, text, CSV, zip and saved emails). Files always download rather than open in the page. Whoever attached a file, or an admin, can remove it. Erasing a contact or deleting a record removes its files too. With `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` set, files go to a private Supabase Storage bucket and download through links that expire after a minute; without them, they're kept in the database.
- **Custom fields:** admins add up to 30 fields in **Settings → Custom fields**: text, number, date, dropdown or yes/no, on contacts, companies, deals or tickets. They show in the About panel, are filled in from the Edit window, and are included in CSV exports. Removing a field hides it but keeps what was entered.

### Sales and data tools

- **Deals gone quiet:** an open deal with nothing logged for 14 days (change it under Settings, Business details) and no task coming up, or past its expected close date, is marked "Gone quiet" on the board and list, and has its own tab. The daily job tells the owner once, by notification.
- **Win and loss reasons:** marking a deal lost asks why (price, timing, a competitor, no decision, no budget or other, plus a note), on its own page so it works without JavaScript. Won deals can have an optional reason. Reports shows both for the last 12 months. The API and workflows record "Not given".
- **Tags:** add tags to contacts and companies on their pages or in bulk from a list, filter lists by tag, and save the filter as a view to make a segment that keeps itself up to date. Tags are in CSV exports. Admins rename, merge and delete tags under Settings, Tags.
- **Duplicates:** admins open **Find duplicates** on the Contacts or Companies list. Contacts match on email, phone number, or name at the same company; companies on Companies House number, name (ignoring Ltd and punctuation) or website. **Merge** keeps the record you choose, fills its empty fields from the other, moves everything linked across and notes it on the timeline. An unsubscribe or bounce on either contact wins. **Not duplicates** hides a pair.
- **Companies House:** set `COMPANIES_HOUSE_API_KEY` and typing a company's name in the new or edit company form suggests matches from the register; choosing one fills in the number and registered office. **Refresh from Companies House** records a company's status and SIC codes, and dissolved companies or ones in liquidation or administration get a red warning. The daily job re-checks up to 100 companies. Get a free key: register at developer.company-information.service.gov.uk, create an application, and add a **REST** API key for the live environment.
- **Recycle bin:** deleted contacts, companies, deals and tickets go to Settings, Recycle bin, with everything deleted alongside them (timeline, line items, tasks, quotes, tags and files). Admins can restore them for 30 days, or delete them permanently sooner; the daily job empties older entries. Erasing a contact under UK GDPR is still immediate.

### Support and email

- **Replying from a ticket:** the ticket page has a **Reply by email** box that emails the ticket's contact from your business name, with replies going to your reply-to address. The reply is logged on the timeline, counts as the first response, and moves a new ticket to Waiting on contact.
- **Saved replies:** admins keep common answers under Settings, Saved replies, with placeholders (`{{first_name}}`, `{{ticket_number}}`, `{{ticket_subject}}`, `{{your_name}}`, `{{business_name}}`). Pick one on a ticket, check it and send.
- **Satisfaction survey:** switch it on under Settings, Business details. When a ticket closes, its contact gets one email asking how you did (Good, Okay or Poor), and the answer is recorded when they press the button on the survey page (opening a link records nothing, so email scanners can't vote). Ratings go on the ticket timeline, and Reports shows the score and recent comments.
- **Daily summary:** each working morning, people with something to deal with get an email listing their overdue and today's tasks, tickets near or past a service level, their deals gone quiet, and (for admins) overdue invoices. One click in the email turns it off, or use Profile and password.
- **Bank holidays:** choose England and Wales, Scotland or Northern Ireland under Settings, Business details. Service levels, the Tasks calendar and working days follow it. Dates come from GOV.UK's feed, refreshed daily, with dates to 2028 built in.

### Workflows

Admins set up rules in **Settings → Workflows**: *when* something happens (a contact is added, a web form is submitted, a deal moves to a stage, a ticket is opened, a quote is accepted, an invoice is paid), optionally narrowed to one stage, priority or form, *then* do one thing:
- create a task (call, meeting, email or task) for a named person, the record's owner, or the team taking turns;
- notify someone;
- assign an owner (a named person, or the team taking turns);
- set the contact's lifecycle stage.

Rules run straight after the change that sets them off, from the app, the API or a public form or quote. Each run is noted on the record's timeline. A rule's own changes never set off another rule, so rules can't loop. Imports and bulk changes don't set rules off.

### API

Admins make keys in **Settings → API and webhooks**. A key is shown once and only its hash is stored. **Read only** keys can list and fetch; **read and write** keys can also add and update. Each key can make 120 requests a minute (`API_RATE_LIMIT`). In a read-only workspace (unpaid), reads still work and changes get `402`.

```bash
curl -H "Authorization: Bearer cae_..." https://your-site/api/v1/deals?stage=Won
```

| Method and path | What it does |
| --- | --- |
| `GET /api/v1/` | The workspace and the key's access |
| `GET /api/v1/{contacts,companies,deals,tickets,invoices}` | A page of records. `page`, `per_page` (up to 100), `created_since=YYYY-MM-DD` and filters such as `email`, `stage`, `status`, `priority`, `owner`, `company_id` |
| `GET /api/v1/{object}/{id}` | One record |
| `POST /api/v1/{contacts,companies,deals,tickets}` | Add a record (JSON body). Returns `201` |
| `PATCH /api/v1/{contacts,companies,deals,tickets}/{id}` | Change only the fields sent. A deal's `stage` and a ticket's `status` can change here too |

- **Same rules as the app.** Records go through the same checks: a contact needs a lawful basis, a company needs a UK postcode, and an owner must be on the team. Problems return `422` with `fields` saying which.
- **Money** is in whole pence (`value_pence`, `net_pence`). When adding a deal you can send `value` in pounds instead, for example `"£1,250.50"`.
- **Custom fields** appear under `custom`, by name, and can be set the same way: `"custom": {"Tier": "Gold"}`.
- **Logging.** Changes made through the API appear on timelines and in the audit trail as "API key *name*".
- **Not in the API:** deleting records and erasing personal data stay in the app, where an admin can see what they're doing.

### Webhooks

In **Settings → API and webhooks**, add an `https://` address and choose events:
- `contact.created`, `contact.updated`
- `company.created`, `company.updated`
- `deal.created`, `deal.updated`, `deal.stage_changed`, `deal.won`, `deal.lost`
- `ticket.created`, `ticket.updated`, `ticket.status_changed`
- `quote.accepted`, `quote.declined`
- `invoice.created`, `invoice.paid`
- `form.submitted`

**What gets sent.** Each event is POSTed as JSON: `{"id", "event", "created_at", "data": {the record, as the API shows it}}`. Some events add extra fields: `previous_stage`, `previous_status`, or `form` and `submission`.

**Checking it came from CAE CRM.** Every request carries `CAE-Signature: t=<unix time>,v1=<signature>`, where the signature is the HMAC-SHA256 of `<t>.<raw body>` keyed with the webhook's signing secret. To check one in Python:

```python
import hashlib, hmac, time

def is_from_cae(raw_body: bytes, header: str, secret: str) -> bool:
    parts = dict(p.split("=", 1) for p in header.split(","))
    expected = hmac.new(secret.encode(), f"{parts['t']}.".encode() + raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, parts["v1"]) and abs(time.time() - int(parts["t"])) < 300
```

**When deliveries fail.** The first attempt is made as soon as the change is saved. Failures are retried by the cron job up to 6 times over about two days. On Vercel's Hobby plan the cron job runs daily, so retries are daily too.

**Pausing.** After 20 failures in a row, a webhook is paused and admins are notified.

**Safe addresses only.** Addresses must resolve to public internet addresses. Redirects aren't followed, so a webhook can't reach anything private.

### Power BI and Excel

Every table is also available as a read-only CSV feed:
- `/api/v1/feed/contacts`
- `/api/v1/feed/companies`
- `/api/v1/feed/deals`
- `/api/v1/feed/tickets`
- `/api/v1/feed/invoices`
- `/api/v1/feed/tasks`

Feeds use plain column names, amounts in pounds, company names alongside ids, and custom fields as columns. Add `?format=json` for JSON.

To connect Power BI:
1. Choose **Get data → Web** and paste a feed address.
2. Choose **Basic** sign-in, with user name `api` and a read-only key as the password.

Scheduled refresh in the Power BI service uses the same sign-in. Cells that a spreadsheet could run as a formula are neutralised, but numbers and phone numbers are left as they are.

### Homepage

`/welcome` is the public homepage, dark by default with a light/dark switch. It only claims what the app does today: there are no testimonials or uptime figures, and the dashboard figures are labelled as sample data.

- **Price, trial and VAT** come from the billing settings (`CAE_SEAT_PRICE`, `CAE_TRIAL_DAYS`). "plus VAT" appears only once `STRIPE_TAX_RATE_ID` is set.
- **Book a demo** appears once `CAE_DEMO_URL` is set. Point it at a web form in your own workspace.
- **Company details** in the footer come from the `LEGAL_…` settings.
- **Nothing is loaded from other websites**, and all motion stops for people who ask their device to reduce it.

### Legal pages

`/legal` has draft **terms of service**, a **privacy notice**, a **data processing agreement** (covering what UK GDPR Article 28 requires) and a **cookies and storage** statement. They're written to match what CAE CRM actually does. **A solicitor must review them before they're relied on.**

- Until `CAE_LEGAL_REVIEWED=1` is set, each page shows a "Draft" notice.
- Company details come from the `LEGAL_…` settings. Anything missing, and any point still to decide, shows as a highlighted "to confirm" note rather than being guessed.
- Signing up records which version of the terms each workspace agreed to, when, and by whom. Admins can see this at `/legal`.
- Links appear on the landing page, the sign-in and sign-up pages, and in Settings.
- When the wording changes, update `VERSION` in `legal.py`.

### Lists, views and data

- **Views:** filter any list, then save the filters as a view tab. Built-in views include My contacts, New leads, Open tickets and Urgent.
- **Bulk actions:** tick rows to assign an owner, set a lifecycle stage or ticket status, or delete.
- **Import:** upload a CSV of contacts or companies, match its columns (common headings are matched for you), then choose whether duplicates are skipped or updated. Files saved by Excel in Windows-1252 are read correctly.
- **Export:** any filtered list downloads as CSV that opens cleanly in Excel. Cells that could run as spreadsheet formulas are neutralised.
- **Search:** press <kbd>Ctrl</kbd>/<kbd>⌘</kbd>+<kbd>K</kbd> (or <kbd>/</kbd>) to search contacts, companies, deals and tickets, or jump to any page or form.
- **New:** create a contact, company, deal, ticket, task or invoice from any page. On a record page the form is already linked to that record.

## Design

- **Style:** flat and minimal. Neutral greys, 1px lines instead of shadows, small corners and no gradients, in light and dark themes. Teal is kept for the one thing to look at: the current page, the main button, a month that met target, the leader in a ranking. Amber marks things due soon, and red marks only what is overdue or breached.
- **Charts:** plain and direct. Square bars in grey, with teal only for months that hit target; a thin dashed target line; sparklines as a single line; pipeline by stage as one stacked bar with a labelled list. Small charts are drawn on the server (`charts.py`), and the revenue chart in `static/app.js`.
- **Sidebar:** the same colour as the page, with compact items, a thin teal marker on the current page, and the profile in one row at the bottom.
- **Typeface:** Plus Jakarta Sans throughout, served from `static/fonts/` (SIL Open Font License) so pages load nothing from other websites.
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
security.py   email confirmation, invites, sessions and devices, sign-in limits, breached-password check
home.py       landing page, Home dashboard, search and Reports
crm.py        contacts, companies, deal pages, timeline, list views and bulk actions
sales.py      deals board, line items, products, tasks and projects
service.py    tickets and service levels
finance.py    invoices, VAT and aged debt
dataio.py     CSV import and export, saved views
settings.py   business details, VAT and invoice settings
assistant.py  the AI assistant: settings, conversations, the Claude loop, suggestions
assistant_tools.py  what the assistant can look up and suggest, all workspace-scoped
tags.py       tags on contacts and companies
duplicates.py finding and merging duplicate contacts and companies
companies_house.py  Companies House lookups and status checks
recycle.py    the 30-day recycle bin for deleted records
support.py    ticket replies, saved replies and the satisfaction survey
digest.py     the daily summary email
ukholidays.py bank holidays for each UK nation
helpers.py    AI helpers: summaries, briefings, draft replies and ticket triage
inbound.py    email-to-ticket: receiving customers' emails into tickets
helpcentre.py help articles and their public pages
chat.py       the website chatbot: the embed script, chat page, answers and handover to a ticket
payments.py   part payments, credit notes, late payment charges, payment pages and Stripe Connect
recurring.py  recurring invoices
db.py         schema, migrations, SQLite/PostgreSQL connection wrapper
seed.py       sample data for a new workspace
ukfmt.py      GBP, dates, VAT, postcodes, phone numbers, working hours, financial year
charts.py     server-side SVG charts
wsgi.py       hosting entrypoint (module-level `app`)
templates/    Jinja templates
static/       style.css and app.js
tests/        pytest suite, including cross-workspace isolation tests
```
