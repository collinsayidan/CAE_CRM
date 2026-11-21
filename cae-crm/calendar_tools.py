"""Personal calendar view and collision-safe public booking pages. Times are UTC on disk."""

import secrets
from datetime import date, datetime, time, timedelta, timezone
from uuid import uuid4
from flask import abort, current_app, flash, g, redirect, render_template, request, url_for
from core import UK_TZ, log_event, now, one, rows, today, ws
from db import get_db
from integrations import IntegrationError, access_token, http
from connected_mail import allowed

UTC = timezone.utc


def iso(value):
    return value.astimezone(UTC).isoformat(timespec="seconds")


def parsed(value):
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return d.replace(tzinfo=UTC) if d.tzinfo is None else d


def clock():
    return now().replace(tzinfo=UK_TZ).astimezone(UTC)


def calendar_connection(workspace_id, user_id):
    cs = (
        get_db()
        .execute(
            "SELECT * FROM connections WHERE workspace_id=? AND user_id=? AND provider IN ('google','microsoft') ORDER BY id",
            (workspace_id, user_id),
        )
        .fetchall()
    )
    return (
        next((c for c in cs if allowed(c, "calendar")), None)
        if current_app.config.get("CALENDAR_ENABLED")
        else None
    )


def external_events(conn, start, end):
    headers = {"Authorization": f"Bearer {access_token(conn)}"}
    if conn["provider"] == "google":
        data = http(
            "GET",
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            headers=headers,
            params={
                "timeMin": iso(start),
                "timeMax": iso(end),
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": 250,
            },
        )
        if data.get("nextPageToken"):
            raise IntegrationError("Too many calendar events in this window. Choose a shorter date range.")
        return [
            dict(
                id=e["id"],
                subject=e.get("summary", "Busy"),
                start=e.get("start", {}).get("dateTime") or e.get("start", {}).get("date"),
                end=e.get("end", {}).get("dateTime") or e.get("end", {}).get("date"),
            )
            for e in data.get("items", [])
            if e.get("status") != "cancelled" and e.get("transparency") != "transparent"
        ]
    headers["Prefer"] = 'outlook.timezone="UTC"'
    data = http(
        "GET",
        "https://graph.microsoft.com/v1.0/me/calendarView",
        headers=headers,
        params={
            "startDateTime": iso(start),
            "endDateTime": iso(end),
            "$top": 250,
            "$select": "id,subject,start,end,isCancelled,showAs",
        },
    )
    if data.get("@odata.nextLink"):
        raise IntegrationError("Too many calendar events in this window. Choose a shorter date range.")
    return [
        dict(
            id=e["id"],
            subject=e.get("subject", "Busy"),
            start=e["start"]["dateTime"],
            end=e["end"]["dateTime"],
        )
        for e in data.get("value", [])
        if not e.get("isCancelled") and e.get("showAs") != "free"
    ]


def busy_for(workspace_id, user_id, start, end):
    found = [
        (parsed(r[0]), parsed(r[1]))
        for r in get_db().execute(
            "SELECT starts_at,ends_at FROM bookings WHERE workspace_id=? AND user_id=? AND starts_at<? AND ends_at>?",
            (workspace_id, user_id, iso(end), iso(start)),
        )
    ]
    conn = calendar_connection(workspace_id, user_id)
    if conn:
        for e in external_events(conn, start, end):
            # All-day Google dates follow the calendar's UK timezone.
            a = parsed(e["start"])
            b = parsed(e["end"])
            if len(e["start"]) == 10:
                a = datetime.combine(date.fromisoformat(e["start"]), time(), UK_TZ)
            if len(e["end"]) == 10:
                b = datetime.combine(date.fromisoformat(e["end"]), time(), UK_TZ)
            found.append((a, b))
    return found


def slots(page, day):
    if day < today() or day > today() + timedelta(days=30) or day.weekday() >= 5:
        return []
    start = datetime.combine(day, time(9), UK_TZ)
    end = datetime.combine(day, time(17), UK_TZ)
    busy = busy_for(page["workspace_id"], page["user_id"], start, end)
    return [
        start + timedelta(minutes=30 * i)
        for i in range(16)
        if start + timedelta(minutes=30 * i) > clock() + timedelta(hours=2)
        and not any(
            start + timedelta(minutes=30 * i) < b and start + timedelta(minutes=30 * (i + 1)) > a
            for a, b in busy
        )
    ]


def push_booking(conn, booking):
    headers = {"Authorization": f"Bearer {access_token(conn)}"}
    key = "cae" + format(booking["id"], "032x")
    start, end = booking["starts_at"], booking["ends_at"]
    if conn["provider"] == "google":
        # Google IDs use base32hex; the prefix and hex identifier both satisfy that alphabet.
        data = http(
            "POST",
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            headers=headers,
            params={"sendUpdates": "all"},
            json_body={
                "id": key,
                "summary": "Meeting with " + booking["name"],
                "start": {"dateTime": start},
                "end": {"dateTime": end},
                "attendees": [{"email": booking["email"]}],
            },
        )
    else:
        data = http(
            "POST",
            "https://graph.microsoft.com/v1.0/me/events",
            headers=headers,
            json_body={
                "transactionId": key,
                "subject": "Meeting with " + booking["name"],
                "start": {"dateTime": start, "timeZone": "UTC"},
                "end": {"dateTime": end, "timeZone": "UTC"},
                "attendees": [
                    {
                        "emailAddress": {"address": booking["email"], "name": booking["name"]},
                        "type": "required",
                    }
                ],
            },
        )
    return data.get("id")


