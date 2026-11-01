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

FIELDS = ("company", "role", "applied_date", "status", "job_url", "notes")

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

        for i, h in enumerate(headers):
            if mapping[i] is None and h and cells[i]:
                notes.append(f"{h}: {cells[i]}")

        rows.append(ImportRow(
            line=offset, company=company, role=values.get("role", ""), applied_date=applied,
            status=status.value, job_url=clean_url(values.get("job_url", "")),
            notes="\n".join(n for n in notes if n),
        ))
    return rows, warnings


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
            source="import", job_url=row.job_url, notes=row.notes,
        )
        # History starts with "applied" on the applied date. The sheet doesn't say when the status
        # last changed, so no event is logged for it: an invented date would skew "days to response".
        app.events[0].at = datetime.combine(row.applied_date, time(12), tzinfo=timezone.utc)
        app.created_at = now
        app.status = row.status
    if not dry_run:
        session.commit()
    return summary
