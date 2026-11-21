"""Role and record visibility enforced at the shared database boundary.

Legacy member access is unchanged. Admins choose own, department or workspace visibility.
The policy rewrites only our application's SQL, never accepts SQL from a user.
"""

import re
from flask import abort, g, has_request_context, request

ROLE_AREAS = {
    "admin": {"crm", "sales", "support", "finance", "marketing", "delivery"},
    "member": {"crm", "sales", "support", "finance", "marketing", "delivery"},
    "manager": {"crm", "sales", "support", "finance", "marketing", "delivery"},
    "sales": {"crm", "sales", "delivery"},
    "support": {"crm", "support"},
    "finance": {"crm", "finance"},
}
AREAS = {
    "contacts": "crm",
    "companies": "crm",
    "deals": "sales",
    "tickets": "support",
    "invoices": "finance",
    "quotes": "sales",
    "products": "sales",
    "projects": "delivery",
    "activities": "crm",
    "engagements": "crm",
    "email_campaigns": "marketing",
}
CHILDREN = {
    "line_items": ("deals", "deal_id"),
    "quote_lines": ("quotes", "quote_id"),
    "invoice_lines": ("invoices", "invoice_id"),
    "invoice_payments": ("invoices", "invoice_id"),
    "credit_notes": ("invoices", "invoice_id"),
    "campaign_recipients": ("email_campaigns", "campaign_id"),
}
RESERVED = {
    "where",
    "join",
    "left",
    "right",
    "inner",
    "outer",
    "on",
    "group",
    "order",
    "limit",
    "offset",
    "union",
    "having",
    "cross",
    "returning",
}


OWNER_TABLES = {"companies", "contacts", "deals", "tickets", "activities", "projects"}


def prepare_ownership(sql, params):
    # Keep the immutable owner reference in sync with existing assignment handlers.
    # Our owner-changing statements use bound values and a plain SET list.
    match = re.match(r"\s*UPDATE\s+(\w+)\s+SET\b", sql, re.I)
    if not match or match[1] not in OWNER_TABLES:
        return sql, params
    first_where = re.search(r"\s+WHERE\b", sql[match.end() :], re.I)
    set_end = match.end() + first_where.start() if first_where else len(sql)
    change = re.search(r"\bowner\s*=\s*\?", sql[:set_end], re.I)
    if not change:
        return sql, params
    where = re.search(r"\s+WHERE\b", sql[change.end() :], re.I)
    end = change.end() + where.start() if where else len(sql)
    owner_index = sql[: change.end()].count("?") - 1
    parameters = list(params)
    insert_at = sql[:end].count("?")
    parameters.insert(insert_at, params[owner_index])
    table = match[1]
    expression = f", owner_id=(SELECT MIN(u.id) FROM users u WHERE u.workspace_id={table}.workspace_id AND u.name=? HAVING COUNT(*)=1) "
    return sql[:end] + expression + sql[end:], parameters


def staff_in_scope(person):
    if not active() or g.user["role"] == "admin" or g.user["record_scope"] == "workspace":
        return True
    if g.user["record_scope"] == "own":
        return person["id"] == g.user["id"]
    return person["id"] == g.user["id"] or bool(
        g.user["department"] and person["department"] == g.user["department"]
    )


def active():
    return (
        has_request_context()
        and g.get("user")
        and not g.get("public_workspace")
        and request.blueprint != "api"
    )


def can(area):
    return not active() or area in ROLE_AREAS.get(g.user["role"], set())


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def policy(db, table):
    if g.user["role"] == "admin" or (
        g.user["role"] in ("member", "manager") and g.user["record_scope"] == "workspace"
    ):
        return None
    if table == "attachments":
        clauses = []
        for kind, parent in (
            ("contact", "contacts"),
            ("company", "companies"),
            ("deal", "deals"),
            ("ticket", "tickets"),
        ):
            p = policy(db, parent) or "1=1"
            clauses.append(f"(record_type='{kind}' AND record_id IN (SELECT id FROM {parent} WHERE {p}))")
        return "(" + " OR ".join(clauses) + ")"
    if table == "engagements":
        gates = []
        for key, parent in (
            ("contact_id", "contacts"),
            ("company_id", "companies"),
            ("deal_id", "deals"),
            ("ticket_id", "tickets"),
        ):
            p = policy(db, parent)
            if p:
                gates.append(f"({key} IS NULL OR {key} IN (SELECT id FROM {parent} WHERE {p}))")
        return " AND ".join(gates) or None
    if table in CHILDREN:
        parent, key = CHILDREN[table]
        p = policy(db, parent)
        return f"{key} IN (SELECT id FROM {parent} WHERE {p})" if p else None
    if table not in AREAS:
        return None
    if not can(AREAS[table]):
        return "1=0"
    user = g.user
    scope = user["record_scope"]
    if user["role"] == "admin" or scope == "workspace":
        return None
    identifiers = [user["id"]]
    if scope == "team" and user["department"]:
        marks = "%s" if db.postgres else "?"
        identifiers = [
            r[0]
            for r in db.conn.execute(
                f"SELECT id FROM users WHERE workspace_id={marks} AND department={marks}",
                (user["workspace_id"], user["department"]),
            )
        ]
    if table in ("invoices", "quotes"):
        return "company_id IN (SELECT id FROM companies WHERE " + policy(db, "companies") + ")"
    if table in ("products", "email_campaigns"):
        return "1=0" if table == "email_campaigns" else None
    return "owner_id IN (" + ",".join(str(int(identifier)) for identifier in identifiers) + ")"


