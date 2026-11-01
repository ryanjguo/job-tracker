from datetime import date, datetime, timezone
from enum import Enum

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Status(str, Enum):
    applied = "applied"
    oa = "oa"
    interview = "interview"
    offer = "offer"
    rejected = "rejected"
    ghosted = "ghosted"
    withdrawn = "withdrawn"


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(20), default=Status.applied.value, index=True)
    applied_date: Mapped[date] = mapped_column(Date)
    job_url: Mapped[str] = mapped_column(String(1000), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    # "email" (created by sync), "review" (accepted from review queue), "manual"
    source: Mapped[str] = mapped_column(String(20), default="manual")
    ats: Mapped[str] = mapped_column(String(40), default="")  # greenhouse, lever, ...
    email_message_id: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    events: Mapped[list["StatusEvent"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", order_by="StatusEvent.at"
    )


class StatusEvent(Base):
    """Every status change is logged, so stats like 'days to first response' are possible."""

    __tablename__ = "status_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    application: Mapped[Application] = relationship(back_populates="events")


class EmailRecord(Base):
    """Every candidate email the sync has looked at. message_id is unique, so re-syncing is safe."""

    __tablename__ = "email_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    sender: Mapped[str] = mapped_column(String(500), default="")
    subject: Mapped[str] = mapped_column(String(1000), default="")
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    snippet: Mapped[str] = mapped_column(Text, default="")
    guessed_company: Mapped[str] = mapped_column(String(200), default="")
    guessed_role: Mapped[str] = mapped_column(String(300), default="")
    ats: Mapped[str] = mapped_column(String(40), default="")
    # created | duplicate | review | accepted | dismissed | ignored
    outcome: Mapped[str] = mapped_column(String(20), index=True)
    reason: Mapped[str] = mapped_column(String(300), default="")
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL"), nullable=True
    )
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Meta(Base):
    """Tiny key/value store (e.g. last successful sync time)."""

    __tablename__ = "meta"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
