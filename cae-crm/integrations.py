"""Connections to other services: Gmail and Outlook (each person's own mailbox), Xero and HMRC (one per business).
Each one is an OAuth 2.0 sign-in with the service. Tokens are encrypted at rest with a key derived from CAE_SECRET_KEY,
so changing that key means reconnecting. A service only appears once its client id and secret are configured.

Tests set INTEGRATION_HTTP to a fake with the same call(method, url, headers, body) signature as http()."""

import base64
import hashlib
import hmac
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet, InvalidToken
from flask import abort, current_app, flash, g, jsonify, redirect, render_template, request, session, url_for

import auth
from core import now, one, rows, ws
from db import get_db


def hmrc_base():
    live = current_app.config.get("HMRC_ENV") == "production"
    return ("https://api.service.hmrc.gov.uk" if live else "https://test-api.service.hmrc.gov.uk",
            "https://www.tax.service.gov.uk" if live else "https://test-www.tax.service.gov.uk")


def providers():
    c = current_app.config
    api, www = hmrc_base()
    return {
        "google": dict(name="Gmail", level="user", env="GOOGLE",
                       auth="https://accounts.google.com/o/oauth2/v2/auth", token="https://oauth2.googleapis.com/token",
                       scope="openid email https://www.googleapis.com/auth/gmail.readonly",
                       extra={"access_type": "offline", "prompt": "consent", "include_granted_scopes": "true"},
                       blurb="Log emails between you and your contacts to their timelines."),
        "microsoft": dict(name="Outlook", level="user", env="MICROSOFT",
                          auth="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
                          token="https://login.microsoftonline.com/common/oauth2/v2.0/token",
                          scope="offline_access openid email User.Read Mail.Read", extra={"prompt": "select_account"},
                          blurb="Log emails between you and your contacts to their timelines. Works with Microsoft 365."),
        "xero": dict(name="Xero", level="workspace", env="XERO",
                     auth="https://login.xero.com/identity/connect/authorize", token="https://identity.xero.com/connect/token",
                     scope=c.get("XERO_SCOPES") or "openid profile email offline_access accounting.transactions accounting.contacts",
                     extra={}, blurb="Send invoices to Xero and mark them paid here when they're paid in Xero."),
        "hmrc": dict(name="HMRC VAT (Making Tax Digital)", level="workspace", env="HMRC",
                     auth=f"{www}/oauth/authorize", token=f"{api}/oauth/token", scope="read:vat write:vat", extra={},
                     blurb="See your VAT deadlines and submit VAT returns to HMRC from your invoices."),
    }


def credentials(provider):
    env = providers()[provider]["env"]
    return current_app.config.get(f"{env}_CLIENT_ID"), current_app.config.get(f"{env}_CLIENT_SECRET")


def available(provider):
    cid, secret = credentials(provider)
    return bool(cid and secret) or bool(current_app.config.get("INTEGRATION_HTTP"))


# --- Tokens, encrypted ---------------------------------------------------------------

def _fernet():
    key = current_app.config.get("TOKEN_KEY") or current_app.config["SECRET_KEY"]
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"cae-tokens:" + str(key).encode()).digest()))


def seal(value):
    return _fernet().encrypt(value.encode()).decode() if value else None


def unseal(value):
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return None  # the key changed: the connection needs signing in again


class IntegrationError(Exception):
    pass


