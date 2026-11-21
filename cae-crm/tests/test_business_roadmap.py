import base64
from datetime import datetime
from urllib.parse import urlsplit
import re
import pytest
from flask import g
from conftest import ADMIN, MEMBER, first_id, query, login
from db import get_db


def execute(app, sql, *args):
    with app.app_context():
        db = get_db()
        db.execute(sql, args)
        db.commit()


def insert(app, table, **values):
    with app.app_context():
        db = get_db()
        rid = db.insert(table, **values)
        db.commit()
        return rid


def post(c, path, **data):
    return c.post(path, data={"csrf": c.csrf, **data})


def test_pipeline_gates_isolation_and_overview(app, client, rival):
    r = post(
        client,
        "/settings/pipelines",
        name="Consulting",
        stages="Discovery | 25\nReview | 75 | contact_id,value",
    )
    assert r.status_code == 302
    pid = int(r.location.split("pipeline_id=")[1])
    co = first_id(app, "companies", app.ws)
    r = post(
        client,
        "/deals",
        pipeline_id=str(pid),
        title="Custom process deal",
        company_id=co,
        close_date="2026-12-01",
        value="100",
        stage="Discovery",
        owner=ADMIN[0],
        source="Referral",
    )
    assert r.status_code == 302
    did = int(r.location.rsplit("/", 1)[1])
    assert tuple(query(app, "SELECT pipeline_id,probability FROM deals WHERE id=?", did)[0]) == (pid, 25)
    assert b"Custom process deal" in client.get(f"/pipeline?pipeline_id={pid}").data
    assert b"Custom process deal" not in client.get("/pipeline").data
    assert post(client, f"/deals/{did}/stage", stage="Review").status_code == 422
    assert post(client, f"/deals/{did}/stage", stage="Qualified").status_code == 422
    assert rival.get(f"/pipeline?pipeline_id={pid}").status_code == 404
    assert client.get("/").status_code == 200


def test_visibility_search_details_finance_and_files(app, client):
    uid = query(app, "SELECT id FROM users WHERE email=?", MEMBER[1])[0][0]
    assert post(client, "/settings/access", user_id=uid, role="sales", record_scope="own").status_code == 302
    own = first_id(app, "contacts", app.ws)
    other = first_id(app, "contacts", app.ws, "id<>?", own)
    execute(app, "UPDATE contacts SET owner=? WHERE id=?", MEMBER[0], own)
    execute(app, "UPDATE contacts SET owner=?,first_name='HiddenRoadmapPerson' WHERE id=?", ADMIN[0], other)
    c = login(app, MEMBER[1], MEMBER[2])
    assert c.get(f"/contacts/{own}").status_code == 200
    assert c.get(f"/contacts/{other}").status_code == 404
    for path in ("/contacts", "/api/search?q=HiddenRoadmapPerson"):
        assert b"HiddenRoadmapPerson" not in c.get(path).data
    invoice = first_id(app, "invoices", app.ws)
    assert c.get(f"/invoices/{invoice}").status_code == 404
    fid = insert(
        app,
        "attachments",
        workspace_id=app.ws,
        record_type="contact",
        record_id=other,
        filename="private.txt",
        content_type="text/plain",
        size=6,
        content=base64.b64encode(b"secret").decode(),
        uploaded_by=ADMIN[0],
        created_at="2026-10-16T10:00",
    )
    assert c.get(f"/files/{fid}").status_code == 404
    assert c.get("/").status_code == 200


def test_department_scope_and_admin_access(app, client):
    uid = query(app, "SELECT id FROM users WHERE email=?", MEMBER[1])[0][0]
    execute(app, "UPDATE users SET department='Sales' WHERE id=?", uid)
    execute(app, "UPDATE users SET department='Management' WHERE email=?", ADMIN[1])
    post(client, "/settings/access", user_id=uid, role="manager", record_scope="team")
    co = first_id(app, "companies", app.ws)
    execute(app, "UPDATE companies SET owner=? WHERE id=?", ADMIN[0], co)
    c = login(app, MEMBER[1], MEMBER[2])
    assert c.get(f"/companies/{co}").status_code == 404
    assert c.get("/settings/access").status_code == 403


