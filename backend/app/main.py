"""FastAPI app. Run with:  uvicorn app.main:app --reload  (from backend/)"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .config import settings
from .db import get_session, init_db
from .models import Application, EmailRecord, Status, StatusEvent, utcnow
from .schemas import ApplicationCreate, ApplicationOut, ApplicationUpdate
from .sync import create_application


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Job Tracker", lifespan=lifespan)


# --------------------------------------------------------------------------------------
# Serializers
# --------------------------------------------------------------------------------------
def email_url(message_id: str) -> str | None:
    """Gmail can open a message by its Message-ID. Other providers: no deep link."""
    if not message_id or not settings.is_gmail or message_id.startswith("<demo") \
            or message_id.startswith("<generated"):
        return None
    return "https://mail.google.com/mail/u/0/#search/" + quote(f"rfc822msgid:{message_id.strip('<>')}")


def to_out(a: Application) -> ApplicationOut:
    days = (date.today() - a.applied_date).days
    return ApplicationOut(
        id=a.id, company=a.company, role=a.role, status=a.status, applied_date=a.applied_date,
        job_url=a.job_url, notes=a.notes, source=a.source, ats=a.ats, created_at=a.created_at,
        status_changed_at=a.status_changed_at, days_since_applied=days,
        possibly_ghosted=a.status == Status.applied.value and days >= settings.ghost_after_days,
        email_url=email_url(a.email_message_id),
        events=[{"status": e.status, "at": e.at} for e in a.events],
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
    )
    session.commit()
    return to_out(get_app_or_404(session, a.id))


@app.patch("/api/applications/{app_id}", response_model=ApplicationOut)
def update_application(app_id: int, body: ApplicationUpdate, session: Session = Depends(get_session)):
    a = get_app_or_404(session, app_id)
    data = body.model_dump(exclude_unset=True)
    status = data.pop("status", None)
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
# Serve the built frontend (after `npm run build`), so one process runs everything
# --------------------------------------------------------------------------------------
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
