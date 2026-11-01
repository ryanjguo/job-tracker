"""Command line entry points.

    python -m app.cli sync          # pull new confirmation emails (use this from cron)
    python -m app.cli test-imap     # check your IMAP login works
    python -m app.cli seed-demo     # fill the database with fake data to try the UI
"""
import argparse
import random
import sys
from datetime import date, timedelta

from .config import settings
from .db import SessionLocal, init_db
from .models import EmailRecord, Status, StatusEvent, utcnow
from .sync import create_application, sync_from_imap


def cmd_sync(_args) -> int:
    init_db()
    with SessionLocal() as s:
        try:
            summary = sync_from_imap(s)
        except Exception as e:
            print(f"Sync failed: {e}", file=sys.stderr)
            return 1
    print(
        f"Scanned {summary.scanned} emails since {summary.since}: {summary.created} new, "
        f"{summary.duplicates} duplicates, {summary.review} need review, {summary.ignored} skipped."
    )
    for err in summary.errors:
        print("  error:", err, file=sys.stderr)
    return 0


def cmd_test_imap(_args) -> int:
    from .mail import ImapSource

    if not settings.imap_configured:
        print("Set IMAP_USER and IMAP_PASSWORD in backend/.env first.", file=sys.stderr)
        return 1
    try:
        with ImapSource(settings.imap_host, settings.imap_port, settings.imap_user,
                        settings.imap_password, settings.imap_folder) as src:
            n = len(src.fetch_headers(date.today() - timedelta(days=7)))
    except Exception as e:
        print(f"IMAP login failed: {e}", file=sys.stderr)
        return 1
    print(f"OK - connected to {settings.imap_host} as {settings.imap_user}; "
          f"{n} emails in {settings.imap_folder} from the last 7 days.")
    return 0


DEMO = [
    ("Acme Robotics", "Backend Engineer", "greenhouse"), ("Northwind", "Software Engineer, Platform", "lever"),
    ("Globex", "Data Analyst", "linkedin"), ("Initech", "Full Stack Developer", "ashby"),
    ("Umbrella Corp", "Junior QA Analyst", ""), ("Hooli", "Site Reliability Engineer", "workday"),
    ("Stark Industries", "Mobile Developer (iOS)", "workable"), ("Wayne Enterprises", "Customer Success Associate", "indeed"),
    ("Pied Piper", "Frontend Engineer", "greenhouse"), ("Cyberdyne", "ML Engineer Intern", "lever"),
    ("Soylent", "Product Analyst", "ashby"), ("Vandelay Industries", "Software Developer", "workday"),
    ("Massive Dynamic", "Cloud Engineer", "greenhouse"), ("Tyrell Corp", "Backend Developer", "lever"),
]
DEMO_STATUS = ["applied"] * 7 + ["oa", "oa", "interview", "rejected", "rejected", "ghosted", "offer"]


def cmd_seed_demo(_args) -> int:
    init_db()
    rng = random.Random(7)
    with SessionLocal() as s:
        for i, (co, role, ats) in enumerate(DEMO):
            days_ago = rng.randint(1, 50) if DEMO_STATUS[i] != "applied" else rng.choice([2, 5, 9, 16, 34, 41, 3])
            app = create_application(
                s, company=co, role=role, applied_date=date.today() - timedelta(days=days_ago),
                source="email", ats=ats, email_message_id=f"<demo-{i}@example.com>",
            )
            if DEMO_STATUS[i] != "applied":
                app.status = DEMO_STATUS[i]
                app.status_changed_at = utcnow()
                app.events.append(StatusEvent(status=DEMO_STATUS[i]))
        s.add(EmailRecord(
            message_id="<demo-review@example.com>", sender="noreply@jobs-mailer.net",
            subject="Thank you for applying!", received_at=utcnow(),
            snippet="We received your application for the Junior Developer position and will be in touch.",
            guessed_company="", guessed_role="Junior Developer", outcome="review",
            reason="confirmation, but company not found",
        ))
        s.add(EmailRecord(
            message_id="<demo-ignored@example.com>", sender="LinkedIn <jobalerts-noreply@linkedin.com>",
            subject="30+ new jobs for you", received_at=utcnow(),
            snippet="Top job picks for you.", outcome="ignored", reason="job alert / recommendations",
        ))
        s.commit()
    print(f"Added {len(DEMO)} demo applications (+1 review item).")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sync", help="pull new confirmation emails").set_defaults(fn=cmd_sync)
    sub.add_parser("test-imap", help="check IMAP credentials").set_defaults(fn=cmd_test_imap)
    sub.add_parser("seed-demo", help="add fake data to try the UI").set_defaults(fn=cmd_seed_demo)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
