"""Finding and merging duplicate contacts and companies (admins only).

Likely duplicates are found by the same email, phone number, or name at the same company (contacts), and by the same
Companies House number, name ignoring "Ltd" and punctuation, or website (companies). Merging keeps the record the admin
chooses, fills its empty fields from the other, moves everything linked to the other across, notes the merge on the
timeline, and deletes the other. On consent it takes the safer side: an unsubscribe or bounce on either record wins.
"Not duplicates" hides a pair for good."""

import json
import re
from collections import defaultdict
from urllib.parse import urlsplit

from flask import abort, flash, g, redirect, render_template, request, url_for

import auth
import tags
from core import log_event, now, one, rows, ws
from db import LIFECYCLE_STAGES, get_db
from events import emit

KINDS = {"contacts": "contact", "companies": "company"}
NAME_NOISE = re.compile(r"\b(ltd|limited|plc|llp|lp|cic|co|company|uk|group|the|and)\b")
# Fields filled in from the duplicate when the kept record has none.
CONTACT_FIELDS = ["company_id", "role", "email", "phone", "owner", "lead_status", "lawful_basis"]
COMPANY_FIELDS = ["company_no", "vat_no", "industry", "address", "city", "postcode", "region", "website", "phone", "owner"]
# Tables whose rows point at a contact or a company, and so move to the kept one.
CONTACT_LINKS = ["deals", "activities", "engagements", "tickets", "quotes", "form_submissions", "campaign_recipients"]
COMPANY_LINKS = ["contacts", "deals", "activities", "engagements", "tickets", "invoices", "quotes", "projects"]


def phone_key(phone):
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("44"):
        digits = "0" + digits[2:]
    return digits if len(digits) >= 10 else None


def name_key(name):
    plain = NAME_NOISE.sub(" ", re.sub(r"[^a-z0-9 ]", " ", (name or "").lower().replace("&", " and ")))
    plain = re.sub(r"\s+", " ", plain).strip()
    return plain or None


def site_key(website):
    if not website:
        return None
    host = urlsplit(website if "://" in website else "https://" + website).hostname or ""
    host = host.lower().removeprefix("www.")
    return host if "." in host else None


def dismissed(record_type):
    return {(r[0], r[1]) for r in rows("SELECT low_id, high_id FROM duplicate_dismissals WHERE workspace_id=? AND "
                                       "record_type=?", ws(), record_type)}


def find(obj):
    """Likely duplicate pairs: [(record a, record b, [reasons])], a's id lower than b's."""
    record_type = KINDS[obj]
    if obj == "contacts":
        found = rows("SELECT ct.*, c.name AS company FROM contacts ct LEFT JOIN companies c ON c.id=ct.company_id "
                     "WHERE ct.workspace_id=? ORDER BY ct.id", ws())
        keys = [("the same email", lambda r: (r["email"] or "").strip().lower() or None),
                ("the same phone number", lambda r: phone_key(r["phone"])),
                ("the same name at the same company",
                 lambda r: f"{r['first_name']} {r['last_name']}".strip().lower() + f"|{r['company_id']}"
                 if r["company_id"] else None)]
    else:
        found = rows("SELECT * FROM companies WHERE workspace_id=? ORDER BY id", ws())
        keys = [("the same Companies House number", lambda r: (r["company_no"] or "").strip().upper() or None),
                ("the same name", lambda r: name_key(r["name"])),
                ("the same website", lambda r: site_key(r["website"]))]
    by_id = {r["id"]: r for r in found}
    reasons = defaultdict(list)
    for label, key in keys:
        groups = defaultdict(list)
        for r in found:
            k = key(r)
            if k:
                groups[k].append(r["id"])
        for ids in groups.values():
            for i, a in enumerate(ids):
                for b in ids[i + 1:]:
                    reasons[(a, b)].append(label)
    hidden = dismissed(record_type)
    return [(by_id[a], by_id[b], why) for (a, b), why in sorted(reasons.items()) if (a, b) not in hidden][:100]


def _fill(table, fields, keep, drop):
    """Fill the kept record's empty fields from the duplicate."""
    updates = {f: drop[f] for f in fields if not keep[f] and drop[f]}
    custom = {**json.loads(drop["custom"] or "{}"), **json.loads(keep["custom"] or "{}")}
    updates["custom"] = json.dumps(custom) if custom else None
    if updates:
        get_db().execute(f"UPDATE {table} SET {', '.join(f'{k}=?' for k in updates)} WHERE id=? AND workspace_id=?",
                         (*updates.values(), keep["id"], ws()))


def _move_files_and_tags(record_type, keep_id, drop_id):
    db = get_db()
    db.execute("UPDATE attachments SET record_id=? WHERE workspace_id=? AND record_type=? AND record_id=?",
               (keep_id, ws(), record_type, drop_id))
    for t in tags.tags_of(record_type, drop_id):
        tags.add(record_type, keep_id, t["name"])
    tags.forget(record_type, drop_id)


