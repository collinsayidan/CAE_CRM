"""The recycle bin: deleted contacts, companies, deals and tickets can be restored for 30 days (admins only).

Deleting saves a snapshot of the record and everything removed with it (its timeline, line items, tasks, quotes, tags)
plus the links that were cleared on other records (a deal's contact, a ticket's company), then deletes for real, so no
other page needs to know about deleted records. Files stay in storage, set aside under the bin entry. Restoring puts
the rows back with new ids, re-links them, and brings the files back. After 30 days the daily job empties the bin, and
admins can delete an entry permanently straight away, for example to meet a UK GDPR erasure request."""

import json
from datetime import datetime, timedelta

from flask import abort, current_app, flash, g, redirect, render_template, request, url_for

import auth
from core import now, one, rows, ws
from db import get_db

KEEP_DAYS = 30
TYPES = {"contacts": "contact", "companies": "company", "deals": "deal", "tickets": "ticket"}
LABELS = {"contact": "Contact", "company": "Company", "deal": "Deal", "ticket": "Ticket"}
# What happens to other rows when a record is deleted: (table, column, "cascade" to delete them with it, or "unlink"
# to clear the column, and an optional extra condition). Mirrors the database's ON DELETE rules and delete_company_records.
DEPENDENTS = {
    "companies": [("contacts", "company_id", "unlink", None), ("tickets", "company_id", "unlink", None),
                  ("engagements", "company_id", "unlink", "contact_id IS NOT NULL"),
                  ("engagements", "company_id", "cascade", None), ("deals", "company_id", "cascade", None),
                  ("activities", "company_id", "cascade", None), ("projects", "company_id", "cascade", None),
                  ("quotes", "company_id", "cascade", None)],
    "deals": [("line_items", "deal_id", "cascade", None), ("engagements", "deal_id", "cascade", None),
              ("activities", "deal_id", "unlink", None), ("quotes", "deal_id", "unlink", None),
              ("projects", "deal_id", "unlink", None), ("invoices", "deal_id", "unlink", None)],
    "contacts": [("engagements", "contact_id", "cascade", None), ("form_submissions", "contact_id", "cascade", None),
                 ("campaign_recipients", "contact_id", "cascade", None), ("deals", "contact_id", "unlink", None),
                 ("activities", "contact_id", "unlink", None), ("tickets", "contact_id", "unlink", None),
                 ("quotes", "contact_id", "unlink", None)],
    "tickets": [("engagements", "ticket_id", "cascade", None)],
    "quotes": [("quote_lines", "quote_id", "cascade", None)],
}
# Parents come back before children.
RESTORE_ORDER = ["companies", "contacts", "deals", "tickets", "quotes", "quote_lines", "line_items", "projects",
                 "activities", "engagements", "form_submissions", "campaign_recipients", "record_tags"]
# Columns pointing at other rows: column -> (table, whether the row can't exist without it).
FOREIGN = {"company_id": ("companies", False), "contact_id": ("contacts", False), "deal_id": ("deals", False),
           "ticket_id": ("tickets", False), "quote_id": ("quotes", True), "product_id": ("products", False),
           "invoice_id": ("invoices", False), "campaign_id": ("email_campaigns", True), "form_id": ("web_forms", True),
           "tag_id": ("tags", True)}
REQUIRED_PARENTS = {"deals": ["company_id"], "quotes": ["company_id"], "projects": ["company_id"],
                    "line_items": ["deal_id"]}


def label_for(table, row):
    if table == "contacts":
        return f"{row['first_name']} {row['last_name']}".strip()
    return row.get("name") or row.get("title") or row.get("subject") or f"#{row['id']}"


def capture(table, record_id):
    """The snapshot of a record and what goes with it: {rows: {table: [row]}, unlinks: [[table, column, [ids],
    parent id]], records: [[type, id]]}."""
    taken, unlinks = {}, []

    def visit(t, rid):
        row = one(f"SELECT * FROM {t} WHERE id=? AND workspace_id=?", rid, ws())
        if row is None or rid in taken.get(t, {}):
            return
        taken.setdefault(t, {})[rid] = dict(row)
        cleared = set()  # rows this record unlinks rather than deletes
        for child, column, how, condition in DEPENDENTS.get(t, []):
            sql = f"SELECT id FROM {child} WHERE workspace_id=? AND {column}=?" + (f" AND {condition}" if condition else "")
            ids = [r[0] for r in rows(sql, ws(), rid) if r[0] not in taken.get(child, {}) and (child, r[0]) not in cleared]
            if how == "unlink":
                cleared.update((child, i) for i in ids)
                if ids:
                    unlinks.append([child, column, ids, rid])
            else:
                for i in ids:
                    visit(child, i)

    visit(table, record_id)
    records = [[TYPES[t], rid] for t in TYPES for rid in taken.get(t, {})]
    tagged = [dict(r) for kind, rid in records if kind in ("contact", "company")
              for r in rows("SELECT * FROM record_tags WHERE workspace_id=? AND record_type=? AND record_id=?",
                            ws(), kind, rid)]
    if tagged:
        taken["record_tags"] = {r["id"]: r for r in tagged}
    return {"rows": {t: list(found.values()) for t, found in taken.items()}, "unlinks": unlinks, "records": records}


