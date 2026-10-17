"""Making Tax Digital for VAT: read the business's VAT obligations from HMRC and submit a nine-box VAT return.

Sales figures come from CAE CRM's invoices, by tax point (the invoice date), as standard VAT accounting works.
CAE CRM doesn't hold purchases, so the VAT reclaimed (box 4) and purchases (box 7) are entered by hand from the
business's purchase records. HMRC requires fraud prevention headers on every call; the browser supplies its part.

HMRC_ENV=sandbox (the default) talks to HMRC's test service. Live returns need HMRC's production approval."""

import json
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_DOWN, Decimal
from urllib.parse import quote

from flask import abort, current_app, flash, g, redirect, render_template, request, url_for

import auth
from core import now, one, rows, today, workspace, ws
from db import get_db
from integrations import IntegrationError, access_token, connection, hmrc_base, http

DECLARATION = ("When you submit this VAT information you are making a legal declaration that the information is true "
               "and complete. A false declaration can result in prosecution.")
VERSION = "1.0"


def vrn():
    digits = re.sub(r"\D", "", workspace()["vat_no"] or "")
    return digits if len(digits) == 9 else None


def pounds(pence):
    return (Decimal(int(pence or 0)) / 100).quantize(Decimal("0.01"))


def whole(pence):
    return int((Decimal(int(pence or 0)) / 100).to_integral_value(ROUND_DOWN))


def sales_figures(start, end):
    """VAT on sales and sales excluding VAT, from invoices with a tax point in the period."""
    r = one("SELECT SUM(net) AS net, SUM(vat) AS vat FROM invoices WHERE workspace_id=? AND issue_date >= ? AND issue_date <= ?",
            ws(), start, end)
    count = one("SELECT COUNT(*) FROM invoices WHERE workspace_id=? AND issue_date >= ? AND issue_date <= ?", ws(), start, end)[0]
    return dict(vat=int(r["vat"] or 0), net=int(r["net"] or 0), count=count)


def fraud_headers(f):
    """HMRC's fraud prevention headers for the WEB_APP_VIA_SERVER connection method."""
    client_ip = (request.headers.get("X-Real-IP") or (request.access_route[0] if request.access_route else "")
                 or request.remote_addr or "")
    device = f.get("device_id") or request.cookies.get("cae_device") or str(uuid.uuid4())
    headers = {
        "Gov-Client-Connection-Method": "WEB_APP_VIA_SERVER",
        "Gov-Client-Browser-JS-User-Agent": f.get("js_user_agent") or request.headers.get("User-Agent", ""),
        "Gov-Client-Browser-Do-Not-Track": "true" if f.get("dnt") == "1" else "false",
        "Gov-Client-Device-ID": device,
        "Gov-Client-Public-IP": client_ip,
        "Gov-Client-Public-IP-Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "Gov-Client-Public-Port": request.headers.get("X-Forwarded-Port") or str(request.environ.get("REMOTE_PORT") or ""),
        "Gov-Client-Screens": f.get("screens", ""),
        "Gov-Client-Timezone": f.get("timezone", ""),
        "Gov-Client-Window-Size": f.get("window_size", ""),
        "Gov-Client-User-IDs": f"cae-crm={quote(str(g.user['id']))}",
        "Gov-Client-Multi-Factor": "",
        "Gov-Vendor-Version": f"cae-crm={VERSION}",
        "Gov-Vendor-Product-Name": quote("CAE CRM"),
        "Gov-Vendor-License-IDs": "",
    }
    vendor_ip = current_app.config.get("VENDOR_PUBLIC_IP")
    if vendor_ip:
        headers["Gov-Vendor-Public-IP"] = vendor_ip
        headers["Gov-Vendor-Forwarded"] = f"by={quote(vendor_ip)}&for={quote(client_ip)}"
    return {k: v for k, v in headers.items() if v != "" or k in ("Gov-Client-Multi-Factor", "Gov-Vendor-License-IDs")}


def call(method, path, conn, f=None, **kw):
    api, _ = hmrc_base()
    headers = {"Authorization": f"Bearer {access_token(conn)}", "Accept": "application/vnd.hmrc.1.0+json",
               **fraud_headers(f or {})}
    return http(method, api + path, headers=headers, **kw)


