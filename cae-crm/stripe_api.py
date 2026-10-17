"""The few Stripe API calls billing needs, over HTTPS with the standard library. Tests set STRIPE_BACKEND to a fake
object with the same request(method, path, params) signature."""

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from flask import current_app

API = "https://api.stripe.com/v1"


class StripeError(Exception):
    pass


def configured():
    c = current_app.config
    return bool(c.get("STRIPE_BACKEND") or (c.get("STRIPE_SECRET_KEY") and c.get("STRIPE_PRICE_ID")))


def flatten(params, prefix=""):
    """Stripe's form encoding: {"a": {"b": [1]}} -> [("a[b][0]", "1")]."""
    out = []
    items = params.items() if isinstance(params, dict) else enumerate(params)
    for key, value in items:
        name = f"{prefix}[{key}]" if prefix else str(key)
        if isinstance(value, (dict, list)):
            out += flatten(value, name)
        elif value is not None:
            out.append((name, "true" if value is True else "false" if value is False else str(value)))
    return out


def request(method, path, params=None):
    fake = current_app.config.get("STRIPE_BACKEND")
    if fake:
        return fake.request(method, path, params or {})
    key = current_app.config.get("STRIPE_SECRET_KEY")
    if not key:
        raise StripeError("Billing isn't set up. Add STRIPE_SECRET_KEY to the hosting settings.")
    data = urllib.parse.urlencode(flatten(params or {})).encode()
    url = API + path + (("?" + data.decode()) if method == "GET" and data else "")
    req = urllib.request.Request(url, data=data if method != "GET" else None, method=method, headers={
        "Authorization": f"Bearer {key}", "Stripe-Version": "2024-06-20", "User-Agent": "CAE-CRM/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            message = json.loads(e.read()).get("error", {}).get("message", "")
        except ValueError:
            message = ""
        raise StripeError(f"Stripe refused the request ({e.code}). {message}".strip()) from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise StripeError(f"Couldn't reach Stripe: {e}") from None


def verify_webhook(payload, header, secret, tolerance=300):
    """Check the Stripe-Signature header: t=<time>,v1=<HMAC-SHA256 of 't.payload'>."""
    if not (secret and header):
        return False
    parts = {}
    for item in header.split(","):
        k, _, v = item.partition("=")
        parts.setdefault(k.strip(), []).append(v.strip())
    try:
        stamp = int(parts["t"][0])
    except (KeyError, ValueError):
        return False
    if abs(time.time() - stamp) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{stamp}.".encode() + payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, sig) for sig in parts.get("v1", []))