def http(method, url, *, headers=None, form=None, json_body=None, params=None):
    """A JSON request. Returns the decoded body. Raises IntegrationError with the service's message."""
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
    body = None
    headers = dict(headers or {})
    if form is not None:
        body = urllib.parse.urlencode(form).encode()
        headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    elif json_body is not None:
        body = json.dumps(json_body).encode()
        headers.setdefault("Content-Type", "application/json")
    headers.setdefault("Accept", "application/json")
    headers.setdefault("User-Agent", "CAE-CRM/1.0")
    fake = current_app.config.get("INTEGRATION_HTTP")
    if fake:
        status, data = fake(method, url, headers, body)
        if status >= 400:
            raise IntegrationError(f"{status}: {data}")
        return data
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")[:500]
        try:
            data = json.loads(raw)
        except ValueError:
            data = None
        if isinstance(data, dict):
            err = data.get("error")
            raw = (data.get("error_description") or data.get("message") or data.get("Message")
                   or (err.get("message") if isinstance(err, dict) else err) or raw)
        raise IntegrationError(f"{e.code}: {raw}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise IntegrationError(f"Couldn't reach the service: {e}") from None


def save_tokens(conn_id, tokens):
    expires = datetime.now(timezone.utc) + timedelta(seconds=int(tokens.get("expires_in") or 3600))
    db = get_db()
    db.execute("UPDATE connections SET access_token=?, expires_at=? WHERE id=?",
               (seal(tokens["access_token"]), expires.isoformat(timespec="seconds"), conn_id))
    if tokens.get("refresh_token"):  # Xero and Microsoft issue a new one each time
        db.execute("UPDATE connections SET refresh_token=? WHERE id=?", (seal(tokens["refresh_token"]), conn_id))
    db.commit()


def access_token(conn):
    """A working access token for a connection, refreshing it when it's about to expire."""
    token = unseal(conn["access_token"])
    expires = datetime.fromisoformat(conn["expires_at"]) if conn["expires_at"] else None
    if token and expires and expires - datetime.now(timezone.utc) > timedelta(seconds=60):
        return token
    refresh = unseal(conn["refresh_token"])
    if not refresh:
        raise IntegrationError("The connection has expired. Connect it again.")
    p = providers()[conn["provider"]]
    cid, secret = credentials(conn["provider"])
    tokens = http("POST", p["token"], form={"grant_type": "refresh_token", "refresh_token": refresh,
                                            "client_id": cid, "client_secret": secret})
    save_tokens(conn["id"], tokens)
    return tokens["access_token"]


def jwt_claims(id_token):
    """Claims from an ID token received straight from the provider's token endpoint over TLS."""
    try:
        payload = id_token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError, AttributeError):
        return {}


def connection(provider, user_id=None, workspace_id=None):
    sql = "SELECT * FROM connections WHERE workspace_id=? AND provider=?"
    args = [workspace_id or ws(), provider]
    if user_id:
        sql += " AND user_id=?"
        args.append(user_id)
    return one(sql + " ORDER BY id DESC LIMIT 1", *args)


def record_sync(conn_id, error=None, cursor=None):
    db = get_db()
    db.execute("UPDATE connections SET last_sync_at=?, last_error=?" + (", sync_cursor=?" if cursor else "") + " WHERE id=?",
               (now().isoformat(timespec="minutes"), (error or None) and str(error)[:300], *([cursor] if cursor else []), conn_id))
    db.commit()


def run_sync(conn):
    """Sync one connection. Returns a short summary. Errors are recorded on the connection, never raised."""
    import mailsync
    import xero
    g.public_workspace = conn["workspace_id"]
    g.pop("workspace", None)
    try:
        if conn["provider"] in ("google", "microsoft"):
            return mailsync.sync(conn)
        if conn["provider"] == "xero":
            return xero.sync_payments(conn)
        return "Nothing to sync."
    except IntegrationError as e:
        record_sync(conn["id"], error=e)
        return f"Error: {e}"
    finally:
        g.pop("public_workspace", None)
        g.pop("workspace", None)


