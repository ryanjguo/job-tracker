"""FastAPI app. Run with:  uvicorn app.main:app --reload  (from backend/)"""
from __future__ import annotations

import statistics
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .config import settings
from .db import get_session, init_db
from .models import Application, EmailRecord, Status, StatusEvent, utcnow
from .schemas import (
    ApplicationCreate, ApplicationOut, ApplicationUpdate, EmailRecordOut, MetaOut, ReviewAccept,
    StatsOut, WeekCount,
)
from .exporter import applications_csv
from .scheduler import SyncScheduler
from .sync import SyncBusy, create_application, last_sync_at, last_sync_error, sync_from_imap

RESPONDED = {Status.oa.value, Status.interview.value, Status.offer.value, Status.rejected.value}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    scheduler = None
    if settings.sync_every_minutes > 0 and settings.imap_configured:
        scheduler = SyncScheduler(every_seconds=settings.sync_every_minutes * 60)
        scheduler.start()
    yield
    if scheduler:
        scheduler.stop()


app = FastAPI(title="Job Tracker", lifespan=lifespan)

# --------------------------------------------------------------------------------------
# Cross-site protection. There's no login, so make sure requests come from the dashboard:
#  - only answer to known host names (a DNS-rebinding page arrives with its own host name)
#  - writes need a custom header, which other websites can't add without a CORS preflight
#    that this API never approves (plain form posts / fetch no-cors can't set it)
# --------------------------------------------------------------------------------------
CSRF_HEADER = "X-Job-Tracker"
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))


@app.middleware("http")
async def require_dashboard_header(request: Request, call_next):
    if (request.method in WRITE_METHODS and request.url.path.startswith("/api/")
            and CSRF_HEADER.lower() not in request.headers):
        return JSONResponse(
            {"detail": f"Missing {CSRF_HEADER} header: writes are only accepted from the dashboard"},
            status_code=403,
        )
    return await call_next(request)


# --------------------------------------------------------------------------------------
# Serializers
# --------------------------------------------------------------------------------------
def email_url(message_id: str) -> str | None:
    """Gmail can open a message by its Message-ID. Other providers: no deep link."""
    if not message_id or not settings.is_gmail or message_id.startswith("<demo") \
            or message_id.startswith("<generated"):
        return None
    # authuser picks the right account however many Google accounts the browser is signed into
    # (/u/0 would open the first one, e.g. a work account).
    account = f"?authuser={quote(settings.imap_user, safe='@')}" if settings.imap_user else "u/0/"
    search = quote(f"rfc822msgid:{message_id.strip('<>')}")
    return f"https://mail.google.com/mail/{account}#search/{search}"


def to_out(a: Application) -> ApplicationOut:
    days = (date.today() - a.applied_date).days
    return ApplicationOut(
        id=a.id, company=a.company, role=a.role, status=a.status, applied_date=a.applied_date,
        job_url=a.job_url, notes=a.notes, location=a.location, term=a.term,
        next_action=a.next_action, follow_up_date=a.follow_up_date,
        source=a.source, ats=a.ats, created_at=a.created_at,
        status_changed_at=a.status_changed_at, days_since_applied=days,
        possibly_ghosted=a.status == Status.applied.value and days >= settings.ghost_after_days,
        email_url=email_url(a.email_message_id),
        events=[{"status": e.status, "at": e.at} for e in a.events],
    )


def record_out(r: EmailRecord) -> EmailRecordOut:
    return EmailRecordOut(
        id=r.id, sender=r.sender, subject=r.subject, received_at=r.received_at, snippet=r.snippet,
        guessed_company=r.guessed_company, guessed_role=r.guessed_role, ats=r.ats,
        outcome=r.outcome, reason=r.reason, application_id=r.application_id,
        email_url=email_url(r.message_id),
    )


def get_app_or_404(session: Session, app_id: int) -> Application:
    a = session.get(Application, app_id, options=[selectinload(Application.events)])
    if not a:
        raise HTTPException(404, "Application not found")
    return a


def set_status(a: Application, status: str) -> None:
    if a.status != status:
        a.status = status
        a.status_changed_at = utcnow()
        a.events.append(StatusEvent(status=status))


# --------------------------------------------------------------------------------------
# Applications
# --------------------------------------------------------------------------------------
@app.get("/api/applications", response_model=list[ApplicationOut])
def list_applications(session: Session = Depends(get_session)):
    rows = session.scalars(
        select(Application).options(selectinload(Application.events))
        .order_by(Application.applied_date.desc(), Application.id.desc())
    ).all()
    return [to_out(a) for a in rows]


@app.post("/api/applications", response_model=ApplicationOut, status_code=201)
def add_application(body: ApplicationCreate, session: Session = Depends(get_session)):
    a = create_application(
        session, company=body.company, role=body.role, applied_date=body.applied_date or date.today(),
        source="manual", job_url=body.job_url, notes=body.notes, status=body.status.value,
        location=body.location, term=body.term, next_action=body.next_action,
        follow_up_date=body.follow_up_date,
    )
    session.commit()
    return to_out(get_app_or_404(session, a.id))


