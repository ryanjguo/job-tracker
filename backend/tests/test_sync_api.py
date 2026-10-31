from datetime import datetime, timezone

from app.db import SessionLocal
from app.mail import MailHeader
from app.sync import run_sync


class FakeMailbox:
    def __init__(self, items):
        self.items = items

    def fetch_headers(self, since):
        return [h for h, _ in self.items]

    def fetch_body(self, uid):
        return {h.uid: b for h, b in self.items}[uid]


NOW = datetime.now(timezone.utc)
ITEMS = [
    (MailHeader("1", "<a@x>", "Acme <no-reply@greenhouse.io>", "Thank you for applying to Acme!", NOW),
     "We received your application for Backend Engineer, thanks."),
    (MailHeader("2", "<b@x>", "Acme <no-reply@greenhouse.io>", "Thank you for applying to Acme!", NOW),
     "Second copy of the same confirmation."),
    (MailHeader("3", "<c@x>", "noreply@jobs-mailer.net", "Thank you for applying!", NOW),
     "We received your application."),
    (MailHeader("4", "<d@x>", "Mom <mom@gmail.com>", "Dinner Sunday?", NOW), "hi"),
]


def test_sync_creates_dedupes_and_queues():
    with SessionLocal() as s:
        summary = run_sync(s, FakeMailbox(ITEMS))
    assert (summary.created, summary.duplicates, summary.review) == (1, 1, 1)
    assert summary.candidates == 3  # the personal email never got its body downloaded


def test_resync_is_idempotent():
    with SessionLocal() as s:
        run_sync(s, FakeMailbox(ITEMS))
        again = run_sync(s, FakeMailbox(ITEMS))
    assert again.candidates == 0 and again.created == 0
