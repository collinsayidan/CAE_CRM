"""Help articles: short answers a business writes for its customers (opening hours, how to book, delivery and returns).
Admins write them under Settings, as drafts or published. Published articles have plain public pages, which the
website chatbot (chat.py) answers from and links to; together they're the start of a help centre.

Articles use the same simple formatting as email campaigns: blank lines for paragraphs, "- " for lists, **bold** and
[links](https://...)."""

import re
import secrets

from flask import abort, flash, g, redirect, render_template, request, url_for

import auth
from core import now, one, rows, ws
from db import get_db

MAX_TITLE = 120
MAX_BODY = 20_000


def site_token(w):
    """The workspace's public token for its help pages and chatbot, made the first time it's needed. No commit."""
    if w["site_token"]:
        return w["site_token"]
    token = secrets.token_hex(6)
    get_db().execute("UPDATE workspaces SET site_token=? WHERE id=?", (token, w["id"]))
    return token


def published(workspace_id):
    return rows("SELECT * FROM help_articles WHERE workspace_id=? AND published=1 ORDER BY LOWER(title)", workspace_id)


def workspace_by_token(token):
    w = one("SELECT * FROM workspaces WHERE site_token=?", token) if token and len(token) < 40 else None
    if w is None:
        abort(404)
    g.public_workspace = w["id"]
    return w


def render(body):
    """An article or chat reply as safe HTML. The campaign formatter adds inline styles for email, which the help pages
    and chat style themselves, and links open in a new tab so they don't take over the chat window."""
    from campaigns import body_html
    from markupsafe import Markup
    html = re.sub(r' style="[^"]*"', "", str(body_html(body)))  # user text is escaped, so these are all ours
    return Markup(html.replace("<a href=", '<a target="_blank" rel="noopener noreferrer" href='))


def register(app):
    app.add_template_filter(render, "article")

    @app.route("/settings/help-articles", methods=["GET", "POST"])
    def help_articles():
        auth.admin_required()
        db = get_db()
        if request.method == "POST":
            f = request.form
            article_id = f.get("article_id", "")
            existing = one("SELECT * FROM help_articles WHERE id=? AND workspace_id=?", int(article_id), ws()) \
                if article_id.isdigit() else None
            if article_id and existing is None:
                abort(404)
            if f.get("action") == "delete" and existing:
                db.execute("DELETE FROM help_articles WHERE id=?", (existing["id"],))
                db.commit()
                flash(f"Deleted {existing['title']}.", "ok")
                return redirect(url_for("help_articles"))
            title, body = f.get("title", "").strip()[:MAX_TITLE], f.get("body", "").strip()[:MAX_BODY]
            if not title or not body:
                flash("An article needs a title and some text.", "error")
                return redirect(url_for("help_articles", edit=article_id or None))
            live = 1 if f.get("published") == "on" else 0
            stamp = now().isoformat(timespec="minutes")
            if existing:
                db.execute("UPDATE help_articles SET title=?, body=?, published=?, updated_at=? WHERE id=?",
                           (title, body, live, stamp, existing["id"]))
            else:
                db.insert("help_articles", workspace_id=ws(), title=title, body=body, published=live,
                          created_by=g.user["name"], created_at=stamp, updated_at=stamp)
            from core import workspace
            site_token(workspace())
            db.commit()
            flash(f"Saved {title}{' and published it' if live else ' as a draft'}.", "ok")
            return redirect(url_for("help_articles"))
        editing = request.args.get("edit", "")
        edit = one("SELECT * FROM help_articles WHERE id=? AND workspace_id=?", int(editing), ws()) if editing.isdigit() else None
        from core import workspace
        w = workspace()
        return render_template("help_articles.html", articles=rows(
            "SELECT * FROM help_articles WHERE workspace_id=? ORDER BY published DESC, LOWER(title)", ws()),
            edit=edit, token=w["site_token"])

    @app.get("/help/<token>")
    def help_index(token):
        w = workspace_by_token(token)
        from documents import logo_url
        return render_template("public/help_index.html", business=w, logo=logo_url(w), articles=published(w["id"]),
                               token=token)

    @app.get("/help/<token>/<int:article_id>")
    def help_article(token, article_id):
        w = workspace_by_token(token)
        a = one("SELECT * FROM help_articles WHERE id=? AND workspace_id=? AND published=1", article_id, w["id"])
        if a is None:
            abort(404)
        from documents import logo_url
        return render_template("public/help_article.html", business=w, logo=logo_url(w), a=a, token=token,
                               chat_on=bool(w["chat_on"]))