@app.patch("/api/applications/{app_id}", response_model=ApplicationOut)
def update_application(app_id: int, body: ApplicationUpdate, session: Session = Depends(get_session)):
    a = get_app_or_404(session, app_id)
    data = body.model_dump(exclude_unset=True)
    status = data.pop("status", None)
    if "follow_up_date" in data:  # the one field that can be cleared with null
        a.follow_up_date = data.pop("follow_up_date")
    for k, v in data.items():
        if v is not None:
            setattr(a, k, v.strip() if isinstance(v, str) and k != "notes" else v)
    if status is not None:
        set_status(a, Status(status).value)
    session.commit()
    return to_out(get_app_or_404(session, app_id))


@app.delete("/api/applications/{app_id}", status_code=204)
def delete_application(app_id: int, session: Session = Depends(get_session)):
    a = get_app_or_404(session, app_id)
    for r in session.scalars(select(EmailRecord).where(EmailRecord.application_id == app_id)):
        r.application_id = None
        if r.outcome in ("created", "accepted", "duplicate"):
            r.outcome = "dismissed"  # so a re-sync doesn't recreate it
    session.delete(a)
    session.commit()


# --------------------------------------------------------------------------------------
# Review queue + skipped emails
# --------------------------------------------------------------------------------------
@app.get("/api/emails", response_model=list[EmailRecordOut])
def list_emails(outcome: str = "review", limit: int = 100, session: Session = Depends(get_session)):
    rows = session.scalars(
        select(EmailRecord).where(EmailRecord.outcome == outcome)
        .order_by(EmailRecord.received_at.desc().nulls_last(), EmailRecord.id.desc()).limit(limit)
    ).all()
    return [record_out(r) for r in rows]


@app.post("/api/emails/{record_id}/accept", response_model=ApplicationOut)
def accept_email(record_id: int, body: ReviewAccept, session: Session = Depends(get_session)):
    """Turn a review-queue (or skipped) email into an application."""
    r = session.get(EmailRecord, record_id)
    if not r:
        raise HTTPException(404, "Email not found")
    if r.application_id:
        raise HTTPException(409, "Already linked to an application")
    from .sync import local_date

    a = create_application(
        session, company=body.company, role=body.role, applied_date=local_date(r.received_at),
        source="review", ats=r.ats, job_url=body.job_url, email_message_id=r.message_id,
    )
    r.outcome, r.application_id = "accepted", a.id
    session.commit()
    return to_out(get_app_or_404(session, a.id))


@app.post("/api/emails/{record_id}/dismiss", status_code=204)
def dismiss_email(record_id: int, session: Session = Depends(get_session)):
    r = session.get(EmailRecord, record_id)
    if not r:
        raise HTTPException(404, "Email not found")
    r.outcome = "dismissed"
    session.commit()


# --------------------------------------------------------------------------------------
# Sync, stats, meta
# --------------------------------------------------------------------------------------
@app.post("/api/sync")
def sync_now(session: Session = Depends(get_session)):
    try:
        return sync_from_imap(session).as_dict()
    except SyncBusy as e:
        raise HTTPException(409, str(e))
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # login failures etc.
        raise HTTPException(502, f"Sync failed: {e}")


@app.get("/api/export.csv")
def export_csv(session: Session = Depends(get_session)):
    """Every application as CSV, in columns the importer reads back."""
    return Response(
        applications_csv(session), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="job-applications-{date.today()}.csv"'},
    )


@app.get("/api/stats", response_model=StatsOut)
def stats(session: Session = Depends(get_session)):
    apps = session.scalars(select(Application).options(selectinload(Application.events))).all()
    today = date.today()
    by_status = {s.value: 0 for s in Status}
    for a in apps:
        by_status[a.status] = by_status.get(a.status, 0) + 1

    counted = [a for a in apps if a.status != Status.withdrawn.value]
    responded = [a for a in counted if a.status in RESPONDED or any(e.status in RESPONDED for e in a.events)]

    response_days = []
    for a in responded:
        first = next((e for e in a.events if e.status in RESPONDED), None)
        if first:
            response_days.append(max(0, (first.at.date() - a.applied_date).days))

    monday = today - timedelta(days=today.weekday())
    weeks = [monday - timedelta(weeks=i) for i in range(11, -1, -1)]
    per_week = [
        WeekCount(week_start=w, count=sum(1 for a in apps if w <= a.applied_date < w + timedelta(days=7)))
        for w in weeks
    ]
    return StatsOut(
        total=len(apps),
        by_status=by_status,
        response_rate=round(len(responded) / len(counted), 3) if counted else 0.0,
        median_days_to_response=statistics.median(response_days) if response_days else None,
        applied_last_7_days=sum(1 for a in apps if (today - a.applied_date).days < 7),
        possibly_ghosted=sum(
            1 for a in apps
            if a.status == Status.applied.value and (today - a.applied_date).days >= settings.ghost_after_days
        ),
        per_week=per_week,
    )


@app.get("/api/meta", response_model=MetaOut)
def meta(session: Session = Depends(get_session)):
    review_count = session.scalar(
        select(func.count()).select_from(EmailRecord).where(EmailRecord.outcome == "review")
    )
    return MetaOut(
        imap_configured=settings.imap_configured, imap_user=settings.imap_user,
        imap_folder=settings.imap_folder, last_sync_at=last_sync_at(session),
        ghost_after_days=settings.ghost_after_days, statuses=[s.value for s in Status],
        review_count=review_count or 0,
        sync_every_minutes=settings.sync_every_minutes if settings.imap_configured else 0,
        last_sync_error=last_sync_error(session),
    )


# --------------------------------------------------------------------------------------
# Serve the built frontend (after `npm run build`), so one process runs everything
# --------------------------------------------------------------------------------------
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
