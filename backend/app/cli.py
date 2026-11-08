"""Command line entry points.

    python -m app.cli sync          # pull new confirmation emails (use this from cron)
    python -m app.cli test-imap     # check your IMAP login works
    python -m app.cli seed-demo     # fill the database with fake data to try the UI
    python -m app.cli import-csv tracker.csv [--dry-run]   # seed from a spreadsheet
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


def cmd_recheck(args) -> int:
    from .sync import recheck_from_imap

    init_db()
    with SessionLocal() as s:
        try:
            r = recheck_from_imap(s, days=args.days, dry_run=args.dry_run)
        except Exception as e:
            print(f"Re-check failed: {e}", file=sys.stderr)
            return 1
    verb = "Would change" if args.dry_run else "Changed"
    print(f"Re-checked {r.candidates} skipped / review emails since {r.since} "
          f"({r.not_found} no longer in the mailbox).")
    print(f"{verb} {len(r.changes)}: {r.created} new applications, {r.duplicates} linked to existing ones, "
          f"{r.review} in the review queue.")
    for line in r.changes:
        print("  " + line)
    for err in r.errors:
        print("  error:", err, file=sys.stderr)
    if args.dry_run and r.changes:
        print("Nothing saved (--dry-run). Run again without --dry-run to apply.")
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


def cmd_import_csv(args) -> int:
    from .importer import import_rows, read_csv

    try:
        rows, warnings = read_csv(args.file)
    except (OSError, ValueError) as e:
        print(f"Could not read {args.file}: {e}", file=sys.stderr)
        return 1
    init_db()
    with SessionLocal() as s:
        summary = import_rows(s, rows, dry_run=args.dry_run)
    for row in summary.created:
        print(f"  {'would add' if args.dry_run else 'added'}  {row.applied_date}  {row.status:<10} "
              f"{row.company} | {row.role}")
    for row in summary.skipped_existing:
        print(f"  skipped    {row.applied_date}  {row.company} | {row.role}  (already in the tracker)")
    for w in warnings:
        print("  note:", w)
    verb = "Would add" if args.dry_run else "Added"
    print(f"{verb} {len(summary.created)} applications, skipped {len(summary.skipped_existing)} "
          f"already in the tracker." + (" Nothing was saved (--dry-run)." if args.dry_run else ""))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sync", help="pull new confirmation emails").set_defaults(fn=cmd_sync)
    sub.add_parser("test-imap", help="check IMAP credentials").set_defaults(fn=cmd_test_imap)
    rc = sub.add_parser("recheck", help="run the current rules over emails skipped by an older version")
    rc.add_argument("--days", type=int, default=90, help="how far back to look (default 90)")
    rc.add_argument("--dry-run", action="store_true", help="show what would change, save nothing")
    rc.set_defaults(fn=cmd_recheck)
    sub.add_parser("seed-demo", help="add fake data to try the UI").set_defaults(fn=cmd_seed_demo)
    imp = sub.add_parser("import-csv", help="add applications from a spreadsheet saved as CSV")
    imp.add_argument("file", help="path to the .csv file")
    imp.add_argument("--dry-run", action="store_true", help="show what would be added, save nothing")
    imp.set_defaults(fn=cmd_import_csv)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