def test_new_screens_and_role_guards(client, member_client):
    for path in (
        "/settings/pipelines",
        "/settings/access",
        "/mailbox",
        "/calendar",
        "/automation",
        "/sequences",
        "/reports/builder",
        "/forecast",
        "/settings/portal",
        "/getting-started",
        "/settings/reliability",
    ):
        r = client.get(path)
        assert r.status_code == 200, (path, r.data[:500])
    for path in (
        "/settings/access",
        "/automation",
        "/sequences",
        "/settings/portal",
        "/getting-started",
        "/settings/reliability",
    ):
        assert member_client.get(path).status_code == 403


def test_workflow_delay_and_idempotent_worker(app, client):
    assert (
        post(
            client,
            "/automation",
            name="Assign task",
            on_event="contact.created",
            action_0="task",
            delay_0="1",
            person_0="owner",
            subject_0="Roadmap follow-up",
            condition_0="owner",
            equals_0=ADMIN[0],
        ).status_code
        == 302
    )
    assert (
        post(
            client,
            "/contacts",
            first_name="Queue",
            last_name="Test",
            email="queue@example.co.uk",
            lawful_basis="Legitimate interests",
            owner=ADMIN[0],
        ).status_code
        == 302
    )
    assert len(query(app, "SELECT id FROM automation_jobs WHERE workspace_id=?", app.ws)) == 1
    from automation import run_due

    with app.test_request_context("/"):
        g.user = None
        assert run_due() == 0
    app.config["NOW"] = datetime(2026, 10, 16, 12, 1)
    with app.test_request_context("/"):
        g.user = None
        assert run_due() == 1
        assert run_due() == 0
    assert (
        query(
            app,
            "SELECT COUNT(*) FROM activities WHERE subject LIKE 'Roadmap follow-up%' AND workspace_id=?",
            app.ws,
        )[0][0]
        == 1
    )


def test_sequence_tasks_and_enrollment_duplicates(app, client):
    cid = first_id(
        app,
        "contacts",
        app.ws,
        "marketing_consent=1 AND unsubscribed_at IS NULL AND email_bounced_at IS NULL",
    )
    assert (
        post(
            client, "/sequences", name="Follow up", kind_0="task", days_0="0", subject_0="Sequence task"
        ).status_code
        == 302
    )
    pid = query(app, "SELECT id FROM sequence_plans WHERE workspace_id=?", app.ws)[0][0]
    assert post(client, "/sequences/enroll", plan_id=pid, contact_id=cid).status_code == 302
    assert post(client, "/sequences/enroll", plan_id=pid, contact_id=cid).status_code == 409
    from sequences import run_due

    with app.test_request_context("/"):
        g.user = None
        assert run_due() == 1
        assert run_due() == 0
    assert query(app, "SELECT COUNT(*) FROM activities WHERE subject='Sequence task'")[0][0] == 1


def test_mailbox_send_needs_new_grant(app):
    import connected_mail as mailbox
    from integrations import IntegrationError

    uid = query(app, "SELECT id FROM users WHERE email=?", ADMIN[1])[0][0]
    conn = insert(
        app,
        "connections",
        workspace_id=app.ws,
        user_id=uid,
        provider="google",
        created_at="2026-10-16",
        granted_scopes="https://www.googleapis.com/auth/gmail.readonly",
    )
    cid = first_id(app, "contacts", app.ws)
    with app.test_request_context("/"):
        g.user = get_db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        c = get_db().execute("SELECT * FROM contacts WHERE id=?", (cid,)).fetchone()
        connection = get_db().execute("SELECT * FROM connections WHERE id=?", (conn,)).fetchone()
        app.config["MAIL_SEND_ENABLED"] = True
        with pytest.raises(IntegrationError):
            mailbox.send_connected(connection, c, "Hello", "A message")


