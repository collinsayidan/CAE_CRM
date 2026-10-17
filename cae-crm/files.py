"""Files attached to contacts, companies, deals and tickets: contracts, purchase orders, photos.

Stored in Supabase Storage (a private bucket) when SUPABASE_URL and SUPABASE_SERVICE_KEY are set, and downloaded
through short-lived signed links; otherwise kept in the database, which suits local use and small teams. Files go
through the app, so each is limited to 4 MB (Vercel's request limit is 4.5 MB). Types that could run code are refused."""

import base64
import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request

from flask import Response, abort, current_app, flash, g, redirect, request, url_for

from core import now, one, rows, ws
from db import get_db

MAX_BYTES = 4 * 1024 * 1024
ALLOWED = {"pdf", "png", "jpg", "jpeg", "gif", "webp", "heic", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods",
           "odp", "rtf", "txt", "csv", "zip", "msg", "eml"}
RECORDS = {"contact": "contacts", "company": "companies", "deal": "deals", "ticket": "tickets"}


class StorageError(Exception):
    pass


def bucket_config():
    c = current_app.config
    if c.get("SUPABASE_URL") and c.get("SUPABASE_SERVICE_KEY"):
        return c["SUPABASE_URL"].rstrip("/"), c["SUPABASE_SERVICE_KEY"], c.get("STORAGE_BUCKET") or "attachments"
    return None


def _storage(method, path, body=None, content_type="application/json"):
    url, key, _ = bucket_config()
    req = urllib.request.Request(f"{url}/storage/v1{path}", data=body, method=method, headers={
        "Authorization": f"Bearer {key}", "apikey": key, "Content-Type": content_type})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
        raise StorageError(f"File storage didn't respond as expected ({getattr(e, 'code', e)}).") from None


def put(key, data, content_type):
    if bucket_config():
        _, _, bucket = bucket_config()
        _storage("POST", f"/object/{bucket}/{urllib.parse.quote(key)}", data, content_type or "application/octet-stream")
        return None
    return base64.b64encode(data).decode()  # kept in the database row


def remove(attachments):
    """Delete stored files for attachment rows that are going away."""
    keys = [a["storage_key"] for a in attachments if a["storage_key"] and not a["content"]]
    if keys and bucket_config():
        _, _, bucket = bucket_config()
        try:
            _storage("DELETE", f"/object/{bucket}", json.dumps({"prefixes": keys}).encode())
        except StorageError:
            current_app.logger.warning("Couldn't delete %s stored files", len(keys))


def delete_for(record_type, record_id, workspace_id=None):
    """Remove a record's files, for example when a contact's personal data is erased."""
    found = rows("SELECT * FROM attachments WHERE workspace_id=? AND record_type=? AND record_id=?",
                 workspace_id or ws(), record_type, record_id)
    remove(found)
    get_db().execute("DELETE FROM attachments WHERE workspace_id=? AND record_type=? AND record_id=?",
                     (workspace_id or ws(), record_type, record_id))


def for_record(record_type, record_id):
    return rows("SELECT id, filename, size, uploaded_by, created_at FROM attachments WHERE workspace_id=? AND record_type=? "
                "AND record_id=? ORDER BY id DESC", ws(), record_type, record_id)


def human_size(n):
    return f"{n / 1024 / 1024:.1f} MB" if n >= 1024 * 1024 else f"{max(1, round(n / 1024))} KB"


def register(app):
    app.add_template_global(for_record, "record_files")
    app.add_template_filter(human_size, "filesize")

    @app.post("/files")
    def upload_file():
        record_type, record_id = request.form.get("record_type"), request.form.get("record_id", "")
        table = RECORDS.get(record_type)
        if not table or not record_id.isdigit() or not one(f"SELECT 1 FROM {table} WHERE id=? AND workspace_id=?",
                                                          int(record_id), ws()):
            abort(404)
        back_to = redirect(request.form.get("next") if (request.form.get("next") or "").startswith("/") else url_for("overview"))
        upload = request.files.get("file")
        if not upload or not upload.filename:
            flash("Choose a file to attach.", "error")
            return back_to
        name = os.path.basename(upload.filename.replace("\\", "/")).lstrip(". ")[:150]
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in ALLOWED:
            flash(f"Files ending .{ext or '?'} can't be attached. PDFs, images, Office documents, text and zip files can.", "error")
            return back_to
        data = upload.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            flash("That file is over 4 MB. Attach a smaller copy, or share a link to it in a note.", "error")
            return back_to
        key = f"{ws()}/{record_type}/{record_id}/{secrets.token_hex(8)}-{name}"
        try:
            content = put(key, data, upload.mimetype)
        except StorageError as e:
            flash(f"File not attached. {e}", "error")
            return back_to
        db = get_db()
        db.insert("attachments", workspace_id=ws(), record_type=record_type, record_id=int(record_id), filename=name,
                  content_type=upload.mimetype or "application/octet-stream", size=len(data), storage_key=key,
                  content=content, uploaded_by=g.user["name"], created_at=now().isoformat(timespec="minutes"))
        db.commit()
        flash(f"Attached {name}.", "ok")
        return back_to

    @app.get("/files/<int:file_id>")
    def download_file(file_id):
        a = one("SELECT * FROM attachments WHERE id=? AND workspace_id=?", file_id, ws())
        if a is None:
            abort(404)
        if a["content"] is None and bucket_config():
            _, _, bucket = bucket_config()
            try:
                signed = _storage("POST", f"/object/sign/{bucket}/{urllib.parse.quote(a['storage_key'])}",
                                  json.dumps({"expiresIn": 60, "download": a["filename"]}).encode())
            except StorageError:
                abort(502)
            return redirect(f"{bucket_config()[0]}/storage/v1{signed.get('signedURL') or signed.get('signedUrl')}")
        resp = Response(base64.b64decode(a["content"] or ""), mimetype=a["content_type"])
        # Always a download, never shown in the page, and never sniffed as something else.
        resp.headers["Content-Disposition"] = f'attachment; filename="{a["filename"].replace(chr(34), "")}"'
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    @app.post("/files/<int:file_id>/delete")
    def delete_file(file_id):
        a = one("SELECT * FROM attachments WHERE id=? AND workspace_id=?", file_id, ws())
        if a is None:
            abort(404)
        if a["uploaded_by"] != g.user["name"] and g.user["role"] != "admin":
            abort(403)
        remove([a])
        db = get_db()
        db.execute("DELETE FROM attachments WHERE id=?", (file_id,))
        db.commit()
        flash(f"Removed {a['filename']}.", "ok")
        return redirect(request.form.get("next") if (request.form.get("next") or "").startswith("/") else url_for("overview"))
