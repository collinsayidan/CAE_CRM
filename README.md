# CAE CRM

A CRM for UK businesses, made by Collinalitics. It runs at **https://cae.collinalitics.co.uk**.

Each business signs up for its own workspace, and no business can see another's records. It covers:

- **Sales:** contacts, companies, deals with products and line items, quotes, and email campaigns.
- **Service:** a help desk with service levels, email-to-ticket, a help centre and website chat.
- **Money:** VAT invoices, part payments, credit notes, recurring invoices, aged debt, and card payments through Stripe.
- **UK details built in:** GBP, UK dates, VAT, Companies House lookups, bank holidays for each nation, Making Tax Digital and UK GDPR tools.
- **Connections:** Gmail, Outlook, Xero, HMRC, a public API, signed webhooks, workflows and Power BI feeds.
- **AI assistant** (optional, uses Claude): answers questions about your records, writes summaries and draft replies, and triages tickets.

It's written in Python with Flask. It uses SQLite on your own computer and PostgreSQL in production, and plain JavaScript in the browser, with no build step.

## Try it on your computer

```bash
cd cae-crm
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000, choose **Create a workspace**, and tick the sample data box to look around with made-up UK companies.

## What's in this repository

| Folder | What it holds |
| --- | --- |
| [`cae-crm/`](cae-crm/) | The app: code, templates, tests and the `Dockerfile`. Its [README](cae-crm/README.md) covers every feature and setting. |
| [`brand/`](brand/) | The CAE CRM logo, icons and favicon. See the [brand README](brand/README.md). |
| [`.github/workflows/`](.github/workflows/) | Automated tests. Every pull request runs the full test suite on SQLite and PostgreSQL, and builds the Docker image. |

## How it's hosted

- The app runs in Docker on a Hetzner server in Nuremberg, managed with Coolify.
- Its PostgreSQL database and attached files are on the same server. The database has no public port: only the app connects to it.
- The database is backed up every night, and Hetzner backs up the whole server.
- Merging into `main` deploys automatically.

The [app README](cae-crm/README.md#deploy-to-coolify-or-any-docker-host) explains how to set it up from scratch.

## Run the tests

```bash
cd cae-crm
pip install -r requirements-dev.txt
python -m pytest -q
```

## Legal

The terms, privacy notice, data processing agreement, cookie policy and accessibility statement are at [/legal](https://cae.collinalitics.co.uk/legal). They're drafts awaiting a solicitor's review.
