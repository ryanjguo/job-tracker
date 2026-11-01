"""CSV import, using a made-up sheet laid out like a Google Sheets tracker (title + totals above the table)."""
import csv
import io
from datetime import date

import pytest

from app.db import SessionLocal
from app.importer import column_field, import_rows, map_status, read_rows
from app.models import Application

SHEET = """\
,,,,,,,,,,
,Internship Application Tracker,,,,,,,,,
,TOTAL APPLICATIONS,,UNDER REVIEW,,INTERVIEWS,,OFFERS,,,
,5,,3,,1,,0,,,
,Company,Role / Position,Location,Date Applied,Term / Season,Status,Next Action,Deadline / Follow-up,Job Link / Portal,Notes
,Acme Robotics,Software Engineering Intern,Vancouver,2026-09-19,Summer 2027,Rejected,,,,"US rejected, Canada pending"
,Globex ,Software Engineering Intern,"Toronto, Waterloo",2026-09-19,Summer 2027,Interview,Prep system design,2026-11-05,,
,Initech,Backend Intern,Seattle,2026-09-20,Summer 2027,Online Assessment,,,careers.initech.example,Didn't do the OA
,Hooli,Data Intern,,Unsure,Summer 2027,Applied,,,,
,Hooli,"Software Engineering Intern, 6 month","Redmond, WA",2026-09-21,Summer 2027,Applied,,,https://hooli.example/jobs/1,
,,,,,,,,,,
"""

TODAY = date(2026, 11, 1)


def rows():
    return read_rows(list(csv.reader(io.StringIO(SHEET))), TODAY)


def test_reads_table_below_title_block():
    parsed, warnings = rows()
    assert [r.company for r in parsed] == ["Acme Robotics", "Globex", "Initech", "Hooli", "Hooli"]
    assert [r.status for r in parsed] == ["rejected", "interview", "oa", "applied", "applied"]
    assert parsed[1].role == "Software Engineering Intern"
    assert parsed[1].applied_date == date(2026, 9, 19)


def test_extra_columns_are_kept_in_notes():
    parsed, _ = rows()
    assert parsed[0].notes.splitlines() == [
        "US rejected, Canada pending", "Location: Vancouver", "Term / Season: Summer 2027",
    ]
    assert "Next Action: Prep system design" in parsed[1].notes
    assert "Deadline / Follow-up: 2026-11-05" in parsed[1].notes


def test_bare_link_gets_a_scheme():
    parsed, _ = rows()
    assert parsed[2].job_url == "https://careers.initech.example"
    assert parsed[4].job_url == "https://hooli.example/jobs/1"


def test_unreadable_date_uses_previous_row_and_says_so():
    parsed, warnings = rows()
    assert parsed[3].applied_date == date(2026, 9, 20)
    assert "Applied date in spreadsheet: Unsure (set to 2026-09-20)" in parsed[3].notes
    assert len(warnings) == 1 and "Unsure" in warnings[0]


def test_missing_company_header_is_an_error():
    with pytest.raises(ValueError):
        read_rows([["Name", "Status"], ["x", "Applied"]], TODAY)


@pytest.mark.parametrize("word,status", [
    ("Applied", "applied"), ("Under review", "applied"), ("Online Assessment", "oa"), ("OA", "oa"),
    ("Phone screen", "interview"), ("Final round interview", "interview"), ("Offer", "offer"),
    ("Rejected", "rejected"), ("No offer", "rejected"), ("Ghosted", "ghosted"), ("Withdrew", "withdrawn"),
])
def test_status_words(word, status):
    assert map_status(word).value == status


def test_headers():
    assert column_field("Role / Position") == "role"
    assert column_field("Date Applied") == "applied_date"
    assert column_field("Job Link / Portal") == "job_url"
    assert column_field("Deadline / Follow-up") is None
    assert column_field("Location") is None


def test_import_saves_history_and_is_idempotent():
    parsed, _ = rows()
    with SessionLocal() as s:
        dry = import_rows(s, parsed, dry_run=True)
        assert len(dry.created) == 5 and s.query(Application).count() == 0

        first = import_rows(s, parsed)
        again = import_rows(s, parsed)
        assert (len(first.created), len(again.created), len(again.skipped_existing)) == (5, 0, 5)

        globex = s.query(Application).filter_by(company="Globex").one()
        assert globex.source == "import" and globex.status == "interview"
        # no invented date for the interview: only the known "applied" event is logged
        assert [e.status for e in globex.events] == ["applied"]
        assert globex.events[0].at.date() == date(2026, 9, 19)