def test_booking_csrf_and_double_booking(app, client, anon):
    assert post(client, "/calendar").status_code == 302
    token = query(app, "SELECT token FROM booking_pages WHERE workspace_id=?", app.ws)[0][0]
    page = anon.get(f"/book/{token}?date=2026-10-19")
    assert page.status_code == 200
    slot = re.search(rb'<option value="([^"]+)"', page.data).group(1).decode()
    data = dict(date="2026-10-19", starts_at=slot, name="Guest", email="guest@example.co.uk")
    assert anon.post(f"/book/{token}", data=data).status_code == 400
    assert post(anon, f"/book/{token}", **data).status_code == 200
    assert post(anon, f"/book/{token}", **data).status_code == 409
    assert query(app, "SELECT COUNT(*) FROM bookings WHERE workspace_id=?", app.ws)[0][0] == 1


def test_portal_proof_single_use_and_revocation(app, client, anon):
    app.config["MAIL_BACKEND"] = "memory"
    post(client, "/settings/portal")
    token = query(app, "SELECT token FROM portal_sites WHERE workspace_id=?", app.ws)[0][0]
    cid = first_id(app, "contacts", app.ws, "email IS NOT NULL")
    post(client, "/settings/portal", contact_id=cid, active="on")
    email = query(app, "SELECT email FROM contacts WHERE id=?", cid)[0][0]
    assert post(anon, f"/portal/{token}", email=email).status_code == 200
    link = re.search(r"https?://\S+", app.extensions["outbox"][-1]["text"]).group(0)
    path = urlsplit(link).path
    assert anon.get(path).status_code == 200
    assert anon.get(path).status_code == 200
    r = post(anon, path)
    assert r.status_code == 302
    assert anon.get(r.location).status_code == 200
    assert b"No invoices available for your access level" in anon.get(r.location).data
    assert post(anon, path).status_code == 410
    post(client, "/settings/portal", contact_id=cid)
    assert anon.get(r.location).status_code == 403


def test_reporting_forecast_and_target_tenant_boundary(app, client, rival):
    assert (
        post(
            client,
            "/reports/builder",
            object="deals",
            dimension="source",
            metric="weighted",
            start="2026-01-01",
            end="2026-12-31",
            name="Pipeline by source",
            weekly="on",
        ).status_code
        == 302
    )
    rid = query(app, "SELECT id FROM report_definitions WHERE workspace_id=?", app.ws)[0][0]
    assert rival.get(f"/reports/builder?report_id={rid}").status_code == 404
    did = first_id(app, "deals", app.ws, "stage NOT IN ('Won','Lost')")
    assert (
        post(
            client, "/forecast", deal_id=did, category="Commit", note="Reviewed with team", month="2026-10"
        ).status_code
        == 302
    )
    assert query(app, "SELECT forecast_category FROM deals WHERE id=?", did)[0][0] == "Commit"
    uid = query(app, "SELECT id FROM users WHERE email=?", ADMIN[1])[0][0]
    assert post(client, "/forecast/targets", user_id=uid, month="2026-10", amount="25000").status_code == 302
    assert query(app, "SELECT amount FROM sales_targets WHERE user_id=?", uid)[0][0] == 2500000


def test_required_fields_block_edit_before_any_changes(app, client):
    insert(
        app,
        "custom_fields",
        workspace_id=app.ws,
        object="deals",
        label="Purchase order",
        field_type="text",
        required=1,
        position=0,
        created_at="2026-10-16",
    )
    did = first_id(app, "deals", app.ws)
    r = post(
        client,
        f"/deals/{did}/edit",
        cf_present="1",
        title="Should not change",
        close_date="2026-11-01",
        value="10",
    )
    assert r.status_code == 422
    assert query(app, "SELECT title FROM deals WHERE id=?", did)[0][0] != "Should not change"


def test_worker_auth_and_readiness(app, client):
    assert client.get("/readyz").status_code == 200
    assert client.get("/cron/fast").status_code == 403
    app.config["CRON_SECRET"] = "worker-secret"
    r = app.test_client().get("/cron/fast", headers={"Authorization": "Bearer worker-secret"})
    assert r.status_code == 200, r.data
    assert query(app, "SELECT status FROM job_health WHERE name='fast'")[0][0] == "ok"


