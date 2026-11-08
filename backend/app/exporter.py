"""CSV export. Column names are ones the importer maps back to fields, so export -> import
round-trips (and the file opens cleanly in Excel / Google Sheets)."""
from __future__ import annotations

import csv
import io

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Application

COLUMNS = ["Company", "Role", "Location", "Term", "Date Applied", "Status", "Next Action",
           "Follow-up Date", "Job Link", "Notes"]

STATUS_LABELS = {"applied": "Applied", "oa": "OA", "interview": "Interview", "offer": "Offer",
                 "rejected": "Rejected", "ghosted": "Ghosted", "withdrawn": "Withdrawn"}

# Cells starting with these run as formulas in spreadsheet apps; company names and roles come
# from emails, so they're prefixed with ' (the importer strips it again).
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: str) -> str:
    return "'" + value if value.startswith(_FORMULA_START) else value


def unsafe_cell(value: str) -> str:
    """Undo safe_cell when importing."""
    return value[1:] if value.startswith("'") and value[1:].startswith(_FORMULA_START) else value


def row_for(a: Application) -> list[str]:
    return [safe_cell(v) for v in (
        a.company, a.role, a.location, a.term, a.applied_date.isoformat(),
        STATUS_LABELS.get(a.status, a.status), a.next_action,
        a.follow_up_date.isoformat() if a.follow_up_date else "", a.job_url, a.notes,
    )]


def applications_csv(session: Session) -> str:
    apps = session.scalars(
        select(Application).order_by(Application.applied_date.desc(), Application.id.desc())
    ).all()
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    writer.writerows(row_for(a) for a in apps)
    # BOM so Excel reads it as UTF-8 (the importer reads utf-8-sig)
    return "﻿" + buf.getvalue()
