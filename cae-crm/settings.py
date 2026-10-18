"""Workspace settings: the business's own details, which appear on its invoices, and its sales target."""

import re

from flask import flash, g, redirect, render_template, request, url_for

import auth
import ukfmt
from core import workspace, ws
from db import get_db


HUB = [
    ("settings", "cog", "Business details", "Your company details, VAT, invoice numbering and sales target.", True),
    ("auth.team", "users", "Team", "Who's on CAE CRM, their profiles, roles and access.", False),
    ("assistant_settings", "sparkle", "AI assistant", "Let your team ask questions about your CRM data and get drafts.", True),
    ("integrations", "bolt", "Integrations", "Connect your email, Xero and HMRC.", False),
    ("imports", "upload", "Import", "Bring in contacts and companies from a spreadsheet.", True),
    ("custom_fields_page", "edit", "Custom fields", "Add your own fields to contacts, companies, deals and tickets.", True),
    ("workflows", "bolt", "Workflows", "Create tasks, assign owners and notify people automatically.", True),
    ("developers", "columns", "API and webhooks", "Connect other systems, Zapier or Power BI to your CRM data.", True),
    ("billing", "pound", "Billing", "Your plan, number of users and payments.", True),
    ("vat", "shield", "VAT returns", "Submit Making Tax Digital VAT returns to HMRC.", True),
    ("audit_trail", "list", "Audit trail", "Who changed what, and when. Download it for your records.", True),
    ("legal_index", "shield", "Legal and privacy", "Terms of service, privacy notice, data processing agreement and cookies.", False),
]


def register(app):

    @app.route("/workspace")
    def workspace_settings():
        """One place for everything about running the workspace."""
        from billing import state
        admin = g.user["role"] == "admin"
        import assistant
        cards = [c for c in HUB if (admin or not c[4]) and (c[0] != "billing" or state(workspace())["enabled"])
                 and (c[0] != "assistant_settings" or assistant.configured())]
        return render_template("workspace.html", cards=cards)

    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        auth.admin_required()
        w = workspace()
        errors = {}
        form = request.form if request.method == "POST" else dict(w) | {
            "monthly_target": f"{w['monthly_target'] / 100:,.0f}", "vat_registered": "on" if w["vat_registered"] else "",
            "reminders_on": "on" if w["reminders_on"] else ""}
        if request.method == "POST":
            f = request.form
            data = {k: f.get(k, "").strip() for k in ("name", "legal_name", "address", "city")}
            if not data["name"]:
                errors["name"] = "Enter the name your team knows the business by."
            data["postcode"] = ""
            if f.get("postcode", "").strip():
                data["postcode"] = ukfmt.normalise_postcode(f["postcode"])
                if not data["postcode"]:
                    errors["postcode"] = "Enter a valid UK postcode, like EH2 2AN."
            data["company_no"] = ukfmt.normalise_company_no(f.get("company_no"))
            if data["company_no"] is None:
                errors["company_no"] = "Companies House numbers have 8 characters, like 08451236 or SC512345."
            data["vat_registered"] = 1 if f.get("vat_registered") == "on" else 0
            data["vat_no"] = ukfmt.normalise_vat(f.get("vat_no")) if data["vat_registered"] else ""
            if data["vat_no"] is None:
                errors["vat_no"] = "UK VAT numbers look like GB123456789."
            elif data["vat_registered"] and not data["vat_no"]:
                errors["vat_no"] = "VAT invoices must show your VAT number."
            target = ukfmt.parse_money(f.get("monthly_target"))
            if not target:
                errors["monthly_target"] = "Enter the amount you aim to win each month, like £150,000."
            data["monthly_target"] = target
            prefix = f.get("invoice_prefix", "").strip().upper()
            if not re.fullmatch(r"[A-Z0-9]{1,8}", prefix):
                errors["invoice_prefix"] = "Use 1 to 8 letters or numbers, like INV."
            data["invoice_prefix"] = prefix
            terms = f.get("payment_terms", "")
            if not terms.isdigit() or not 0 <= int(terms) <= 120:
                errors["payment_terms"] = "Enter a number of days between 0 and 120."
            data["payment_terms"] = int(terms) if terms.isdigit() else 30
            data["reply_to"] = f.get("reply_to", "").strip().lower()
            data["bank_account_name"] = f.get("bank_account_name", "").strip()[:80]
            sort_code = re.sub(r"\D", "", f.get("bank_sort_code", ""))
            account = re.sub(r"\D", "", f.get("bank_account_number", ""))
            if (sort_code or account) and not (len(sort_code) == 6 and len(account) == 8):
                errors["bank_sort_code"] = "Enter a 6-digit sort code and an 8-digit account number, or leave both empty."
            data["bank_sort_code"] = f"{sort_code[:2]}-{sort_code[2:4]}-{sort_code[4:]}" if sort_code else ""
            data["bank_account_number"] = account
            data["payment_link"] = f.get("payment_link", "").strip()[:300]
            if data["payment_link"] and not data["payment_link"].startswith("https://"):
                errors["payment_link"] = "Enter a full web address starting with https://"
            data["reminders_on"] = 1 if f.get("reminders_on") == "on" else 0
            logo = request.files.get("logo")
            if logo and logo.filename:
                from documents import process_logo
                try:
                    data["logo"] = process_logo(logo)
                except ValueError as e:
                    errors["logo"] = str(e)
            if data["reply_to"] and not auth.valid_email(data["reply_to"]):
                errors["reply_to"] = "Enter an email address, like hello@yourbusiness.co.uk."
            if not errors:
                db = get_db()
                db.execute("UPDATE workspaces SET name=?, legal_name=?, address=?, city=?, postcode=?, company_no=?,"
                           " vat_registered=?, vat_no=?, monthly_target=?, invoice_prefix=?, payment_terms=?, reply_to=?,"
                           " bank_account_name=?, bank_sort_code=?, bank_account_number=?, payment_link=?, reminders_on=?"
                           " WHERE id=?",
                           (data["name"], data["legal_name"], data["address"], data["city"], data["postcode"],
                            data["company_no"], data["vat_registered"], data["vat_no"], data["monthly_target"],
                            data["invoice_prefix"], data["payment_terms"], data["reply_to"] or None,
                            data["bank_account_name"] or None, data["bank_sort_code"] or None,
                            data["bank_account_number"] or None, data["payment_link"] or None, data["reminders_on"], ws()))
                if data.get("logo"):
                    from core import now
                    db.execute("UPDATE workspaces SET logo=?, logo_updated=? WHERE id=?",
                               (data["logo"], now().strftime("%Y%m%d%H%M%S"), ws()))
                elif f.get("remove_logo") == "on":
                    db.execute("UPDATE workspaces SET logo=NULL, logo_updated=NULL WHERE id=?", (ws(),))
                db.commit()
                flash("Settings saved.", "ok")
                return redirect(url_for("settings"))
        return render_template("settings.html", errors=errors, form=form), (422 if errors else 200)
