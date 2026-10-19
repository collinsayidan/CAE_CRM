"""What customers receive: the business's logo and payment details, invoice and quote PDFs, invoices by email, and
polite automatic reminders (3 days before the due date, then 3, 14 and 30 days after it, when switched on), in wording
each business can change."""

import base64
import io
import re
from datetime import date

from flask import Response, abort, current_app, flash, g, redirect, render_template, request, url_for

import mail
from core import get_or_404, log_event, now, one, rows, today, workspace, ws
from db import get_db
from ukfmt import money, uk_date

MAX_LOGO_BYTES = 2 * 1024 * 1024
REMINDER_DAYS = (3, 14, 30)  # days after the due date
REMINDER_STAGES = (-3, 3, 14, 30)  # -3 is three days before the due date
STAGE_NAMES = {-3: "3 days before the due date", 3: "3 days late", 14: "14 days late", 30: "30 days late"}
MERGE_FIELDS = ("first_name", "number", "amount_due", "due_date", "days_late", "business")
DEFAULT_REMINDERS = {
    -3: ("Invoice {number} from {business} is due soon",
         "Hi {first_name},\n\nJust a note that invoice {number} for {amount_due} is due on {due_date}. If you've "
         "already paid, thank you."),
    3: ("Reminder: invoice {number} from {business}",
        "Hi {first_name},\n\nA friendly reminder that invoice {number} for {amount_due} was due on {due_date}. If "
        "you've already paid, thank you, and please ignore this email."),
    14: ("Reminder: invoice {number} from {business}",
         "Hi {first_name},\n\nInvoice {number} for {amount_due} was due on {due_date} and is now {days_late} days "
         "overdue. Please let us know when we can expect payment, or if there's a problem we can help with."),
    30: ("Overdue: invoice {number} from {business}",
         "Hi {first_name},\n\nInvoice {number} for {amount_due} was due on {due_date} and is now {days_late} days "
         "overdue. Please arrange payment as soon as possible, or let us know if there's a problem.\n\nWe may add "
         "interest and compensation under the Late Payment of Commercial Debts (Interest) Act 1998."),
}


# --- The business's logo -------------------------------------------------------------

