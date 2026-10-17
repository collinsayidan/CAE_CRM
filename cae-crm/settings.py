"""Workspace settings: the business's own details, which appear on its invoices, and its sales target."""

import re

from flask import flash, redirect, render_template, request, url_for

import auth
import ukfmt
from core import workspace, ws
from db import get_db


def register(app):

    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        auth.admin_required()
        w = workspace()
        errors = {}
        form = request.form if request.method == "POST" else dict(w) | {
            "monthly_target": f"{w['monthly_target'] / 100:,.0f}", "vat_registered": "on" if w["vat_registered"] else ""}
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
            if not errors:
                db = get_db()
                db.execute("UPDATE workspaces SET name=?, legal_name=?, address=?, city=?, postcode=?, company_no=?,"
                           " vat_registered=?, vat_no=?, monthly_target=?, invoice_prefix=?, payment_terms=? WHERE id=?",
                           (data["name"], data["legal_name"], data["address"], data["city"], data["postcode"],
                            data["company_no"], data["vat_registered"], data["vat_no"], data["monthly_target"],
                            data["invoice_prefix"], data["payment_terms"], ws()))
                db.commit()
                flash("Settings saved.", "ok")
                return redirect(url_for("settings"))
        return render_template("settings.html", errors=errors, form=form), (422 if errors else 200)
