from flask import abort, flash, redirect, render_template, request, url_for
import auth
from core import rows, ws
from db import get_db
from permissions import ROLE_AREAS


def register(app):
    @app.route("/settings/access", methods=["GET", "POST"])
    def access_settings():
        auth.admin_required()
        if request.method == "POST":
            uid = request.form.get("user_id", "")
            role = request.form.get("role")
            scope = request.form.get("record_scope")
            if not uid.isdigit() or role not in auth.ROLES or scope not in ("own", "team", "workspace"):
                abort(422)
            from flask import g

            if int(uid) == g.user["id"]:
                abort(422, "Use another administrator to change your own access.")
            db = get_db()
            row = db.execute(
                "SELECT id FROM users WHERE id=? AND workspace_id=?", (int(uid), ws())
            ).fetchone()
            if not row:
                abort(404)
            db.execute(
                "UPDATE users SET role=?, record_scope=? WHERE id=? AND workspace_id=?",
                (role, scope, int(uid), ws()),
            )
            db.commit()
            flash("Access updated. It takes effect on the person's next request.", "ok")
            return redirect(url_for("access_settings"))
        return render_template(
            "access_settings.html",
            people=rows("SELECT * FROM users WHERE workspace_id=? ORDER BY name", ws()),
            roles=auth.ROLES,
            areas=ROLE_AREAS,
        )