def process_logo(upload):
    """An uploaded logo as a PNG (base64) no bigger than 600x200, keeping transparency. Raises ValueError."""
    from PIL import Image, ImageOps, UnidentifiedImageError
    data = upload.read(MAX_LOGO_BYTES + 1)
    if len(data) > MAX_LOGO_BYTES:
        raise ValueError("That logo is over 2 MB. Choose a smaller file.")
    try:
        img = Image.open(io.BytesIO(data))
        if img.width * img.height > 40_000_000:
            raise ValueError("That image is too large.")
        img = ImageOps.exif_transpose(img).convert("RGBA")
        img.thumbnail((600, 200), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        img.save(out, "PNG", optimize=True)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError("That file isn't an image we can read. Use a PNG, JPG or WebP.") from None
    return base64.b64encode(out.getvalue()).decode()


def logo_url(business, external=False):
    """Where the business's logo is served, or None. Public, so it shows in emails and on customers' pages."""
    if not business or not business["logo_updated"]:
        return None
    return url_for("workspace_logo", workspace_id=business["id"], v=business["logo_updated"], _external=external)


# --- PDFs ----------------------------------------------------------------------------

def latin(text):
    """PDF core fonts cover Latin-1, which has £; swap typographic punctuation for plain equivalents."""
    text = str(text or "")
    for a, b in (("‘", "'"), ("’", "'"), ("“", '"'), ("”", '"'), ("–", "-"), ("—", "-"), ("…", "..."), ("•", "-"),
                 (" ", " ")):
        text = text.replace(a, b)
    return text.encode("latin-1", "replace").decode("latin-1")


def gbp(pence):
    return latin(money(pence, pennies=True))


def render_pdf(kind, number, facts, business, company, lines, totals, notes, signature=None):
    """A one-business document: logo and details, who it's for, the lines, totals and closing notes."""
    from fpdf import FPDF
    navy, teal, grey, line_grey = (15, 31, 61), (15, 118, 110), (91, 107, 128), (226, 232, 240)
    pdf = FPDF(format="A4", unit="mm")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(18, 18, 18)
    pdf.add_page()
    pdf.set_title(latin(f"{kind} {number}"))
    pdf.set_author(latin(business["legal_name"] or business["name"]))

    top = pdf.get_y()
    if business["logo"]:
        try:
            pdf.image(io.BytesIO(base64.b64decode(business["logo"])), x=18, y=top, h=16)
            pdf.set_y(top + 19)
        except Exception:  # a logo the PDF library can't use mustn't stop the invoice
            pdf.set_y(top)
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*navy)
    pdf.cell(110, 7, latin(business["legal_name"] or business["name"]), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*grey)
    for part in [business["address"], " ".join(p for p in [business["city"], business["postcode"]] if p),
                 f"Company number {business['company_no']}" if business["company_no"] else None,
                 f"VAT number {business['vat_no']}" if business["vat_registered"] and business["vat_no"] else None]:
        if part:
            pdf.cell(110, 4.6, latin(part), new_x="LMARGIN", new_y="NEXT")
    after_business = pdf.get_y()

    pdf.set_xy(130, top)
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(*navy)
    pdf.cell(62, 9, latin(kind.upper()), align="R", new_x="LEFT", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    for label, value in facts:
        pdf.set_x(118)
        pdf.set_text_color(*grey)
        pdf.cell(36, 5, latin(label), align="R")
        pdf.set_text_color(*navy)
        pdf.cell(38, 5, latin(value), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(max(after_business, pdf.get_y()) + 8)

    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*grey)
    pdf.cell(0, 5, "BILL TO" if kind == "Invoice" else "PREPARED FOR", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*navy)
    pdf.cell(0, 6, latin(company["name"]), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*grey)
    for part in [company["address"], company["city"], company["postcode"],
                 f"VAT number {company['vat_no']}" if company["vat_no"] else None]:
        if part:
            pdf.cell(0, 4.6, latin(part), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    widths = (82, 16, 28, 18, 30)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(*grey)
    pdf.set_draw_color(*line_grey)
    for w, head, align in zip(widths, ("Description", "Qty", "Unit price", "VAT", "Net"), "LRRRR"):
        pdf.cell(w, 7, head, border="B", align=align)
    pdf.ln()
    pdf.set_text_color(*navy)
    for li in lines:
        desc = latin(li["description"]) + (f"  ({li['discount_pct']}% discount)" if li["discount_pct"] else "")
        pdf.set_font("Helvetica", "", 9.5)
        y = pdf.get_y()
        pdf.multi_cell(widths[0], 6, desc, border=0, align="L", new_x="RIGHT", new_y="TOP")
        height = max(pdf.get_y(), y + 6) - y
        pdf.set_xy(18 + widths[0], y)
        for w, value in zip(widths[1:], (str(li["quantity"]), gbp(li["unit_price"]), f"{li['vat_rate']}%", gbp(li["net"]))):
            pdf.cell(w, 6, value, align="R")
        pdf.set_y(y + max(height, 6.5))
        pdf.line(18, pdf.get_y(), 192, pdf.get_y())
    pdf.ln(2)
    for label, value, bold in totals:
        pdf.set_font("Helvetica", "B" if bold else "", 11 if bold else 9.5)
        pdf.set_x(18 + widths[0])
        pdf.cell(sum(widths[1:4]), 7 if bold else 6, latin(label), align="R")
        pdf.cell(widths[4], 7 if bold else 6, latin(value), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    for heading, body in notes:
        if heading:
            pdf.set_font("Helvetica", "B", 9.5)
            pdf.set_text_color(*teal)
            pdf.cell(0, 6, latin(heading), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*grey)
        pdf.multi_cell(0, 4.8, latin(body), align="L", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
    if signature:
        pdf.ln(2)
        pdf.set_font("Helvetica", "I", 16)
        pdf.set_text_color(*navy)
        pdf.cell(0, 9, latin(signature[0]), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(*grey)
        pdf.multi_cell(0, 4.5, latin(signature[1]), align="L", new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def vat_totals(net, vat, lines, business):
    by_rate = {}
    for li in lines:
        n, v = by_rate.get(li["vat_rate"], (0, 0))
        by_rate[li["vat_rate"]] = (n + li["net"], v + li["vat"])
    totals = [("Subtotal excluding VAT", gbp(net), False)]
    if business["vat_registered"] or vat:
        totals += [(f"VAT at {rate}% on {gbp(n)}", gbp(v), False) for rate, (n, v) in sorted(by_rate.items(), reverse=True)]
    return totals


def online_link(i, business):
    """Where a customer can pay this invoice online: its payment page once Stripe is connected, otherwise the
    business's own payment link, if it has one."""
    from payments import card_ready
    if i is not None and i["pay_token"] and card_ready(business):
        return url_for("pay_invoice", token=i["pay_token"], _external=True)
    return business["payment_link"] or None


def payment_notes(business, number, due, i=None):
    notes = []
    if business["bank_account_number"]:
        notes.append(("How to pay", f"By bank transfer to {business['bank_account_name'] or business['legal_name'] or business['name']}, "
                                    f"sort code {business['bank_sort_code']}, account {business['bank_account_number']}. "
                                    f"Please use {number} as the reference."))
    link = online_link(i, business)
    if link:
        notes.append(("Pay online" if not notes else None, f"Or pay online: {link}"))
    notes.append((None, f"Payment is due by {uk_date(due)}. Late payments may attract interest under the Late Payment of "
                        "Commercial Debts (Interest) Act 1998."))
    if not business["vat_registered"]:
        notes.append((None, f"{business['legal_name'] or business['name']} is not registered for VAT, so no VAT is charged."))
    return notes


def invoice_lines(i):
    found = rows("SELECT * FROM invoice_lines WHERE workspace_id=? AND invoice_id=? ORDER BY id", i["workspace_id"], i["id"])
    if found:
        return found
    return [dict(description=i["description"], quantity=1, unit_price=i["net"], discount_pct=0, vat_rate=i["vat_rate"],
                 net=i["net"], vat=i["vat"])]


def invoice_pdf(i, business):
    company = one("SELECT * FROM companies WHERE id=?", i["company_id"])
    lines = invoice_lines(i)
    facts = [("Invoice number", i["number"]), ("Tax point" if business["vat_registered"] else "Date", uk_date(i["issue_date"])),
             ("Payment due", uk_date(i["due_date"]))]
    from payments import balance, late_charges
    totals = vat_totals(i["net"], i["vat"], lines, business)
    if late_charges(i) or i["credited"] or i["amount_paid"]:
        totals.append(("Total including VAT", gbp(i["net"] + i["vat"]), False))
        if late_charges(i):
            totals.append(("Late payment interest and compensation (no VAT)", gbp(late_charges(i)), False))
        if i["credited"]:
            totals.append(("Less credit notes", "-" + gbp(i["credited"]), False))
        if i["amount_paid"]:
            totals.append(("Less paid", "-" + gbp(i["amount_paid"]), False))
    totals.append(("Amount due in GBP", gbp(max(balance(i), 0)), True))
    if i["paid_date"]:
        totals.append(("Paid in full", uk_date(i["paid_date"]), False))
    return render_pdf("Invoice", i["number"], facts, business, company, lines, totals,
                      payment_notes(business, i["number"], i["due_date"], i))


def quote_pdf(q, business):
    company = one("SELECT * FROM companies WHERE id=?", q["company_id"])
    lines = rows("SELECT * FROM quote_lines WHERE quote_id=? ORDER BY id", q["id"])
    facts = [("Quote number", q["number"]), ("Date", uk_date(q["issue_date"])), ("Valid until", uk_date(q["expiry_date"]))]
    totals = vat_totals(q["net"], q["vat"], lines, business) + [("Total in GBP", gbp(q["net"] + q["vat"]), True)]
    notes = [("Terms", q["terms"])] if q["terms"] else []
    signature = None
    if q["status"] == "Accepted" and q["signer_name"]:
        who = q["signer_name"] + (f", {q['signer_position']}" if q["signer_position"] else "")
        signature = (q["signer_name"], f"Accepted online by {who} on {q['decided_at'][:16].replace('T', ' at ')}.")
    return render_pdf("Quote", q["number"], facts, business, company, lines, totals, notes, signature)


def pdf_response(data, filename, download):
    return Response(data, mimetype="application/pdf", headers={
        "Content-Disposition": f'{"attachment" if download else "inline"}; filename="{filename}"'})


# --- Sending invoices and reminders -----------------------------------------------------

def reminder_template(workspace_id, stage):
    """(subject, body) for a reminder stage: the business's own wording, or ours."""
    row = one("SELECT subject, body FROM reminder_templates WHERE workspace_id=? AND stage=?", workspace_id, stage)
    return (row["subject"], row["body"]) if row else DEFAULT_REMINDERS[stage]


def merge(text, values):
    """Fill in {first_name} and the other merge fields. Plain replacement, so stray braces are left alone."""
    for key in MERGE_FIELDS:
        text = text.replace("{" + key + "}", str(values[key]))
    return text


def stage_for(days_late):
    """The reminder wording that fits how late an invoice is."""
    if days_late <= 0:
        return -3
    return 30 if days_late >= 30 else 14 if days_late >= 14 else 3


def invoice_email(i, business, recipient_name, kind="invoice", days_late=0, stage=None):
    """(subject, html, text) for an invoice or a reminder about it."""
    from payments import balance
    first = (recipient_name or "").split()[0] if recipient_name else "there"
    if kind == "invoice":
        subject = f"Invoice {i['number']} from {business['name']}"
        paragraphs = [f"Hi {first},", f"Please find attached invoice {i['number']} for "
                      f"{money(max(balance(i), 0), pennies=True)}, due by {uk_date(i['due_date'])}."]
    else:
        values = dict(first_name=first, number=i["number"], amount_due=money(max(balance(i), 0), pennies=True),
                      due_date=uk_date(i["due_date"]), days_late=max(days_late, 0), business=business["name"])
        subject_t, body_t = reminder_template(business["id"], stage if stage is not None else stage_for(days_late))
        subject = merge(subject_t, values).replace("\n", " ")[:200]
        paragraphs = [p.strip() for p in merge(body_t, values).replace("\r\n", "\n").split("\n\n") if p.strip()]
    if business["bank_account_number"]:
        paragraphs.append(f"Bank transfer: sort code {business['bank_sort_code']}, account {business['bank_account_number']}, "
                          f"reference {i['number']}.")
    paragraphs.append("The invoice is attached as a PDF.")
    link = online_link(i, business)
    html = render_template("emails/notice.html", business=business, heading=subject, paragraphs=paragraphs,
                           button_url=link, button_label="Pay online",
                           footer=f"{business['legal_name'] or business['name']}. Reply to this email with any questions.",
                           logo=logo_url(business, external=True))
    text = "\n\n".join(paragraphs) + (f"\n\nPay online: {link}" if link else "") + "\n"
    return subject, html, text


def send_invoice(i, business, to_email, to_name, kind="invoice", days_late=0, sender_name=None, stage=None):
    """Email an invoice or a reminder, PDF attached. Raises mail.MailError."""
    from payments import pay_token
    if not i["pay_token"]:
        pay_token(i)
        i = one("SELECT * FROM invoices WHERE id=?", i["id"])
    subject, html, text = invoice_email(i, business, to_name, kind, days_late, stage)
    mail.send(mail.message(to_email, subject, html, text, business["name"], business["reply_to"],
                           attachments=[(f"{i['number']}.pdf", invoice_pdf(i, business))]))


def reminder_stage(i, on, before=False):
    """Which reminder an unpaid invoice has reached (-3 for the one before it's due, if switched on, then 3, 14 or
    30 days late), or None, with how many days late it is."""
    late = (on - date.fromisoformat(i["due_date"])).days
    reached = [d for d in REMINDER_DAYS if late >= d]
    if reached:
        return reached[-1], late
    return (-3 if before and -3 <= late < 0 else None), late


def send_due_reminders():
    """Run by the daily job: one reminder per overdue invoice per run, for workspaces that switched them on."""
    from flask import g as flask_g
    if not mail.configured():
        return 0
    sent = 0
    db = get_db()
    candidates = rows("SELECT i.* FROM invoices i JOIN workspaces w ON w.id=i.workspace_id WHERE w.reminders_on=1 "
                      "AND i.paid_date IS NULL AND i.sent_to IS NOT NULL ORDER BY i.id LIMIT 200")
    for i in candidates:
        flask_g.public_workspace = i["workspace_id"]
        flask_g.pop("workspace", None)
        business = workspace()
        stage, late = reminder_stage(i, today(), before=bool(business["remind_before"]))
        if not stage or one("SELECT 1 FROM invoice_reminders WHERE invoice_id=? AND stage>=?", i["id"], stage):
            continue
        try:
            send_invoice(i, business, i["sent_to"], None, "reminder", late, stage=stage)
        except mail.MailError:
            current_app.logger.warning("Reminder for invoice %s not sent", i["id"])
            continue
        db.insert("invoice_reminders", workspace_id=i["workspace_id"], invoice_id=i["id"], stage=stage, sent_to=i["sent_to"],
                  sent_at=now().isoformat(timespec="minutes"))
        log_event(f"Reminder sent for invoice {i['number']}",
                  (f"{late} days overdue." if late > 0 else f"Due on {uk_date(i['due_date'])}.") + f" Sent to {i['sent_to']}.",
                  company_id=i["company_id"], deal_id=i["deal_id"])
        db.commit()
        sent += 1
    flask_g.pop("public_workspace", None)
    flask_g.pop("workspace", None)
    return sent


def register(app):
    app.add_template_global(logo_url, "logo_url")

    @app.get("/logo/<int:workspace_id>")
    def workspace_logo(workspace_id):
        row = one("SELECT logo FROM workspaces WHERE id=? AND logo IS NOT NULL", workspace_id)
        if row is None:
            abort(404)
        resp = Response(base64.b64decode(row["logo"]), mimetype="image/png")
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"  # the URL changes when the logo does
        return resp

    @app.get("/invoices/<int:invoice_id>/pdf")
    def invoice_pdf_view(invoice_id):
        i = get_or_404("invoices", invoice_id)
        return pdf_response(invoice_pdf(i, workspace()), f"{i['number']}.pdf", request.args.get("download") == "1")

    @app.get("/quotes/<int:quote_id>/pdf")
    def quote_pdf_view(quote_id):
        q = get_or_404("quotes", quote_id)
        return pdf_response(quote_pdf(q, workspace()), f"{q['number']}.pdf", request.args.get("download") == "1")

    @app.get("/q/<token>/pdf")
    def public_quote_pdf(token):
        from quotes import public_quote_or_404
        q = public_quote_or_404(token)
        return pdf_response(quote_pdf(q, workspace()), f"{q['number']}.pdf", True)

    @app.post("/invoices/<int:invoice_id>/email")
    def email_invoice(invoice_id):
        i = get_or_404("invoices", invoice_id)
        back_to = redirect(url_for("invoice", invoice_id=invoice_id))
        contact = None
        if request.form.get("contact_id", "").isdigit():
            contact = one("SELECT * FROM contacts WHERE id=? AND workspace_id=? AND company_id=?",
                          int(request.form["contact_id"]), ws(), i["company_id"])
        to_email = (contact["email"] if contact else request.form.get("email", "")).strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", to_email or ""):
            flash("Invoice not sent. Choose a contact with an email address, or type one in.", "error")
            return back_to
        business = workspace()
        try:
            send_invoice(i, business, to_email, f"{contact['first_name']} {contact['last_name']}" if contact else None)
        except mail.MailError as e:
            flash(f"Invoice not sent. {e}", "error")
            return back_to
        db = get_db()
        db.execute("UPDATE invoices SET sent_at=?, sent_to=? WHERE id=? AND workspace_id=?",
                   (now().isoformat(timespec="minutes"), to_email, invoice_id, ws()))
        log_event(f"Invoice {i['number']} emailed", f"Sent to {to_email} by {g.user['name']}, PDF attached.", kind="email",
                  author=g.user["name"], company_id=i["company_id"], deal_id=i["deal_id"],
                  contact_id=contact["id"] if contact else None)
        db.commit()
        flash(f"Invoice {i['number']} emailed to {to_email}.", "ok")
        return back_to

    @app.post("/invoices/<int:invoice_id>/remind")
    def remind_invoice(invoice_id):
        i = get_or_404("invoices", invoice_id)
        back_to = redirect(url_for("invoice", invoice_id=invoice_id))
        if i["paid_date"] or not i["sent_to"]:
            flash("Only an unpaid invoice that's been emailed can be chased.", "error")
            return back_to
        _, late = reminder_stage(i, today())
        try:
            send_invoice(i, workspace(), i["sent_to"], None, "reminder", max(late, 0))
        except mail.MailError as e:
            flash(f"Reminder not sent. {e}", "error")
            return back_to
        db = get_db()
        db.insert("invoice_reminders", workspace_id=ws(), invoice_id=invoice_id, stage=0, sent_to=i["sent_to"],
                  sent_at=now().isoformat(timespec="minutes"))
        log_event(f"Reminder sent for invoice {i['number']}", f"Sent to {i['sent_to']} by {g.user['name']}.", kind="email",
                  author=g.user["name"], company_id=i["company_id"], deal_id=i["deal_id"])
        db.commit()
        flash(f"Reminder sent to {i['sent_to']}.", "ok")
        return back_to