def register(app):

    @app.route("/integrations")
    def integrations():
        mine = {r["provider"]: r for r in rows("SELECT * FROM connections WHERE workspace_id=? AND (user_id=? OR user_id IS NULL)",
                                               ws(), g.user["id"])}
        team_mail = rows("SELECT c.provider, c.account, u.name FROM connections c JOIN users u ON u.id=c.user_id "
                         "WHERE c.workspace_id=? AND c.provider IN ('google','microsoft') ORDER BY u.name", ws())
        return render_template("integrations.html", providers=providers(), mine=mine, available=available,
                               team_mail=team_mail, hmrc_live=current_app.config.get("HMRC_ENV") == "production",
                               cron=bool(current_app.config.get("CRON_SECRET")))

    @app.post("/integrations/<provider>/connect")
    def oauth_connect(provider):
        if provider not in providers() or not available(provider):
            abort(404)
        p = providers()[provider]
        if p["level"] == "workspace":
            auth.admin_required()
        state = secrets.token_urlsafe(24)
        session["oauth"] = {"state": state, "provider": provider}
        cid, _ = credentials(provider)
        params = {"client_id": cid, "redirect_uri": url_for("oauth_callback", provider=provider, _external=True),
                  "response_type": "code", "scope": p["scope"], "state": state, **p["extra"]}
        return redirect(f"{p['auth']}?{urllib.parse.urlencode(params)}")

    @app.get("/integrations/<provider>/callback")
    def oauth_callback(provider):
        if provider not in providers():
            abort(404)
        expected = session.pop("oauth", None) or {}
        state_ok = expected.get("provider") == provider and hmac.compare_digest(str(expected.get("state", "")),
                                                                                request.args.get("state", ""))
        if not state_ok:
            flash("That sign-in link had expired or didn't come from here. Try connecting again.", "error")
            return redirect(url_for("integrations"))
        if request.args.get("error") or not request.args.get("code"):
            flash(f"Not connected. {request.args.get('error_description') or 'The sign-in was cancelled.'}", "error")
            return redirect(url_for("integrations"))
        p = providers()[provider]
        cid, secret = credentials(provider)
        try:
            tokens = http("POST", p["token"], form={
                "grant_type": "authorization_code", "code": request.args["code"], "client_id": cid, "client_secret": secret,
                "redirect_uri": url_for("oauth_callback", provider=provider, _external=True)})
            account, tenant = describe(provider, tokens)
        except IntegrationError as e:
            flash(f"Not connected. {e}", "error")
            return redirect(url_for("integrations"))
        db = get_db()
        user_id = g.user["id"] if p["level"] == "user" else None
        old = connection(provider, user_id)
        if old:
            db.execute("DELETE FROM connections WHERE id=?", (old["id"],))
        conn_id = db.insert("connections", workspace_id=ws(), user_id=user_id, provider=provider, account=account,
                            tenant_id=tenant, created_at=now().isoformat(timespec="minutes"))
        db.commit()
        save_tokens(conn_id, tokens)
        flash(f"{p['name']} connected{f' ({account})' if account else ''}.", "ok")
        return redirect(url_for("integrations"))

    def describe(provider, tokens):
        """(account label, tenant id) for a new connection."""
        claims = jwt_claims(tokens.get("id_token"))
        if provider == "google":
            return claims.get("email"), None
        if provider == "microsoft":
            me = http("GET", "https://graph.microsoft.com/v1.0/me",
                      headers={"Authorization": f"Bearer {tokens['access_token']}"})
            return me.get("mail") or me.get("userPrincipalName"), None
        if provider == "xero":
            tenants = http("GET", "https://api.xero.com/connections", headers={"Authorization": f"Bearer {tokens['access_token']}"})
            orgs = [t for t in tenants if t.get("tenantType") == "ORGANISATION"]
            if not orgs:
                raise IntegrationError("No Xero organisation was shared. Connect again and choose your organisation.")
            return orgs[0].get("tenantName"), orgs[0].get("tenantId")
        return None, None

    @app.post("/integrations/<int:conn_id>/disconnect")
    def oauth_disconnect(conn_id):
        conn = one("SELECT * FROM connections WHERE id=? AND workspace_id=?", conn_id, ws())
        if conn is None:
            abort(404)
        if conn["user_id"] != g.user["id"]:
            auth.admin_required()
        get_db().execute("DELETE FROM connections WHERE id=?", (conn_id,))
        get_db().commit()
        flash(f"{providers()[conn['provider']]['name']} disconnected. Records already logged are kept.", "ok")
        return redirect(url_for("integrations"))

    @app.post("/integrations/<int:conn_id>/sync")
    def oauth_sync(conn_id):
        conn = one("SELECT * FROM connections WHERE id=? AND workspace_id=?", conn_id, ws())
        if conn is None:
            abort(404)
        flash(run_sync(conn), "ok")
        return redirect(url_for("integrations"))

    @app.get("/cron/sync")
    def cron_sync():
        """Vercel Cron calls this with "Authorization: Bearer <CRON_SECRET>"."""
        secret = current_app.config.get("CRON_SECRET")
        given = request.headers.get("Authorization", "").removeprefix("Bearer ")
        if not secret or not hmac.compare_digest(given, secret):
            abort(401)
        started, results = time.monotonic(), []
        for conn in rows("SELECT * FROM connections WHERE provider IN ('google','microsoft','xero') ORDER BY last_sync_at"):
            if time.monotonic() - started > 45:  # leave the rest for the next run
                break
            results.append({"connection": conn["id"], "result": run_sync(conn)})
        import documents
        reminders = documents.send_due_reminders()
        import webhooks
        delivered = webhooks.retry_due(budget=20)
        import assistant
        return jsonify(synced=len(results), results=results, reminders=reminders, webhooks=delivered,
                       assistant_conversations_deleted=assistant.purge())
