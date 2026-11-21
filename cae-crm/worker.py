"""Run every five minutes: python worker.py. Keep cron.py on its once-daily schedule."""

import json
import os
import sys
from app import create_app


def main():
    base = os.environ.get("CAE_BASE_URL", "").rstrip("/")
    if not base.startswith("https://"):
        print("Set CAE_BASE_URL to the public https address.", file=sys.stderr)
        return 1
    app = create_app()
    secret = app.config.get("CRON_SECRET")
    if not secret:
        print("Set CRON_SECRET before starting the worker.", file=sys.stderr)
        return 1
    response = app.test_client().get(
        "/cron/fast", base_url=base, headers={"Authorization": "Bearer " + secret}
    )
    print(json.dumps(response.get_json(silent=True) or {"status": response.status_code}))
    return 0 if response.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