def register(app):

    @app.route("/vat")
    def vat():
        auth.admin_required()
        conn = connection("hmrc")
        obligations, error, number = [], None, vrn()
        if conn and number:
            try:
                # HMRC allows at most 366 days per request; the page passes the browser's details for the headers.
                data = call("GET", f"/organisations/vat/{number}/obligations", conn, request.args,
                            params={"from": (today() - timedelta(days=300)).isoformat(),
                                    "to": (today() + timedelta(days=60)).isoformat()})
                obligations = sorted(data.get("obligations") or [], key=lambda o: o["start"], reverse=True)
            except IntegrationError as e:
                error = str(e)
        submitted = {r["period_key"]: r for r in rows("SELECT * FROM vat_returns WHERE workspace_id=?", ws())}
        return render_template("vat.html", conn=conn, vrn=number, obligations=obligations, error=error,
                               submitted=submitted, sandbox=current_app.config.get("HMRC_ENV") != "production")

    @app.route("/vat/<period_key>", methods=["GET", "POST"])
    def vat_return(period_key):
        auth.admin_required()
        conn = connection("hmrc")
        number = vrn()
        start, end = request.values.get("start", ""), request.values.get("end", "")
        try:
            date.fromisoformat(start), date.fromisoformat(end)
        except ValueError:
            abort(404)
        if not conn or not number:
            return redirect(url_for("vat"))
        if one("SELECT 1 FROM vat_returns WHERE workspace_id=? AND period_key=?", ws(), period_key):
            flash("This period's return has already been submitted.", "error")
            return redirect(url_for("vat"))
        sales = sales_figures(start, end)
        f = request.form
        errors = {}
        boxes = dict(box1=pounds(sales["vat"]), box2=Decimal("0.00"), box4=Decimal("0.00"), box6=whole(sales["net"]),
                     box7=0, box8=0, box9=0)
        if request.method == "POST":
            try:
                for k in ("box1", "box2", "box4"):
                    boxes[k] = Decimal(f.get(k, "0") or "0").quantize(Decimal("0.01"))
                for k in ("box6", "box7", "box8", "box9"):
                    boxes[k] = int(Decimal(f.get(k, "0") or "0"))
            except ArithmeticError:
                errors["boxes"] = "Enter amounts as numbers, like 1234.56 (boxes 1 to 4) or 1234 (boxes 6 to 9)."
            if any(v < 0 for k, v in boxes.items() if k != "box1") and not errors:
                errors["boxes"] = "Only box 1 can be negative."
            if f.get("declaration") != "on":
                errors["declaration"] = "Tick the declaration to submit."
        boxes["box3"] = boxes["box1"] + boxes["box2"]
        boxes["box5"] = abs(boxes["box3"] - boxes["box4"])
        if request.method == "POST" and not errors:
            body = {"periodKey": period_key, "vatDueSales": float(boxes["box1"]), "vatDueAcquisitions": float(boxes["box2"]),
                    "totalVatDue": float(boxes["box3"]), "vatReclaimedCurrPeriod": float(boxes["box4"]),
                    "netVatDue": float(boxes["box5"]), "totalValueSalesExVAT": boxes["box6"],
                    "totalValuePurchasesExVAT": boxes["box7"], "totalValueGoodsSuppliedExVAT": boxes["box8"],
                    "totalAcquisitionsExVAT": boxes["box9"], "finalised": True}
            try:
                receipt = call("POST", f"/organisations/vat/{number}/returns", conn, f, json_body=body)
            except IntegrationError as e:
                flash(f"HMRC didn't accept the return. {e}", "error")
            else:
                db = get_db()
                db.insert("vat_returns", workspace_id=ws(), period_key=period_key, period_start=start, period_end=end,
                          boxes=json.dumps({k: str(v) for k, v in boxes.items()}), receipt=json.dumps(receipt),
                          submitted_by=g.user["name"], submitted_at=now().isoformat(timespec="minutes"))
                db.commit()
                flash(f"VAT return submitted to HMRC. Reference {receipt.get('formBundleNumber', 'received')}.", "ok")
                return redirect(url_for("vat"))
        return render_template("vat_return.html", period_key=period_key, start=start, end=end, boxes=boxes, sales=sales,
                               errors=errors, declaration=DECLARATION, vrn=number,
                               sandbox=current_app.config.get("HMRC_ENV") != "production"), (422 if errors else 200)
