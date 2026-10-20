"""Approve workspaces from open sign-up. Run it in the app's container (in Coolify, the application's Terminal).

Until a workspace is approved, its AI features stay off and it can send CAE_UNAPPROVED_DAILY_EMAILS emails a day
(30 unless set). Workspaces that signed up with the invite code, and those from before open sign-up, are approved.

    python approve.py                  lists the workspaces waiting, newest first
    python approve.py all              lists every workspace
    python approve.py approve 12       approves workspace 12
    python approve.py unapprove 12     takes approval away again"""

import sys

from app import create_app
from db import get_db


def listing(db, waiting_only):
    where = "w.demo_until IS NULL" + (" AND w.approved=0" if waiting_only else "")
    found = db.execute(
        "SELECT w.id, w.name, w.created_at, w.approved, "
        "(SELECT MIN(u.email) FROM users u WHERE u.workspace_id=w.id AND u.role='admin') AS admin_email, "
        "(SELECT COUNT(*) FROM users u WHERE u.workspace_id=w.id) AS people "
        f"FROM workspaces w WHERE {where} ORDER BY w.id DESC").fetchall()
    if not found:
        print("No workspaces are waiting for approval." if waiting_only else "No workspaces yet.")
    for w in found:
        state = "approved" if w["approved"] else "WAITING"
        print(f"{w['id']:>5}  {state:9} {w['created_at']}  {w['name'][:40]:40}  {w['admin_email'] or '-'}  "
              f"({w['people']} {'person' if w['people'] == 1 else 'people'})")
    return 0


def set_approved(db, workspace_id, value):
    row = db.execute("SELECT name FROM workspaces WHERE id=? AND demo_until IS NULL", (workspace_id,)).fetchone()
    if not row:
        print(f"There's no workspace {workspace_id}.", file=sys.stderr)
        return 1
    db.execute("UPDATE workspaces SET approved=? WHERE id=?", (int(value), workspace_id))
    db.commit()
    print(f"{row['name']} is now {'approved: AI can be turned on and email is no longer capped' if value else 'unapproved'}.")
    return 0


def main(argv, app=None):
    with (app or create_app()).app_context():
        db = get_db()
        if not argv:
            return listing(db, waiting_only=True)
        if argv == ["all"]:
            return listing(db, waiting_only=False)
        if len(argv) == 2 and argv[0] in ("approve", "unapprove") and argv[1].isdigit():
            return set_approved(db, int(argv[1]), argv[0] == "approve")
        print(__doc__.split("\n\n", 2)[2], file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
