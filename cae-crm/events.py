"""Things that happen to records, for workflow rules and webhooks to act on.

Pages and the API call emit() when something happens. Nothing runs straight away: once the request has finished
without an error, workflow rules run first, then webhooks are queued and sent. So a change that fails validation never
starts anything, and a rule or webhook that fails never undoes the change that set it off."""

from flask import current_app, g

from core import change_failed, error_flashes

# Event name -> (description, record type).
EVENTS = {
    "contact.created": ("A contact is added", "contact"),
    "contact.updated": ("A contact is edited", "contact"),
    "company.created": ("A company is added", "company"),
    "company.updated": ("A company is edited", "company"),
    "deal.created": ("A deal is added", "deal"),
    "deal.updated": ("A deal is edited", "deal"),
    "deal.stage_changed": ("A deal moves to another stage", "deal"),
    "deal.won": ("A deal is won", "deal"),
    "deal.lost": ("A deal is lost", "deal"),
    "ticket.created": ("A ticket is opened", "ticket"),
    "ticket.updated": ("A ticket is edited", "ticket"),
    "ticket.status_changed": ("A ticket's status changes", "ticket"),
    "quote.accepted": ("A quote is accepted", "quote"),
    "quote.declined": ("A quote is declined", "quote"),
    "invoice.created": ("An invoice is raised", "invoice"),
    "invoice.paid": ("An invoice is paid", "invoice"),
    "invoice.payment_received": ("A payment is recorded on an invoice", "invoice"),
    "credit_note.created": ("A credit note is raised against an invoice", "invoice"),
    "form.submitted": ("A web form is submitted", "contact"),
}


def emit(event, record_id, value=None, **extra):
    """Note that something happened. `value` is what rules can filter on (a deal's new stage, a ticket's priority,
    a form's id); `extra` goes into webhook payloads as it is."""
    assert event in EVENTS, event
    g.setdefault("pending_events", []).append(dict(event=event, record_id=record_id, value=value, extra=extra))


def register(app):

    @app.before_request
    def count_errors():
        g.errors_at_start = error_flashes()

    @app.after_request
    def run_events(response):
        pending = g.pop("pending_events", None)
        if not pending or response.status_code >= 400:
            return response
        if change_failed():
            return response  # the change didn't go through
        import webhooks
        import workflows
        for evt in pending:
            try:
                workflows.run(evt)
            except Exception:  # a broken rule must never break the page that set it off
                current_app.logger.exception("Workflow rules failed for %s", evt["event"])
        try:
            webhooks.queue(pending)
        except Exception:
            current_app.logger.exception("Webhooks not queued")
        return response
