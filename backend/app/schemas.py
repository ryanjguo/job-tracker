from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .models import Status


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    status: str
    at: datetime


class ApplicationOut(BaseModel):
    id: int
    company: str
    role: str
    status: str
    applied_date: date
    job_url: str
    notes: str
    source: str
    ats: str
    created_at: datetime
    status_changed_at: datetime
    days_since_applied: int
    possibly_ghosted: bool
    email_url: Optional[str]
    events: list[EventOut]


class ApplicationCreate(BaseModel):
    company: str = Field(min_length=1, max_length=200)
    role: str = Field(default="", max_length=300)
    applied_date: Optional[date] = None
    job_url: str = Field(default="", max_length=1000)
    notes: str = ""
    status: Status = Status.applied


class ApplicationUpdate(BaseModel):
    company: Optional[str] = Field(default=None, min_length=1, max_length=200)
    role: Optional[str] = Field(default=None, max_length=300)
    applied_date: Optional[date] = None
    job_url: Optional[str] = Field(default=None, max_length=1000)
    notes: Optional[str] = None
    status: Optional[Status] = None


class EmailRecordOut(BaseModel):
    id: int
    sender: str
    subject: str
    received_at: Optional[datetime]
    snippet: str
    guessed_company: str
    guessed_role: str
    ats: str
    outcome: str
    reason: str
    application_id: Optional[int]
    email_url: Optional[str]


class ReviewAccept(BaseModel):
    company: str = Field(min_length=1, max_length=200)
    role: str = Field(default="", max_length=300)
    job_url: str = Field(default="", max_length=1000)


class WeekCount(BaseModel):
    week_start: date
    count: int


class StatsOut(BaseModel):
    total: int
    by_status: dict[str, int]
    response_rate: float  # share of applications that got any reply (OA/interview/offer/rejected)
    median_days_to_response: Optional[float]
    applied_last_7_days: int
    possibly_ghosted: int
    per_week: list[WeekCount]


class MetaOut(BaseModel):
    imap_configured: bool
    imap_user: str
    imap_folder: str
    last_sync_at: Optional[datetime]
    ghost_after_days: int
    statuses: list[str]
    review_count: int