def test_restore_verifier_detects_missing_data(app, tmp_path):
    import sqlite3
    from db import Database, is_postgres

    if is_postgres(app.config["DATABASE"]):
        pytest.skip(
            "SQLite backup fixture; production restore verification uses a separately restored PostgreSQL database"
        )
    from verify_restore import verify

    backup = str(tmp_path / "restored.sqlite3")
    with sqlite3.connect(app.config["DATABASE"]) as source, sqlite3.connect(backup) as destination:
        source.backup(destination)
    source = Database(app.config["DATABASE"])
    restored = Database(backup)
    try:
        assert verify(source, restored)["verified"]
        restored.execute("DELETE FROM mail_usage")
        restored.insert("mail_usage", workspace_id=app.ws, day="2026-01-01", sent=1)
        restored.commit()
        assert not verify(source, restored)["verified"]
        with pytest.raises(ValueError):
            verify(source, source)
    finally:
        source.close()
        restored.close()


def test_calculated_fields_and_zero_required_value(app):
    from fields import calculate, problems

    defs = [
        dict(
            id=3,
            field_type="calculated",
            calculation='{"left":1,"right":2,"operation":"multiply"}',
            required=0,
            condition_field=None,
        )
    ]
    assert calculate(defs, {"1": 5, "2": 2})["3"] == 10
    required = [dict(id=1, label="Count", required=1, field_type="number", condition_field=None)]
    assert not problems(required, {"1": 0})


def test_mailbox_read_failure_is_displayed_without_send_state(app, client, monkeypatch):
    import connected_mail as mailbox
    from integrations import IntegrationError

    uid = query(app, "SELECT id FROM users WHERE email=?", ADMIN[1])[0][0]
    conn = insert(
        app, "connections", workspace_id=app.ws, user_id=uid, provider="google", created_at="2026-10-16"
    )
    cid = first_id(app, "contacts", app.ws)

    def fail(*args):
        raise IntegrationError("Reconnect your mailbox")

    monkeypatch.setattr(mailbox, "conversation", fail)
    r = client.get(f"/mailbox?connection_id={conn}&contact_id={cid}")
    assert r.status_code == 200 and b"Reconnect your mailbox" in r.data


def test_stage_rename_and_transfer_keep_record_identity(app, client):
    r = post(client, "/settings/pipelines", name="Renewals", stages="Review | 50\nAgreement | 80")
    pid = int(r.location.split("pipeline_id=")[1])
    did = first_id(app, "deals", app.ws, "stage NOT IN ('Won','Lost')")
    assert post(client, f"/deals/{did}/pipeline", pipeline_id=pid).status_code == 302
    sid = query(app, "SELECT id FROM pipeline_stages WHERE pipeline_id=? ORDER BY position", pid)[0][0]
    assert (
        post(client, f"/settings/pipelines/stages/{sid}", name="Account review", probability="55").status_code
        == 302
    )
    assert tuple(query(app, "SELECT stage,probability,pipeline_id FROM deals WHERE id=?", did)[0]) == (
        "Account review",
        55,
        pid,
    )
    assert client.get(f"/deals/{did}").status_code == 200


def test_pipeline_api_rejects_foreign_ids_and_entry_gate_bypass(app, client, rival):
    from test_api_automation import make_key, bearer

    key = make_key(client)
    r = post(client, "/settings/pipelines", name="Gated", stages="Review | 50 | contact_id,value")
    pid = int(r.location.split("pipeline_id=")[1])
    co = first_id(app, "companies", app.ws)
    data = dict(
        title="API deal", company_id=co, pipeline_id=pid, stage="Review", close_date="2026-11-30", value=100
    )
    assert client.post("/api/v1/deals", json=data, headers=bearer(key)).status_code == 422
    data["contact_id"] = first_id(app, "contacts", app.ws)
    assert client.post("/api/v1/deals", json=data, headers=bearer(key)).status_code == 201
    foreign = make_key(rival)
    assert rival.post("/api/v1/deals", json=data, headers=bearer(foreign)).status_code == 422