def secure_sql(db, sql):
    if not active():
        return sql
    # Queries use parameter binding; the only inserted values are escaped identity values.
    if re.match(r"\s*SELECT\b", sql, re.I):
        pattern = (
            r"\b(FROM|JOIN)\s+(" + "|".join({**AREAS, **CHILDREN, "attachments": "crm"}) + r")\b(?!\s*\()"
        )

        def sub(m):
            table = m[2]
            p = policy(db, table)
            if not p:
                return m[0]
            tail = sql[m.end() :]
            alias = re.match(r"\s+(?:AS\s+)?([a-zA-Z_]\w*)", tail, re.I)
            has_alias = alias and alias[1].lower() not in RESERVED
            return f"{m[1]} (SELECT * FROM {table} WHERE {p})" + ("" if has_alias else f" AS {table}")

        return re.sub(pattern, sub, sql, flags=re.I)
    m = re.match(r"\s*(?:UPDATE|DELETE FROM)\s+(\w+)\b", sql, re.I)
    if m:
        p = policy(db, m[1])
        if p == "1=0":
            abort(403)
        if p:
            # Locate outer WHERE/RETURNING tokens without confusing nested subqueries or strings.
            depth = 0
            quoted = False
            tokens = []
            i = 0
            while i < len(sql):
                char = sql[i]
                if char == "'":
                    if quoted and i + 1 < len(sql) and sql[i + 1] == "'":
                        i += 2
                        continue
                    quoted = not quoted
                    i += 1
                    continue
                if not quoted:
                    if char == "(":
                        depth += 1
                    elif char == ")":
                        depth -= 1
                    elif depth == 0 and (char.isalpha() or char == "_"):
                        match = re.match(r"[A-Za-z_]+", sql[i:])
                        word = match[0].upper()
                        if word in ("WHERE", "RETURNING"):
                            tokens.append((word, i, i + len(word)))
                        i += len(word)
                        continue
                i += 1
            where = next((t for t in tokens if t[0] == "WHERE"), None)
            returning = next((t for t in tokens if t[0] == "RETURNING"), None)
            end = returning[1] if returning else len(sql)
            if where:
                original = sql[where[2] : end].strip().rstrip(";")
                sql = sql[: where[2]] + f" ({original}) AND ({p}) " + sql[end:]
            else:
                sql = sql[:end].rstrip().rstrip(";") + f" WHERE {p} " + sql[end:]

    return sql


def check_insert(db, table, values):
    if not active():
        return
    if table in AREAS and not can(AREAS[table]):
        abort(403)
    if table in AREAS and g.user["role"] != "admin" and g.user["record_scope"] != "workspace":
        if "owner" in values:
            owner = values["owner"]
            if owner != g.user["name"]:
                allowed = (
                    g.user["record_scope"] == "team"
                    and g.user["department"]
                    and db.execute(
                        "SELECT id FROM users WHERE workspace_id=? AND department=? AND name=?",
                        (g.user["workspace_id"], g.user["department"], owner),
                    ).fetchone()
                )
                if not allowed:
                    abort(403)


def navigation(nav):
    mapping = {
        "pipeline": "sales",
        "forecast_page": "sales",
        "quotes": "sales",
        "products": "sales",
        "tickets": "support",
        "knowledge_base": "support",
        "invoices": "finance",
        "projects": "delivery",
        "campaigns": "marketing",
        "forms": "marketing",
    }
    result = []
    for heading, items in nav:
        shown = [
            item
            for item in items
            if can(mapping.get(item[0], "crm")) and (item[0] != "sequences_page" or g.user["role"] == "admin")
        ]
        if shown:
            result.append((heading, shown))
    return result