def delete(table, record_id):
    """Move a record (and what goes with it) to the bin. No commit."""
    db = get_db()
    snap = capture(table, record_id)
    root = snap["rows"][table][0]
    entry = db.insert("recycle_bin", workspace_id=ws(), record_type=TYPES[table], record_id=record_id,
                      label=label_for(table, root)[:200], deleted_by=g.user["name"] if g.get("user") else "CAE CRM",
                      deleted_at=now().isoformat(timespec="minutes"), snapshot=json.dumps(snap, default=str))
    for kind, rid in snap["records"]:  # files wait in storage under the bin entry
        db.execute("UPDATE attachments SET record_type=? WHERE workspace_id=? AND record_type=? AND record_id=?",
                   (f"bin{entry}:{kind}", ws(), kind, rid))
    for child, column, ids, _ in snap["unlinks"]:
        db.execute(f"UPDATE {child} SET {column}=NULL WHERE workspace_id=? AND id IN ({','.join('?' * len(ids))})",
                   (ws(), *ids))
    for kind, rid in snap["records"]:
        if kind in ("contact", "company"):
            db.execute("DELETE FROM record_tags WHERE workspace_id=? AND record_type=? AND record_id=?", (ws(), kind, rid))
    db.execute(f"DELETE FROM {table} WHERE id=? AND workspace_id=?", (record_id, ws()))  # the database cascades the rest
    return entry


class RestoreError(Exception):
    pass


def current_id(table, old_id):
    """Where a row is now: rows restored from the bin come back with new ids, which later restores follow."""
    seen = set()
    while (table, old_id) not in seen:
        seen.add((table, old_id))
        moved = one("SELECT new_id FROM recycle_ids WHERE workspace_id=? AND table_name=? AND old_id=?", ws(), table, old_id)
        if moved is None:
            break
        old_id = moved[0]
    return old_id


def restore(entry):
    """Put a bin entry back. Returns the restored record's new id. Raises RestoreError with a reason. No commit."""
    db = get_db()
    snap = json.loads(entry["snapshot"])
    table = next(t for t, kind in TYPES.items() if kind == entry["record_type"])
    root = snap["rows"][table][0]
    for column in REQUIRED_PARENTS.get(table, []):
        parent, _ = FOREIGN[column]
        if root.get(column) and not one(f"SELECT 1 FROM {parent} WHERE id=? AND workspace_id=?",
                                        current_id(parent, root[column]), ws()):
            waiting = one("SELECT label FROM recycle_bin WHERE workspace_id=? AND record_type=? AND record_id=?", ws(),
                          TYPES.get(parent, ""), root[column])
            raise RestoreError(f"Restore {waiting[0]} first: this {LABELS[entry['record_type']].lower()} belongs to it."
                               if waiting else "What it belonged to has been deleted for good, so it can't come back.")
    new_ids = {}  # (table, old id) -> new id
    columns = {}
    for t in RESTORE_ORDER:
        for row in snap["rows"].get(t, []):
            columns.setdefault(t, db.columns(t))
            values = {k: v for k, v in row.items() if k in columns[t] and k != "id"}
            skip = False
            for column, (target, required) in FOREIGN.items():
                if column not in values or values[column] is None:
                    continue
                if (target, values[column]) in new_ids:
                    values[column] = new_ids[target, values[column]]
                    continue
                values[column] = current_id(target, values[column])
                if not one(f"SELECT 1 FROM {target} WHERE id=? AND workspace_id=?", values[column], ws()):
                    if required or (t in REQUIRED_PARENTS and column in REQUIRED_PARENTS[t]):
                        skip = True
                        break
                    values[column] = None
            if t == "record_tags" and not skip:
                kind_table = {"contact": "contacts", "company": "companies"}[values["record_type"]]
                values["record_id"] = new_ids.get((kind_table, values["record_id"]), values["record_id"])
            if t == "quotes" and not skip:
                if one("SELECT 1 FROM quotes WHERE workspace_id=? AND number=?", ws(), values["number"]):
                    values["number"] = f"{values['number']}-R"
                if one("SELECT 1 FROM quotes WHERE token=?", values["token"]):
                    import secrets
                    values["token"] = secrets.token_urlsafe(24)
            if skip:
                continue
            new_ids[t, row["id"]] = db.insert(t, **values)
            db.insert("recycle_ids", workspace_id=ws(), table_name=t, old_id=row["id"], new_id=new_ids[t, row["id"]],
                      created_at=now().isoformat(timespec="minutes"))
    for child, column, ids, parent_id in snap["unlinks"]:
        parent_table = next(t for t, deps in DEPENDENTS.items() for d in deps if d[0] == child and d[1] == column)
        new_parent = new_ids.get((parent_table, parent_id))
        ids = [current_id(child, i) for i in ids]
        if new_parent and ids:
            db.execute(f"UPDATE {child} SET {column}=? WHERE workspace_id=? AND {column} IS NULL AND id IN "
                       f"({','.join('?' * len(ids))})", (new_parent, ws(), *ids))
    for kind, rid in snap["records"]:
        kind_table = next(t for t, k in TYPES.items() if k == kind)
        if (kind_table, rid) in new_ids:
            db.execute("UPDATE attachments SET record_type=?, record_id=? WHERE workspace_id=? AND record_type=? AND "
                       "record_id=?", (kind, new_ids[kind_table, rid], ws(), f"bin{entry['id']}:{kind}", rid))
    db.execute("DELETE FROM recycle_bin WHERE id=?", (entry["id"],))
    return new_ids[table, root["id"]]