def merge_contacts(keep, drop):
    db = get_db()
    _fill("contacts", CONTACT_FIELDS, keep, drop)
    stages = [s for s in (keep["lifecycle_stage"], drop["lifecycle_stage"]) if s in LIFECYCLE_STAGES and s != "Other"]
    if stages:
        db.execute("UPDATE contacts SET lifecycle_stage=? WHERE id=?", (max(stages, key=LIFECYCLE_STAGES.index), keep["id"]))
    # Consent: an unsubscribe or a bounce on either record wins; otherwise consent given on either counts.
    unsubscribed = min(filter(None, [keep["unsubscribed_at"], drop["unsubscribed_at"]]), default=None)
    bounced = min(filter(None, [keep["email_bounced_at"], drop["email_bounced_at"]]), default=None)
    consent, consent_date = keep["marketing_consent"], keep["consent_date"]
    if not consent and drop["marketing_consent"]:
        consent, consent_date = drop["marketing_consent"], drop["consent_date"]
    if unsubscribed:
        consent = 0
    db.execute("UPDATE contacts SET unsubscribed_at=?, email_bounced_at=?, marketing_consent=?, consent_date=? WHERE id=?",
               (unsubscribed, bounced, consent, consent_date, keep["id"]))
    for table in CONTACT_LINKS:
        db.execute(f"UPDATE {table} SET contact_id=? WHERE workspace_id=? AND contact_id=?", (keep["id"], ws(), drop["id"]))
    _move_files_and_tags("contact", keep["id"], drop["id"])
    name = f"{drop['first_name']} {drop['last_name']}".strip()
    log_event(f"Merged with a duplicate: {name}", f"Merged by {g.user['name']}. Their timeline, deals and tickets are "
              "now on this contact.", contact_id=keep["id"], company_id=keep["company_id"] or drop["company_id"])
    db.execute("DELETE FROM contacts WHERE id=? AND workspace_id=?", (drop["id"], ws()))
    emit("contact.updated", keep["id"])


def merge_companies(keep, drop):
    db = get_db()
    _fill("companies", COMPANY_FIELDS, keep, drop)
    for table in COMPANY_LINKS:
        db.execute(f"UPDATE {table} SET company_id=? WHERE workspace_id=? AND company_id=?", (keep["id"], ws(), drop["id"]))
    _move_files_and_tags("company", keep["id"], drop["id"])
    log_event(f"Merged with a duplicate: {drop['name']}", f"Merged by {g.user['name']}. Its people, deals, tickets and "
              "invoices are now on this company.", company_id=keep["id"])
    db.execute("DELETE FROM companies WHERE id=? AND workspace_id=?", (drop["id"], ws()))
    emit("company.updated", keep["id"])


def register(app):

    @app.get("/duplicates/<obj>")
    def duplicates(obj):
        auth.admin_required()
        if obj not in KINDS:
            abort(404)
        return render_template("duplicates.html", obj=obj, pairs=find(obj))

    @app.post("/duplicates/<obj>/merge")
    def merge_duplicates(obj):
        auth.admin_required()
        if obj not in KINDS:
            abort(404)
        pair = [i for i in request.form.getlist("pair") if i.isdigit()]
        keep_id = request.form.get("keep", "")
        if len(set(pair)) != 2 or keep_id not in pair:
            abort(400)
        drop_id = next(i for i in pair if i != keep_id)
        keep = one(f"SELECT * FROM {obj} WHERE id=? AND workspace_id=?", int(keep_id), ws())
        drop = one(f"SELECT * FROM {obj} WHERE id=? AND workspace_id=?", int(drop_id), ws())
        if keep is None or drop is None:
            abort(404)
        (merge_contacts if obj == "contacts" else merge_companies)(keep, drop)
        get_db().commit()
        label = f"{keep['first_name']} {keep['last_name']}" if obj == "contacts" else keep["name"]
        flash(f"Merged into {label}.", "ok")
        return redirect(url_for("duplicates", obj=obj))

    @app.post("/duplicates/<obj>/dismiss")
    def dismiss_duplicates(obj):
        auth.admin_required()
        if obj not in KINDS:
            abort(404)
        ids = sorted(int(i) for i in request.form.getlist("ids") if i.isdigit())
        if len(ids) != 2 or len(rows(f"SELECT id FROM {obj} WHERE workspace_id=? AND id IN (?, ?)", ws(), *ids)) != 2:
            abort(400)
        if (ids[0], ids[1]) not in dismissed(KINDS[obj]):
            get_db().insert("duplicate_dismissals", workspace_id=ws(), record_type=KINDS[obj], low_id=ids[0],
                            high_id=ids[1], created_at=now().isoformat(timespec="minutes"))
            get_db().commit()
        flash("Got it. That pair won't be suggested again.", "ok")
        return redirect(url_for("duplicates", obj=obj))
