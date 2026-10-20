"""Legal pages: terms of service, privacy notice, data processing agreement, and cookies and storage.

These are drafts written to match what CAE CRM actually does. A solicitor should review them before they're relied on.
Until CAE_LEGAL_REVIEWED is set, each page says it's a draft. Company details come from settings (LEGAL_*), and any
that are missing show as a highlighted "to confirm" note rather than being made up."""

import os

from flask import abort, current_app, render_template
from markupsafe import Markup, escape

DOCS = {
    "terms": "Terms of service",
    "privacy": "Privacy notice",
    "dpa": "Data processing agreement",
    "cookies": "Cookies and storage",
    "accessibility": "Accessibility statement",
}
# Changes whenever the wording changes, so each workspace's record shows which version it agreed to.
VERSION = "2026-10-20.6 draft"
UPDATED = "20 October 2026"

# Company details used in the documents: setting name -> what it is.
DETAILS = {
    "LEGAL_COMPANY_NAME": "company name",
    "LEGAL_COMPANY_NUMBER": "Companies House number",
    "LEGAL_ADDRESS": "registered office address",
    "LEGAL_ICO_NUMBER": "ICO registration number",
    "LEGAL_EMAIL": "privacy and legal contact email",
    "LEGAL_LAW": "governing law (for example England and Wales, or Scotland)",
}


def detail(name):
    """A company detail for the documents, or a visible note that it still needs confirming."""
    value = current_app.config.get(name)
    if value:
        return escape(value)
    return Markup('<mark class="to-confirm">[to confirm: {}]</mark>').format(DETAILS[name])


def todo(text):
    """A point for the solicitor or the business to confirm, highlighted in the page."""
    return Markup('<mark class="to-confirm">[to confirm: {}]</mark>').format(text)


def register(app):
    app.config.setdefault("LEGAL_COMPANY_NAME", os.environ.get("LEGAL_COMPANY_NAME", "Collinalitics Ltd"))
    for name in DETAILS:
        app.config.setdefault(name, os.environ.get(name, ""))
    app.config.setdefault("LEGAL_REVIEWED", os.environ.get("CAE_LEGAL_REVIEWED") == "1")
    app.add_template_global(detail, "legal_detail")
    app.add_template_global(DOCS, "legal_docs")
    app.add_template_global(todo, "to_confirm")

    @app.get("/legal")
    def legal_index():
        return render_template("legal/index.html", doc=None, title="Legal", version=VERSION, updated=UPDATED,
                               reviewed=current_app.config["LEGAL_REVIEWED"])

    @app.get("/legal/<doc>")
    def legal(doc):
        if doc not in DOCS:
            abort(404)
        return render_template(f"legal/{doc}.html", doc=doc, title=DOCS[doc], version=VERSION, updated=UPDATED,
                               reviewed=current_app.config["LEGAL_REVIEWED"])