def empty(entry, workspace_id=None):
    """Delete a bin entry for good, with its files. No commit."""
    from files import delete_for
    snap = json.loads(entry["snapshot"])
    for kind, rid in snap["records"]:
        delete_for(f"bin{entry['id']}:{kind}", rid, workspace_id or entry["workspace_id"])
    get_db().execute("DELETE FROM recycle_bin WHERE id=?", (entry["id"],))


def purge():
    """For the daily job: empty entries older than 30 days."""
    cutoff = (now() - timedelta(days=KEEP_DAYS)).isoformat(timespec="minutes")
    old = rows("SELECT * FROM recycle_bin WHERE deleted_at < ?", cutoff)
    # Old-to-new ids are only needed while something that refers to them could still be restored.
    get_db().execute("DELETE FROM recycle_ids WHERE created_at < ?",
                     ((now() - timedelta(days=KEEP_DAYS * 2)).isoformat(timespec="minutes"),))
    for entry in old:
        try:
            empty(entry, entry["workspace_id"])
        except Exception:  # a storage hiccup shouldn't stop the rest; it's retried tomorrow
            current_app.logger.exception("Recycle bin entry %s not emptied", entry["id"])
    get_db().commit()
    return len(old)


def register(app):

    @app.get("/settings/recycle-bin")
    def recycle_bin():
        auth.admin_required()
        entries = rows("SELECT id, record_type, record_id, label, deleted_by, deleted_at FROM recycle_bin "
                       "WHERE workspace_id=? ORDER BY id DESC", ws())
        expires = {e["id"]: (datetime.fromisoformat(e["deleted_at"]) + timedelta(days=KEEP_DAYS)).isoformat()
                   for e in entries}
        return render_template("recycle_bin.html", entries=entries, labels=LABELS, keep_days=KEEP_DAYS, expires=expires)

    def entry_or_404(entry_id):
        e = one("SELECT * FROM recycle_bin WHERE id=? AND workspace_id=?", entry_id, ws())
        if e is None:
            abort(404)
        return e

    @app.post("/settings/recycle-bin/<int:entry_id>/restore")
    def restore_from_bin(entry_id):
        auth.admin_required()
        e = entry_or_404(entry_id)
        try:
            new_id = restore(e)
        except RestoreError as err:
            get_db().rollback()
            flash(str(err), "error")
            return redirect(url_for("recycle_bin"))
        from core import log_event
        kind = e["record_type"]
        link = {f"{kind}_id": new_id}
        log_event(f"Restored from the recycle bin by {g.user['name']}", None, **link)
        get_db().commit()
        flash(f"Restored {e['label']}.", "ok")
        return redirect(url_for(kind, **link))

    @app.post("/settings/recycle-bin/<int:entry_id>/delete")
    def delete_from_bin(entry_id):
        auth.admin_required()
        e = entry_or_404(entry_id)
        empty(e, ws())
        get_db().commit()
        flash(f"Deleted {e['label']} permanently.", "ok")
        return redirect(url_for("recycle_bin"))
