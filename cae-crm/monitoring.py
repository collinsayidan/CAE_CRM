"""Error monitoring with Sentry, switched on by SENTRY_DSN. Reports carry the error and the page, never form
contents, cookies or sign-in headers, so no passwords or customer details leave the app; people are identified only
by their user and workspace numbers."""

import os

SCRUBBED_HEADERS = {"authorization", "cookie", "x-csrf-token", "stripe-signature", "svix-signature"}


def scrub(event, _hint=None):
    """Remove anything personal from an error report before it's sent."""
    request = event.get("request") or {}
    request.pop("data", None)
    request.pop("cookies", None)
    request.pop("query_string", None)  # reset and quote tokens travel in links
    headers = request.get("headers") or {}
    for name in list(headers):
        if name.lower() in SCRUBBED_HEADERS:
            headers[name] = "[removed]"
    user = event.get("user") or {}
    event["user"] = {k: v for k, v in user.items() if k in ("id", "workspace")}
    return event


def start(app):
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn or app.config.get("TESTING"):
        return False
    import sentry_sdk
    sentry_sdk.init(dsn=dsn, send_default_pii=False, before_send=scrub,
                    environment=os.environ.get("VERCEL_ENV", "local"),
                    release=os.environ.get("VERCEL_GIT_COMMIT_SHA") or None,
                    traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE") or 0))
    return True


def identify(user):
    """Tag errors with who hit them, by number only."""
    try:
        import sentry_sdk
    except ImportError:
        return
    sentry_sdk.set_user({"id": str(user["id"]), "workspace": str(user["workspace_id"])} if user else None)
