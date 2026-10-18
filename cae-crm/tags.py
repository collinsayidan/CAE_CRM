"""Tags on contacts and companies, such as "VIP" or "Trade show 2026". People add and remove them on a record page or
in bulk from a list; lists filter by them, and a filtered list saved as a view is a segment that keeps itself up to
date. Admins rename and delete tags under Settings."""

import re

from flask import abort, flash, redirect, render_template, request, url_for

import auth
from core import back, now, one, owned, rows, ws
from db import get_db

MAX_NAME = 40
# Record type -> (table, page endpoint, URL argument).
RECORDS = {"contact": ("contacts", "contact", "contact_id"), "company": ("companies", "company", "company_id")}


def clean(name):
    return re.sub(r"\s+", " ", str(name or "")).strip()[:MAX_NAME]


def all_names():
    return [r[0] for r in rows("SELECT name FROM tags WHERE workspace_id=? ORDER BY LOWER(name)", ws())]


def tags_of(record_type, record_id):
    return rows("SELECT t.id, t.name FROM record_tags rt JOIN tags t ON t.id=rt.tag_id WHERE rt.workspace_id=? AND "
                "rt.record_type=? AND rt.record_id=? ORDER BY LOWER(t.name)", ws(), record_type, record_id)


def tags_for(record_type, ids):
    """{record id: [tag names]} for a page of a list."""
    out = {}
    if not ids:
        return out
    marks = ",".join("?" * len(ids))
    for r in rows(f"SELECT rt.record_id, t.name FROM record_tags rt JOIN tags t ON t.id=rt.tag_id WHERE rt.workspace_id=? "
                  f"AND rt.record_type=? AND rt.record_id IN ({marks}) ORDER BY LOWER(t.name)", ws(), record_type, *ids):
        out.setdefault(r[0], []).append(r[1])
    return out


def filter_clause(record_type, alias):
    """A list filter: records with the tag named by the parameter."""
    return (f"EXISTS (SELECT 1 FROM record_tags rt JOIN tags tg ON tg.id=rt.tag_id WHERE rt.record_type='{record_type}' "
            f"AND rt.record_id={alias}.id AND tg.name = ?)")


def tag_id(name, create=True):
    name = clean(name)
    if not name:
        return None
    found = one("SELECT id FROM tags WHERE workspace_id=? AND LOWER(name)=LOWER(?)", ws(), name)
    if found:
        return found[0]
    if not create:
        return None
    return get_db().insert("tags", workspace_id=ws(), name=name, created_at=now().isoformat(timespec="minutes"))


def add(record_type, record_id, name):
    """Tag a record (making the tag if it's new). Returns the tag's id, or None if the name is empty. No commit."""
    tid = tag_id(name)
    if tid and not one("SELECT 1 FROM record_tags WHERE tag_id=? AND record_type=? AND record_id=?",
                       tid, record_type, record_id):
        get_db().insert("record_tags", workspace_id=ws(), tag_id=tid, record_type=record_type, record_id=record_id)
    return tid


def remove(record_type, record_id, tid):
    get_db().execute("DELETE FROM record_tags WHERE workspace_id=? AND tag_id=? AND record_type=? AND record_id=?",
                     (ws(), tid, record_type, record_id))


def forget(record_type, record_id):
    """When a record is erased or deleted."""
    get_db().execute("DELETE FROM record_tags WHERE workspace_id=? AND record_type=? AND record_id=?",
                     (ws(), record_type, record_id))


def register(app):
    app.add_template_global(tags_of, "record_tags")
    app.add_template_global(all_names, "all_tag_names")

    @app.post("/tags/<record_type>/<int:record_id>")
    def add_tag(record_type, record_id):
        if record_type not in RECORDS:
            abort(404)
        table, page, arg = RECORDS[record_type]
        if not owned(table, record_id):
            abort(404)
        name = clean(request.form.get("name"))
        if not name:
            flash("Type a tag first.", "error")
        else:
            add(record_type, record_id, name)
            get_db().commit()
        return back(page, **{arg: record_id})

    @app.post("/tags/<record_type>/<int:record_id>/remove")
    def remove_tag(record_type, record_id):
        if record_type not in RECORDS:
            abort(404)
        table, page, arg = RECORDS[record_type]
        if not owned(table, record_id) or not request.form.get("tag_id", "").isdigit():
            abort(404)
        remove(record_type, record_id, int(request.form["tag_id"]))
        get_db().commit()
        return back(page, **{arg: record_id})

    @app.route("/settings/tags", methods=["GET", "POST"])
    def tags_settings():
        auth.admin_required()
        if request.method == "POST":
            db = get_db()
            tid = request.form.get("tag_id", "")
            tag = one("SELECT * FROM tags WHERE id=? AND workspace_id=?", int(tid), ws()) if tid.isdigit() else None
            if tag is None:
                abort(404)
            if request.form.get("action") == "delete":
                db.execute("DELETE FROM record_tags WHERE tag_id=? AND workspace_id=?", (tag["id"], ws()))
                db.execute("DELETE FROM tags WHERE id=? AND workspace_id=?", (tag["id"], ws()))
                flash(f"Deleted the tag {tag['name']}. Records keep everything else.", "ok")
            else:
                name = clean(request.form.get("name"))
                other = one("SELECT id FROM tags WHERE workspace_id=? AND LOWER(name)=LOWER(?) AND id<>?", ws(), name,
                            tag["id"]) if name else None
                if not name:
                    flash("A tag needs a name.", "error")
                    return redirect(url_for("tags_settings"))
                if other:  # renaming onto an existing tag merges the two
                    for r in rows("SELECT record_type, record_id FROM record_tags WHERE tag_id=?", tag["id"]):
                        if not one("SELECT 1 FROM record_tags WHERE tag_id=? AND record_type=? AND record_id=?",
                                   other[0], r["record_type"], r["record_id"]):
                            db.execute("UPDATE record_tags SET tag_id=? WHERE tag_id=? AND record_type=? AND record_id=?",
                                       (other[0], tag["id"], r["record_type"], r["record_id"]))
                    db.execute("DELETE FROM record_tags WHERE tag_id=?", (tag["id"],))
                    db.execute("DELETE FROM tags WHERE id=?", (tag["id"],))
                    flash(f"Merged {tag['name']} into {name}.", "ok")
                else:
                    db.execute("UPDATE tags SET name=? WHERE id=?", (name, tag["id"]))
                    flash(f"Renamed to {name}. Saved views that filter by the old name need updating.", "ok")
            db.commit()
            return redirect(url_for("tags_settings"))
        found = rows("SELECT t.*, (SELECT COUNT(*) FROM record_tags rt WHERE rt.tag_id=t.id AND rt.record_type='contact') "
                     "AS contacts, (SELECT COUNT(*) FROM record_tags rt WHERE rt.tag_id=t.id AND rt.record_type='company') "
                     "AS companies FROM tags t WHERE t.workspace_id=? ORDER BY LOWER(t.name)", ws())
        return render_template("tags.html", tags=found)


def bulk(record_type, ids, action, value):
    """Add or remove a tag on several records from a list. Returns a message, or None if the tag is unknown."""
    tid = tag_id(value, create=False)
    if not tid:
        return None
    for record_id in ids:
        if action == "tag_add":
            add(record_type, record_id, value)
        else:
            remove(record_type, record_id, tid)
    name = one("SELECT name FROM tags WHERE id=?", tid)[0]
    return f"{'Tagged' if action == 'tag_add' else 'Removed the tag from'} {len(ids)}: {name}."
