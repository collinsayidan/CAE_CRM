"""The daily job (mailbox sync, invoice reminders, webhook retries), for hosts without Vercel Cron.

In Coolify, add a scheduled task on the CAE CRM application that runs `python cron.py` once a day, for example at
06:00 (`0 6 * * *`). Run it no more than once a day: each run sends one reminder for every overdue invoice.

It calls the same /cron/sync job as Vercel, inside the container, with CRON_SECRET. CAE_BASE_URL must be the site's
public address (for example https://cae.collinalitics.co.uk), because links in the emails it sends are built from it."""

import json
import os
import sys

from app import create_app


def main():
    base_url = os.environ.get("CAE_BASE_URL", "").rstrip("/")
    if not base_url.startswith("https://"):
        print("Set CAE_BASE_URL to the site's public https:// address, so links in emails point to it.", file=sys.stderr)
        return 1
    app = create_app()
    secret = app.config.get("CRON_SECRET")
    if not secret:
        print("CRON_SECRET isn't set, so the daily job can't run.", file=sys.stderr)
        return 1
    response = app.test_client().get("/cron/sync", base_url=base_url, headers={"Authorization": f"Bearer {secret}"})
    print(json.dumps(response.get_json(silent=True) or {"status": response.status_code}))
    return 0 if response.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
