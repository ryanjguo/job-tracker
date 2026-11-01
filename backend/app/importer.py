"""Import applications from a spreadsheet exported as CSV (e.g. Google Sheets: File > Download > CSV).

The sheet can have a title or totals block above the table: the header row is the first row with a
"Company" column. Known columns map to Application fields; every other non-empty column is kept as
a "Header: value" line in the notes, so nothing in the sheet is lost.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Application, Status, utcnow
from .parser import normalize_company, normalize_role
from .sync import create_application

FIELDS = ("company", "role", "applied_date", "status", "job_url", "notes",
          "location", "term", "next_action", "follow_up_date")
# optional fields added after v1; also the note-line prefixes moved by backfill_fields_from_notes
EXTRA_FIELDS = ("location", "term", "next_action", "follow_up_date")

# Spreadsheet status words -> app statuses (matched on the lowercased cell)
STATUS_WORDS: list[tuple[re.Pattern, Status]] = [
    (re.compile(r"withdr[ae]w"), Status.withdrawn),
    (re.compile(r"ghost|no response|never heard"), Status.ghosted),
    (re.compile(r"reject|declined|not selected|no offer"), Status.rejected),
    (re.compile(r"offer"), Status.offer),
    (re.compile(r"interview|phone screen|onsite|final round|superday"), Status.interview),
    (re.compile(r"\boa\b|assessment|coding challenge|hackerrank|codesignal|take-?home"), Status.oa),
    (re.compile(r"appl|submitted|under review|in review|pending|waiting"), Status.applied),
]

DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%Y/%m/%d")


@dataclass
class ImportRow:
    line: int
    company: str
    role: str
    applied_date: date
    status: str
    job_url: str
    notes: str
    location: str = ""
    term: str = ""
    next_action: str = ""
    follow_up_date: date | None = None


@dataclass
class ImportSummary:
    created: list[ImportRow] = field(default_factory=list)
    skipped_existing: list[ImportRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------------------
# Reading the sheet
# --------------------------------------------------------------------------------------
def column_field(header: str) -> str | None:
    """Which Application field a header maps to, or None to keep it as a note line."""
    h = re.sub(r"\s+", " ", header.strip().lower())
    if not h:
        return None
    if "company" in h or h in {"employer", "organization", "organisation"}:
        return "company"
    if "location" in h or h in {"city", "office", "where"}:
        return "location"
    if "term" in h or "season" in h or h in {"cycle", "intake"}:
        return "term"
    if "next" in h and ("action" in h or "step" in h):
        return "next_action"
    if "follow" in h or "deadline" in h or h in {"due", "due date", "remind", "reminder"}:
        return "follow_up_date"
    if "role" in h or "position" in h or "title" in h:
        return "role"
    if ("appl" in h and ("date" in h or h == "applied")) or h in {"date", "applied on", "submitted"}:
        return "applied_date"
    if "status" in h or h == "stage":
        return "status"
    if "link" in h or "url" in h or "portal" in h or "posting" in h:
        return "job_url"
    if "note" in h or "comment" in h:
        return "notes"
    return None


def parse_date(value: str) -> date | None:
    v = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def map_status(value: str) -> Status | None:
    v = value.strip().lower()
    for rx, status in STATUS_WORDS:
        if rx.search(v):
            return status
    return None


def clean_url(value: str) -> str:
    v = value.strip()
    if v and not re.match(r"^[a-z][a-z0-9+.-]*://", v, re.I) and "." in v and " " not in v:
        v = "https://" + v
    return v


def read_rows(lines: list[list[str]], today: date) -> tuple[list[ImportRow], list[str]]:
    """Turn raw CSV rows into ImportRows. Returns (rows, warnings)."""
    warnings: list[str] = []
    header_idx = next(
        (i for i, row in enumerate(lines) if any(column_field(c) == "company" for c in row)), None
    )
    if header_idx is None:
        raise ValueError("No header row with a 'Company' column found")
    headers = [c.strip() for c in lines[header_idx]]
    mapping = {i: column_field(h) for i, h in enumerate(headers)}
    # first column wins if two headers map to the same field
    seen: set[str] = set()
    for i, f in list(mapping.items()):
        if f in seen:
            mapping[i] = None
        elif f:
            seen.add(f)

    rows: list[ImportRow] = []
    last_date: date | None = None
    for offset, raw in enumerate(lines[header_idx + 1:], start=header_idx + 2):
        cells = {i: (raw[i].strip() if i < len(raw) else "") for i in range(len(headers))}
        values = {f: cells[i] for i, f in mapping.items() if f}
        company = values.get("company", "")
        if not company:
            continue
        notes = [values.get("notes", "")]

        applied = parse_date(values.get("applied_date", ""))
        if applied is None:
            original = values.get("applied_date", "") or "blank"
            applied = last_date or today
            notes.append(f"Applied date in spreadsheet: {original} (set to {applied.isoformat()})")
            warnings.append(f"line {offset}: {company}: date {original!r} not understood, using {applied}")
        last_date = applied

        raw_status = values.get("status", "")
        status = map_status(raw_status) if raw_status else Status.applied
        if status is None:
            status = Status.applied
            notes.append(f"Status in spreadsheet: {raw_status}")
            warnings.append(f"line {offset}: {company}: status {raw_status!r} not understood, using applied")

        follow_up = None
        raw_follow = values.get("follow_up_date", "")
        if raw_follow:
            follow_up = parse_date(raw_follow)
            if follow_up is None:  # e.g. "ASAP": keep the words
                notes.append(f"{headers[_col(mapping, 'follow_up_date')]}: {raw_follow}")

        for i, h in enumerate(headers):
            if mapping[i] is None and h and cells[i]:
                notes.append(f"{h}: {cells[i]}")

        rows.append(ImportRow(
            line=offset, company=company, role=values.get("role", ""), applied_date=applied,
            status=status.value, job_url=clean_url(values.get("job_url", "")),
            notes="\n".join(n for n in notes if n),
            location=values.get("location", ""), term=values.get("term", ""),
            next_action=values.get("next_action", ""), follow_up_date=follow_up,
        ))
    return rows, warnings


def _col(mapping: dict[int, str | None], name: str) -> int:
    return next(i for i, f in mapping.items() if f == name)


def read_csv(path: str | Path, today: date | None = None) -> tuple[list[ImportRow], list[str]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return read_rows(list(csv.reader(f)), today or date.today())


# --------------------------------------------------------------------------------------
# Writing to the database
# --------------------------------------------------------------------------------------
def _key(company: str, role: str, applied: date) -> tuple[str, str, date]:
    return normalize_company(company), normalize_role(role), applied


def import_rows(session: Session, rows: list[ImportRow], dry_run: bool = False) -> ImportSummary:
    """Create an application per row. A row matching an existing application's company, role and
    applied date is skipped, so importing the same file twice is safe."""
    summary = ImportSummary()
    existing = {_key(a.company, a.role, a.applied_date) for a in session.scalars(select(Application))}
    now = utcnow()
    for row in rows:
        key = _key(row.company, row.role, row.applied_date)
        if key in existing:
            summary.skipped_existing.append(row)
            continue
        existing.add(key)
        summary.created.append(row)
        if dry_run:
            continue
        app = create_application(
            session, company=row.company, role=row.role, applied_date=row.applied_date,
            source="import", job_url=row.job_url, notes=row.notes, location=row.location,
            term=row.term, next_action=row.next_action, follow_up_date=row.follow_up_date,
        )
        # History starts with "applied" on the applied date. The sheet doesn't say when the status
        # last changed, so no event is logged for it: an invented date would skew "days to response".
        app.events[0].at = datetime.combine(row.applied_date, time(12), tzinfo=timezone.utc)
        app.created_at = now
        app.status = row.status
    if not dry_run:
        session.commit()
    return summary


# --------------------------------------------------------------------------------------
# One-time upgrade for databases imported before these fields existed
# --------------------------------------------------------------------------------------
_NOTE_LINE = re.compile(r"^(?P<label>[^:\n]{2,40}):\s*(?P<value>.+)$")


def move_note_lines(app: Application) -> bool:
    """Move "Location: Vancouver"-style note lines (written by older imports) into the matching
    empty field. Returns True if anything changed."""
    kept, changed = [], False
    for line in (app.notes or "").splitlines():
        m = _NOTE_LINE.match(line.strip())
        name = column_field(m.group("label")) if m else None
        if name in EXTRA_FIELDS and not getattr(app, name):
            value = m.group("value").strip()
            if name == "follow_up_date":
                parsed = parse_date(value)
                if parsed is None:
                    kept.append(line)
                    continue
                value = parsed
            setattr(app, name, value)
            changed = True
        else:
            kept.append(line)
    if changed:
        app.notes = "\n".join(kept)
    return changed


def backfill_fields_from_notes(bind) -> int:
    with Session(bind=bind) as s:
        n = sum(move_note_lines(a) for a in s.scalars(select(Application).where(Application.notes != "")))
        s.commit()
    return n