def register(app):
    @app.route("/calendar", methods=["GET", "POST"])
    def calendar_page():
        if request.method == "POST":
            if g.get("demo"):
                abort(403)
            if not one("SELECT id FROM booking_pages WHERE user_id=? AND workspace_id=?", g.user["id"], ws()):
                get_db().insert(
                    "booking_pages",
                    workspace_id=ws(),
                    user_id=g.user["id"],
                    token=secrets.token_urlsafe(24),
                    title="Book a meeting",
                    active=1,
                )
                get_db().commit()
            return redirect(url_for("calendar_page"))
        events = []
        error = None
        conn = calendar_connection(ws(), g.user["id"])
        if conn:
            try:
                events = external_events(conn, clock(), clock() + timedelta(days=7))
            except IntegrationError as exc:
                error = str(exc)
        return render_template(
            "calendar_page.html",
            events=events,
            error=error,
            connected=bool(conn),
            booking_page=one(
                "SELECT * FROM booking_pages WHERE workspace_id=? AND user_id=?", ws(), g.user["id"]
            ),
            bookings=rows(
                "SELECT * FROM bookings WHERE workspace_id=? AND user_id=? ORDER BY starts_at DESC LIMIT 50",
                ws(),
                g.user["id"],
            ),
        )

    @app.route("/book/<token>", methods=["GET", "POST"])
    def public_booking(token):
        page = one("SELECT * FROM booking_pages WHERE token=? AND active=1", token)
        if not page:
            abort(404)
        g.public_workspace = page["workspace_id"]
        if one("SELECT demo_until FROM workspaces WHERE id=?", page["workspace_id"])[0]:
            abort(403)
        try:
            day = date.fromisoformat(request.values.get("date", today().isoformat()))
        except ValueError:
            abort(422)
        available = []
        error = None
        confirmed = False
        if request.method == "POST":
            import hashlib
            from quotes import client_ip

            key = "booking:" + hashlib.sha256(client_ip().encode()).hexdigest()
            if (
                one(
                    "SELECT COUNT(*) FROM portal_attempts WHERE workspace_id=? AND fingerprint=? AND created_at>?",
                    page["workspace_id"],
                    key,
                    (now() - timedelta(hours=1)).isoformat(timespec="seconds"),
                )[0]
                >= 5
            ):
                abort(429)
            get_db().insert(
                "portal_attempts",
                workspace_id=page["workspace_id"],
                fingerprint=key,
                created_at=now().isoformat(timespec="seconds"),
            )
            get_db().commit()
        try:
            available = slots(page, day)
        except IntegrationError:
            error = "We couldn't check availability. Please try again later."
        if request.method == "POST" and not error:
            # Browser CSRF plus a honeypot, a booking cap and a unique database slot reservation.
            name = request.form.get("name", "").strip()[:100]
            email = request.form.get("email", "").strip().lower()[:254]
            import auth

            if not name or not auth.valid_email(email) or request.form.get("website"):
                abort(422)
            if (
                one(
                    "SELECT COUNT(*) FROM bookings WHERE workspace_id=? AND email=? AND created_at>=?",
                    page["workspace_id"],
                    email,
                    (clock() - timedelta(days=1)).isoformat(),
                )[0]
                >= 3
            ):
                abort(429)
            chosen = next((s for s in available if iso(s) == request.form.get("starts_at")), None)
            if chosen is None:
                abort(409, "This slot is no longer available. Choose another time.")
            db = get_db()
            c = one(
                "SELECT * FROM contacts WHERE workspace_id=? AND lower(email)=?", page["workspace_id"], email
            )
            try:
                bid = db.insert(
                    "bookings",
                    workspace_id=page["workspace_id"],
                    user_id=page["user_id"],
                    contact_id=c["id"] if c else None,
                    starts_at=iso(chosen),
                    ends_at=iso(chosen + timedelta(minutes=30)),
                    name=name,
                    email=email,
                    created_at=clock().isoformat(),
                )
                db.commit()
            except Exception as exc:
                db.rollback()
                # A concurrent request may have reserved the same slot.
                if one(
                    "SELECT id FROM bookings WHERE user_id=? AND starts_at=?", page["user_id"], iso(chosen)
                ):
                    abort(409, "This slot has just been booked.")
                raise
            owner = one("SELECT name FROM users WHERE id=?", page["user_id"])[0]
            db.insert(
                "activities",
                workspace_id=page["workspace_id"],
                contact_id=c["id"] if c else None,
                company_id=c["company_id"] if c else None,
                kind="Meeting",
                subject="Meeting with " + name,
                owner=owner,
                due_at=chosen.replace(tzinfo=None).isoformat(timespec="minutes"),
                done=0,
            )
            if c:
                log_event(
                    "Meeting booked",
                    chosen.strftime("%d/%m/%Y %H:%M Europe/London"),
                    kind="meeting",
                    contact_id=c["id"],
                    company_id=c["company_id"],
                )
                from sequences import stop_for_contact

                stop_for_contact(c["id"], "Meeting booked")
            conn = calendar_connection(page["workspace_id"], page["user_id"])
            if conn:
                try:
                    external = push_booking(conn, one("SELECT * FROM bookings WHERE id=?", bid))
                    db.execute("UPDATE bookings SET external_id=? WHERE id=?", (external, bid))
                except IntegrationError:
                    db.execute(
                        "UPDATE bookings SET sync_error=? WHERE id=?",
                        ("Calendar delivery needs attention; meeting reserved in CRM.", bid),
                    )
            db.commit()
            confirmed = True
        return render_template(
            "public_booking.html",
            page=page,
            day=day,
            slots=available,
            error=error,
            confirmed=confirmed,
            iso=iso,
        ), (503 if error else 200)
