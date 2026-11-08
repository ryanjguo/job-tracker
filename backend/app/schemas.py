from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import Status
from .urls import normalize_job_url


class _JobUrl(BaseModel):
    """job_url is rendered as a link: only http(s) (bare domains get https:// added)."""

    @field_validator("job_url", check_fields=False)
    @classmethod
    def _check_job_url(cls, v):
        return None if v is None else normalize_job_url(v)


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
    location: str
    term: str
    next_action: str
    follow_up_date: Optional[date]
    source: str
    ats: str
    created_at: datetime
    status_changed_at: datetime
    days_since_applied: int
    possibly_ghosted: bool
    email_url: Optional[str]
    events: list[EventOut]


class ApplicationCreate(_JobUrl):
    company: str = Field(min_length=1, max_length=200)
    role: str = Field(default="", max_length=300)
    applied_date: Optional[date] = None
    job_url: str = Field(default="", max_length=1000)
    notes: str = ""
    status: Status = Status.applied
    location: str = Field(default="", max_length=200)
    term: str = Field(default="", max_length=60)
    next_action: str = Field(default="", max_length=300)
    follow_up_date: Optional[date] = None


class ApplicationUpdate(_JobUrl):
    company: Optional[str] = Field(default=None, min_length=1, max_length=200)
    role: Optional[str] = Field(default=None, max_length=300)
    applied_date: Optional[date] = None
    job_url: Optional[str] = Field(default=None, max_length=1000)
    notes: Optional[str] = None
    status: Optional[Status] = None
    location: Optional[str] = Field(default=None, max_length=200)
    term: Optional[str] = Field(default=None, max_length=60)
    next_action: Optional[str] = Field(default=None, max_length=300)
    follow_up_date: Optional[date] = None  # send null to clear


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


class ReviewAccept(_JobUrl):
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
    sync_every_minutes: int  # 0 = no background sync
    last_sync_error: Optional[str]
