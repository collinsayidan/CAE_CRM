"""Read-only verification of a separately restored backup.

Set RESTORED_DATABASE_URL and run python verify_restore.py. Production DATABASE_URL
is only read. This command never creates, drops, restores or writes any database.
"""

import hashlib
import json
import os
import re
import sys
from db import Database, SCHEMA


def signature(db, table):
    digest = hashlib.sha256()
    count = 0
    for row in db.execute(f"SELECT * FROM {table} ORDER BY id"):
        digest.update(json.dumps(list(row), default=str, ensure_ascii=False, separators=(",", ":")).encode())
        digest.update(b"\n")
        count += 1
    return count, digest.hexdigest()


def verify(source, restored):
    if source.target == restored.target:
        raise ValueError("Choose a separate restored database.")
    if source.postgres and restored.postgres:
        query = "SELECT current_database(),inet_server_addr(),inet_server_port()"
        if tuple(source.execute(query).fetchone()) == tuple(restored.execute(query).fetchone()):
            raise ValueError("Source and restored connections refer to the same database.")
    result = {}
    mismatch = []
    for table in re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", SCHEMA):
        a = signature(source, table)
        b = signature(restored, table)
        result[table] = {"rows": a[0], "matches": a == b}
        if a != b:
            mismatch.append(table)
    if not restored.postgres:
        if restored.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            mismatch.append("integrity")
        if restored.execute("PRAGMA foreign_key_check").fetchone():
            mismatch.append("foreign_keys")
    return {"verified": not mismatch, "tables": result, "mismatched": mismatch}


def main():
    source_url = os.environ.get("DATABASE_URL") or os.environ.get("CAE_DATABASE")
    restored_url = os.environ.get("RESTORED_DATABASE_URL")
    if not source_url or not restored_url:
        print(
            "Set DATABASE_URL (or CAE_DATABASE) and RESTORED_DATABASE_URL to separate databases.",
            file=sys.stderr,
        )
        return 1
    for target in (source_url, restored_url):
        if not target.startswith(("postgres://", "postgresql://")) and not os.path.isfile(target):
            print("Both SQLite database files must already exist.", file=sys.stderr)
            return 1
    source = restored = None
    try:
        source = Database(source_url)
        restored = Database(restored_url)
        for reader in (source, restored):
            if reader.postgres:
                reader.conn.read_only = True
            else:
                reader.conn.execute("PRAGMA query_only=ON")
        result = verify(source, restored)
        print(json.dumps(result, indent=2))
        return 0 if result["verified"] else 1
    except Exception:
        # Don't echo a driver exception: it may contain credentials or infrastructure addresses.
        print(
            "Verification could not complete. Check that the restored database is separate and has the same schema.",
            file=sys.stderr,
        )
        return 1
    finally:
        if source:
            source.close()
        if restored:
            restored.close()


if __name__ == "__main__":
    sys.exit(main())
