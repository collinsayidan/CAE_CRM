"""Move CAE CRM's data to another database: every table, row for row, plus attached files held in Supabase Storage.

Built to move off Supabase onto a PostgreSQL database run by Coolify, but it works between any two databases the app
supports. It reads both addresses from settings, so no password is typed or printed:

    DATABASE_URL           where the data is now (the source)
    TARGET_DATABASE_URL    where it's going; must be new and empty
    SUPABASE_URL, SUPABASE_SERVICE_KEY, CAE_STORAGE_BUCKET
                           if set, files kept in Supabase Storage are downloaded and stored in the database instead

Run it inside the app's container:

    python move_database.py --check   counts rows on both sides and changes nothing
    python move_database.py           copies everything, then checks every table's row count matches

The source is only ever read. If anything goes wrong, nothing is lost: point DATABASE_URL back at the source."""

import argparse
import base64
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

from db import SCHEMA, Database, init_db, is_postgres

# Rebuilt by the app itself on the new database, so not copied.
SKIP = {"schema_state"}


def tables():
    return [t for t in re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", SCHEMA) if t not in SKIP]


def storage_from_env():
    url, key = os.environ.get("SUPABASE_URL", "").rstrip("/"), os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not (url and key):
        return None
    return dict(url=url, key=key, bucket=os.environ.get("CAE_STORAGE_BUCKET") or "attachments")


def fetch_object(storage, path):
    """One file's bytes from a private Supabase Storage bucket."""
    req = urllib.request.Request(f"{storage['url']}/storage/v1/object/{storage['bucket']}/{urllib.parse.quote(path)}",
                                 headers={"Authorization": f"Bearer {storage['key']}", "apikey": storage["key"]})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def count(db, table):
    if not db.columns(table):
        return None  # the table doesn't exist there
    return int(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def counts(db):
    return {t: count(db, t) for t in tables()}


def insert_many(db, table, cols, rows):
    if not rows:
        return
    marks = ", ".join(["%s" if db.postgres else "?"] * len(cols))
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({marks})"
    cur = db.conn.cursor()
    cur.executemany(sql, rows)


def move(source_url, target_url, storage=None, fetch=fetch_object, log=print, today=None):
    """Copy everything from source to target. Returns {table: rows copied}. Raises SystemExit if it isn't safe."""
    if not target_url:
        raise SystemExit("Set TARGET_DATABASE_URL to the new database's address.")
    if source_url == target_url:
        raise SystemExit("The source and target are the same database.")
    init_db(target_url, today or date.today())  # the app's own tables, columns and indexes
    src, dst = Database(source_url), Database(target_url)
    try:
        if dst.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0]:
            raise SystemExit("The target database already has data in it. Use a new, empty database.")
        replica = False
        if dst.postgres:
            # Copy in any order: foreign keys were already kept by the source. Needs a superuser, which Coolify's
            # database user is; otherwise tables are copied in the order they're defined, parents first.
            try:
                dst.execute("SET session_replication_role = replica")
                dst.commit()
                replica = True
            except Exception:
                dst.rollback()
                log("  (copying in table order: the target user can't switch off foreign-key checks)")
        else:
            dst.execute("PRAGMA foreign_keys = OFF")
        copied = {}
        for table in tables():
            if not src.columns(table):
                copied[table] = 0
                continue
            cols = sorted(src.columns(table) & dst.columns(table))
            rows = [list(r) for r in src.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()]
            if table == "attachments" and rows:
                rows = bring_files_home(rows, cols, storage, fetch, log)
            insert_many(dst, table, cols, rows)
            copied[table] = len(rows)
            if rows:
                log(f"  {table}: {len(rows)}")
        dst.commit()
        if dst.postgres:
            if replica:
                dst.execute("SET session_replication_role = origin")
            for table in tables():
                if "id" in dst.columns(table):
                    # New records carry on from the highest id copied, rather than starting again at 1.
                    dst.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                                f"COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)")
            dst.commit()
        return copied
    finally:
        src.close()
        dst.close()


def bring_files_home(rows, cols, storage, fetch, log):
    """Files kept in Supabase Storage are downloaded and stored in the row itself, which the app serves directly."""
    content, key = cols.index("content"), cols.index("storage_key")
    for row in rows:
        if row[content] is None and row[key]:
            if storage is None:
                raise SystemExit("Some files are in Supabase Storage. Set SUPABASE_URL and SUPABASE_SERVICE_KEY so they "
                                 "can be copied too.")
            try:
                row[content] = base64.b64encode(fetch(storage, row[key])).decode()
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                raise SystemExit(f"Couldn't download a stored file ({getattr(e, 'code', e)}). Nothing was switched over; "
                                 "try again.") from None
    moved = sum(1 for r in rows if r[key] and r[content] is not None)
    log(f"  files now kept in the database: {moved}")
    return rows


def check(source_url, target_url):
    """Row counts on both sides. True when every table matches."""
    src = Database(source_url)
    dst = Database(target_url) if target_url else None
    try:
        before, after = counts(src), (counts(dst) if dst else {})
        ok = True
        for table in tables():
            a, b = before.get(table), after.get(table)
            if a is None and b is None:
                continue
            same = (a or 0) == (b or 0)
            ok &= same
            print(f"{'  ok ' if same else 'DIFF '} {table:28} source {a if a is not None else '-':>6}   "
                  f"target {b if b is not None else '-':>6}")
        if dst and dst.columns("attachments"):
            left = dst.execute("SELECT COUNT(*) FROM attachments WHERE content IS NULL").fetchone()[0]
            print(f"  files still outside the target database: {left}")
            ok &= int(left) == 0
        return ok
    finally:
        src.close()
        if dst:
            dst.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true", help="only compare row counts; change nothing")
    args = parser.parse_args(argv)
    source = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL") or ""
    target = os.environ.get("TARGET_DATABASE_URL", "")
    if not is_postgres(source) and not os.path.exists(source):
        print("Set DATABASE_URL to the current database.", file=sys.stderr)
        return 1
    if args.check:
        return 0 if check(source, target) else 1
    print("Copying…")
    move(source, target, storage_from_env())
    print("Checking…")
    ok = check(source, target)
    print("Everything matches. Now point DATABASE_URL at the new database." if ok
          else "Something doesn't match. Keep using the current database and ask for help.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
