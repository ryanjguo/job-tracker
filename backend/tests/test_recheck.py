"""Re-checking emails an older parser skipped (#39)."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Application, EmailRecord
from app.sync import recheck

NOW = datetime.now(timezone.utc)

# A confirmation that the pre-#26 parser skipped as a "rejection"
BODY = ("Thanks for your interest in Acme! We received your application for Data Intern. "
        "If we decide not to move forward with your application, we will let you know.")


class Mailbox:
    def __init__(self, bodies):  # message_id -> body
        self.bodies = bodies

    def find_uid(self, message_id):
        return message_id if message_id in self.bodies else None

    def fetch_body(self, uid):
        return self.bodies[uid]


def stored(message_id, outcome, reason="rejection", days_ago=3, subject="Thank you for applying to Acme!"):
    return EmailRecord(
        message_id=message_id, sender="Acme <no-reply@greenhouse.io>", subject=subject,
        received_at=NOW - timedelta(days=days_ago), outcome=outcome, reason=reason,
    )


def test_recheck_creates_what_an_old_parser_skipped():
    with SessionLocal() as s:
        s.add(stored("<a@x>", "ignored"))
        s.commit()
        r = recheck(s, Mailbox({"<a@x>": BODY}))
        assert (r.created, len(r.changes)) == (1, 1)
        assert "ignored (rejection) -> created" in r.changes[0]
        app = s.scalars(select(Application)).one()
        assert (app.company, app.role) == ("Acme", "Data Intern")
        rec = s.scalars(select(EmailRecord)).one()
        assert (rec.outcome, rec.application_id) == ("created", app.id)


def test_dry_run_saves_nothing():
    with SessionLocal() as s:
        s.add(stored("<a@x>", "ignored"))
        s.commit()
        r = recheck(s, Mailbox({"<a@x>": BODY}), dry_run=True)
        assert r.created == 1
    with SessionLocal() as s:
        assert s.scalars(select(Application)).all() == []
        assert s.scalars(select(EmailRecord)).one().outcome == "ignored"


def test_dismissed_old_and_missing_emails_are_left_alone():
    with SessionLocal() as s:
        s.add_all([
            stored("<dismissed@x>", "dismissed"),
            stored("<old@x>", "ignored", days_ago=200),
            stored("<gone@x>", "ignored"),
        ])
        s.commit()
        r = recheck(s, Mailbox({"<dismissed@x>": BODY, "<old@x>": BODY}), days=90)
        assert (r.created, r.not_found, r.scanned) == (0, 1, 1)
        assert {e.outcome for e in s.scalars(select(EmailRecord))} == {"dismissed", "ignored"}


def test_real_rejections_stay_skipped_and_duplicates_link():
    with SessionLocal() as s:
        s.add_all([
            stored("<rej@x>", "ignored", subject="Your application to Acme"),
            stored("<a@x>", "ignored"),
            stored("<b@x>", "review", reason="confirmation, but company not found"),
        ])
        s.commit()
        r = recheck(s, Mailbox({
            "<rej@x>": "Unfortunately, we have decided to move forward with other candidates.",
            "<a@x>": BODY,
            "<b@x>": BODY,  # same application, second copy
        }))
        assert (r.created, r.duplicates, r.ignored) == (1, 1, 1)
        assert s.get(EmailRecord, 1).reason == "rejection"


class StubConn:
    """Answers UID SEARCH like an IMAP server; records what was asked."""

    def __init__(self, header_hit=None, gmail_hit=None):
        self.header_hit, self.gmail_hit, self.calls = header_hit, gmail_hit, []

    def uid(self, command, *args):
        self.calls.append((command, *args))
        hit = self.header_hit if "HEADER" in args else self.gmail_hit
        return "OK", [hit.encode() if hit else b""]


def imap(host, conn):
    from app.mail import ImapSource

    src = ImapSource(host, 993, "me@example.com", "pw")
    src.conn = conn
    return src


def test_find_uid_searches_the_message_id_header():
    conn = StubConn(header_hit="17 42")
    assert imap("imap.fastmail.com", conn).find_uid("<abc@mail.acme.com>") == "42"
    assert conn.calls == [("SEARCH", None, "HEADER", "Message-ID", '"<abc@mail.acme.com>"')]


def test_find_uid_falls_back_to_gmail_search():
    conn = StubConn(header_hit=None, gmail_hit="7")
    assert imap("imap.gmail.com", conn).find_uid("<abc@mail.acme.com>") == "7"
    assert conn.calls[-1] == ("SEARCH", None, "X-GM-RAW", '"rfc822msgid:abc@mail.acme.com"')


def test_find_uid_not_found_and_generated_ids():
    assert imap("imap.fastmail.com", StubConn()).find_uid("<abc@x>") is None
    conn = StubConn(header_hit="1")
    assert imap("imap.gmail.com", conn).find_uid("<generated-123>") is None
    assert conn.calls == []
