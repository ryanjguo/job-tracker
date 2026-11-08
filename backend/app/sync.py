"""The sync pipeline: mailbox -> prefilter -> classify -> dedupe -> database."""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, settings as default_settings
from .mail import ImapSource, MailHeader, MailSource
from .models import Application, EmailRecord, Meta, Status, StatusEvent, utcnow
from .parser import EmailInput, classify, is_prefilter_candidate, normalize_company, normalize_role

_lock = threading.Lock()
LAST_SYNC_KEY = "last_sync_at"
LAST_ERROR_KEY = "last_sync_error"


class SyncBusy(RuntimeError):
    """Another sync is running; not an error worth reporting."""


@dataclass
class SyncSummary:
    scanned: int = 0
    candidates: int = 0
    created: int = 0
    duplicates: int = 0
    review: int = 0
    ignored: int = 0
    errors: list[str] = field(default_factory=list)
    since: str = ""

    def as_dict(self):
        return asdict(self)


# --------------------------------------------------------------------------------------
# Meta helpers
# --------------------------------------------------------------------------------------
def get_meta(session: Session, key: str) -> str | None:
    row = session.get(Meta, key)
    return row.value if row else None


def set_meta(session: Session, key: str, value: str) -> None:
    row = session.get(Meta, key)
    if row:
        row.value = value
    else:
        session.add(Meta(key=key, value=value))


def last_sync_at(session: Session) -> datetime | None:
    v = get_meta(session, LAST_SYNC_KEY)
    return datetime.fromisoformat(v) if v else None


# --------------------------------------------------------------------------------------
# Application helpers (shared with the API)
# --------------------------------------------------------------------------------------
def local_date(dt: datetime | None) -> date:
    if dt is None:
        return date.today()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().date()


def create_application(session: Session, *, company: str, role: str = "", applied_date: date,
                       source: str, ats: str = "", job_url: str = "", notes: str = "",
                       email_message_id: str = "", status: str = Status.applied.value,
                       location: str = "", term: str = "", next_action: str = "",
                       follow_up_date: date | None = None) -> Application:
    app = Application(
        company=company.strip(), role=role.strip(), applied_date=applied_date, source=source,
        ats=ats, job_url=job_url.strip(), notes=notes, email_message_id=email_message_id,
        status=status, location=location.strip(), term=term.strip(),
        next_action=next_action.strip(), follow_up_date=follow_up_date,
    )
    app.events.append(StatusEvent(status=status))
    session.add(app)
    session.flush()
    return app


def find_duplicate(session: Session, company: str, role: str, on: date,
                   window_days: int) -> Application | None:
    """Same company (normalized) + same role (or one side has no role) within the window."""
    norm_co = normalize_company(company)
    norm_role = normalize_role(role)
    lo, hi = on - timedelta(days=window_days), on + timedelta(days=window_days)
    rows = session.scalars(
        select(Application).where(Application.applied_date >= lo, Application.applied_date <= hi)
    ).all()
    for app in rows:
        if normalize_company(app.company) != norm_co:
            continue
        other = normalize_role(app.role)
        if not norm_role or not other or other == norm_role:
            return app
    return None


# --------------------------------------------------------------------------------------
# The sync itself
# --------------------------------------------------------------------------------------
def process_email(session: Session, header: MailHeader, body: str, cfg: Settings,
                  summary: SyncSummary) -> None:
    result = classify(EmailInput(header.message_id, header.sender, header.subject, body))
    applied_on = local_date(header.received_at)
    record = EmailRecord(
        message_id=header.message_id, sender=header.sender[:500], subject=header.subject[:1000],
        received_at=header.received_at, snippet=" ".join(body.split())[:600],
        guessed_company=result.company, guessed_role=result.role, ats=result.ats,
        reason=result.reason, outcome="ignored",
    )

    if result.kind == "ignore":
        summary.ignored += 1
    else:
        dup = None
        if result.company:
            dup = find_duplicate(session, result.company, result.role, applied_on,
                                 cfg.duplicate_window_days)
        if dup:
            record.outcome, record.application_id = "duplicate", dup.id
            if result.role and not dup.role:
                dup.role = result.role  # fill in a missing role from the second email
            summary.duplicates += 1
        elif result.kind == "confirmation":
            app = create_application(
                session, company=result.company, role=result.role, applied_date=applied_on,
                source="email", ats=result.ats, email_message_id=header.message_id,
            )
            record.outcome, record.application_id = "created", app.id
            summary.created += 1
        else:
            record.outcome = "review"
            summary.review += 1
    session.add(record)


def run_sync(session: Session, source: MailSource, cfg: Settings = default_settings,
             now: datetime | None = None) -> SyncSummary:
    now = now or utcnow()
    summary = SyncSummary()
    last = last_sync_at(session)
    since = (last - timedelta(days=1)).date() if last else (now - timedelta(days=cfg.initial_lookback_days)).date()
    summary.since = since.isoformat()

    headers = source.fetch_headers(since)
    summary.scanned = len(headers)
    headers.sort(key=lambda h: h.received_at or now)  # oldest first: first email wins

    ids = [h.message_id for h in headers]
    known: set[str] = set()
    for i in range(0, len(ids), 500):
        known |= set(session.scalars(
            select(EmailRecord.message_id).where(EmailRecord.message_id.in_(ids[i : i + 500]))
        ))

    for h in headers:
        if h.message_id in known or not is_prefilter_candidate(h.sender, h.subject):
            continue
        known.add(h.message_id)
        summary.candidates += 1
        try:
            body = source.fetch_body(h.uid)
            process_email(session, h, body, cfg, summary)
            session.commit()  # commit per email so one failure doesn't undo the rest
        except Exception as e:  # one weird email shouldn't kill the run
            session.rollback()
            summary.errors.append(f"{h.subject[:80]!r}: {e}")

    set_meta(session, LAST_SYNC_KEY, now.isoformat())
    session.commit()
    return summary


def last_sync_error(session: Session) -> str | None:
    return get_meta(session, LAST_ERROR_KEY) or None


def _record_error(session: Session, message: str) -> None:
    session.rollback()
    set_meta(session, LAST_ERROR_KEY, message[:500])
    session.commit()


def sync_from_imap(session: Session, cfg: Settings = default_settings) -> SyncSummary:
    """One IMAP sync. Failures are remembered (see last_sync_error) and re-raised; a success
    clears the remembered error."""
    if not cfg.imap_configured:
        raise RuntimeError("IMAP is not configured. Set IMAP_USER and IMAP_PASSWORD in backend/.env")
    if not _lock.acquire(blocking=False):
        raise SyncBusy("A sync is already running")
    try:
        with ImapSource(cfg.imap_host, cfg.imap_port, cfg.imap_user, cfg.imap_password,
                        cfg.imap_folder) as src:
            summary = run_sync(session, src, cfg)
        set_meta(session, LAST_ERROR_KEY, "")
        session.commit()
        return summary
    except Exception as e:
        _record_error(session, str(e) or e.__class__.__name__)
        raise
    finally:
        _lock.release()
