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