def test_scoped_update_parenthesises_or_and_protects_other_owner(app):
    uid = query(app, "SELECT id FROM users WHERE email=?", MEMBER[1])[0][0]
    execute(app, "UPDATE users SET record_scope='own' WHERE id=?", uid)
    cid = first_id(app, "contacts", app.ws)
    execute(app, "UPDATE contacts SET owner=? WHERE id=?", ADMIN[0], cid)
    with app.test_request_context("/"):
        db = get_db()
        g.user = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        db.execute("UPDATE contacts SET first_name='Do not change' WHERE id=? OR owner=?", (cid, MEMBER[0]))
        db.commit()
    assert query(app, "SELECT first_name FROM contacts WHERE id=?", cid)[0][0] != "Do not change"


def test_sequence_revoked_consent_stops_before_sending(app, client):
    cid = first_id(
        app,
        "contacts",
        app.ws,
        "marketing_consent=1 AND unsubscribed_at IS NULL AND email_bounced_at IS NULL",
    )
    post(
        client, "/sequences", name="Permission", kind_0="task", days_0="0", subject_0="Never create this task"
    )
    pid = query(app, "SELECT id FROM sequence_plans WHERE workspace_id=?", app.ws)[0][0]
    post(client, "/sequences/enroll", plan_id=pid, contact_id=cid)
    execute(app, "UPDATE contacts SET marketing_consent=0 WHERE id=?", cid)
    from sequences import run_due

    with app.test_request_context("/"):
        g.user = None
        assert run_due() == 0
    assert query(app, "SELECT status FROM sequence_enrollments WHERE plan_id=?", pid)[0][0] == "stopped"
    assert query(app, "SELECT COUNT(*) FROM activities WHERE subject='Never create this task'")[0][0] == 0


def test_worker_lease_prevents_overlapping_run(app):
    from operations import fast_jobs

    insert(app, "job_health", name="fast", status="running", started_at="2026-10-16T10:59:00")
    with app.test_request_context("/"):
        g.user = None
        assert fast_jobs() == {"status": "already_running"}


def test_full_mail_body_is_escaped_and_private_to_current_mailbox(app, client, monkeypatch):
    import connected_mail

    uid = query(app, "SELECT id FROM users WHERE email=?", ADMIN[1])[0][0]
    cid = first_id(app, "contacts", app.ws)
    conn = insert(
        app, "connections", workspace_id=app.ws, user_id=uid, provider="google", created_at="2026-10-16"
    )
    monkeypatch.setattr(
        connected_mail,
        "conversation",
        lambda *args: [
            dict(
                subject="Meeting",
                sender="Customer",
                when="Today",
                body="<script>alert(1)</script>",
                thread="thread",
            )
        ],
    )
    r = client.get(f"/mailbox?connection_id={conn}&contact_id={cid}")
    assert b"&lt;script&gt;alert(1)&lt;/script&gt;" in r.data
    other = login(app, MEMBER[1], MEMBER[2])
    assert other.get(f"/mailbox?connection_id={conn}&contact_id={cid}").status_code == 404


def test_mail_sync_keeps_high_water_until_all_pages_finish(app, monkeypatch):
    import mailsync
    from datetime import timezone

    uid = query(app, "SELECT id FROM users WHERE email=?", ADMIN[1])[0][0]
    conn = insert(
        app,
        "connections",
        workspace_id=app.ws,
        user_id=uid,
        provider="google",
        account=ADMIN[1],
        created_at="2026-10-16",
        sync_cursor="2026-10-01T00:00:00+00:00",
    )
    cid = first_id(app, "contacts", app.ws, "email IS NOT NULL")
    email = query(app, "SELECT email FROM contacts WHERE id=?", cid)[0][0]
    monkeypatch.setattr(mailsync, "access_token", lambda c: "token")

    def messages(token, since):
        page = g.get("mail_page")
        g.mail_next_page = None if page else "next-page"
        return [
            dict(
                id="older" if page else "newer",
                subject="Message",
                sender=email,
                recipients=ADMIN[1],
                when=datetime(2026, 10, 12 if page else 15, tzinfo=timezone.utc),
                preview="Body",
            )
        ]

    monkeypatch.setattr(mailsync, "gmail_messages", messages)
    with app.test_request_context("/"):
        g.user = None
        g.public_workspace = app.ws
        db = get_db()
        mailsync.sync(db.execute("SELECT * FROM connections WHERE id=?", (conn,)).fetchone())
        row = db.execute("SELECT * FROM connections WHERE id=?", (conn,)).fetchone()
        assert row["sync_cursor"] == "2026-10-01T00:00:00+00:00" and row["sync_page"] == "next-page"
        mailsync.sync(row)
        row = db.execute("SELECT * FROM connections WHERE id=?", (conn,)).fetchone()
        assert row["sync_page"] is None and row["sync_cursor"].startswith("2026-10-15")


def test_failed_automation_can_retry_without_partial_task(app, client, monkeypatch):
    import automation
    import workflows

    post(
        client,
        "/automation",
        name="Retry",
        on_event="contact.created",
        action_0="task",
        delay_0="0",
        person_0="owner",
        subject_0="Retry task",
    )
    post(
        client,
        "/contacts",
        first_name="Retry",
        last_name="Test",
        lawful_basis="Legitimate interests",
        owner=ADMIN[0],
    )
    original = workflows.act

    def fail(rule, ctx):
        original(rule, ctx)
        raise RuntimeError("Injected failure after task insert")

    monkeypatch.setattr(workflows, "act", fail)
    with app.test_request_context("/"):
        g.user = None
        automation.run_due()
    job = query(app, "SELECT id,status FROM automation_jobs WHERE workspace_id=?", app.ws)[0]
    assert job[1] == "failed"
    assert query(app, "SELECT COUNT(*) FROM activities WHERE subject LIKE 'Retry task:%'")[0][0] == 0
    monkeypatch.setattr(workflows, "act", original)
    assert post(client, f"/automation/jobs/{job[0]}/retry").status_code == 302
    with app.test_request_context("/"):
        g.user = None
        automation.run_due()
        automation.run_due()
    assert query(app, "SELECT COUNT(*) FROM activities WHERE subject LIKE 'Retry task:%'")[0][0] == 1


def test_scoped_staff_cannot_change_identity_or_department_to_gain_access(app, client):
    uid = query(app, "SELECT id FROM users WHERE email=?", MEMBER[1])[0][0]
    execute(app, "UPDATE users SET department='Sales' WHERE id=?", uid)
    post(client, "/settings/access", user_id=uid, role="sales", record_scope="team")
    c = login(app, MEMBER[1], MEMBER[2])
    assert post(c, "/account/profile", name=ADMIN[0], department="Management").status_code == 422
    assert tuple(query(app, "SELECT name,department FROM users WHERE id=?", uid)[0]) == (MEMBER[0], "Sales")


def test_deleted_user_cannot_leave_access_granted_to_reused_identity(app):
    cid = first_id(app, "contacts", app.ws)
    uid = query(app, "SELECT id FROM users WHERE email=?", MEMBER[1])[0][0]
    execute(app, "UPDATE contacts SET owner=? WHERE id=?", MEMBER[0], cid)
    assert query(app, "SELECT owner_id FROM contacts WHERE id=?", cid)[0][0] == uid
    execute(app, "DELETE FROM users WHERE id=?", uid)
    assert query(app, "SELECT owner_id FROM contacts WHERE id=?", cid)[0][0] is None


def test_equal_stage_names_keep_pipeline_specific_probabilities(app, client):
    r = post(client, "/settings/pipelines", name="Different probability", stages="Lead | 45\nClosing | 65")
    pid = int(r.location.split("pipeline_id=")[1])
    did = first_id(app, "deals", app.ws, "stage NOT IN ('Won','Lost')")
    assert post(client, f"/deals/{did}/pipeline", pipeline_id=pid).status_code == 302
    r = client.post(
        f"/deals/{did}/stage",
        data={"csrf": client.csrf, "stage": "Closing"},
        headers={"X-Requested-With": "fetch"},
    )
    assert r.status_code == 200 and r.get_json()["probability"] == 65
    assert query(app, "SELECT probability FROM deals WHERE id=?", did)[0][0] == 65
    assert client.get("/").status_code == 200
