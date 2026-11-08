"""CSV export (#43): round-trips through the importer and is safe to open in a spreadsheet."""
import csv
import io
from datetime import date

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.exporter import applications_csv
from app.importer import import_rows, read_rows
from app.main import app
from app.models import Application
from app.sync import create_application


def seed(s):
    a = create_application(s, company="Acme, Inc.", role="Software Engineer, Platform",
                           applied_date=date(2026, 10, 3), source="email",
                           job_url="https://jobs.acme.com/1", notes="Referred by Sam\nSecond line",
                           location="Vancouver, BC", term="Summer 2027", next_action="Prep OA",
                           follow_up_date=date(2026, 11, 20))
    a.status = "oa"
    create_application(s, company="=HYPERLINK(\"http://evil\")", role="@SUM(1)",
                       applied_date=date(2026, 10, 5), source="email")
    s.commit()


def parse(text):
    return list(csv.reader(io.StringIO(text.lstrip("﻿"))))


def test_export_round_trips_through_the_importer():
    with SessionLocal() as s:
        seed(s)
        text = applications_csv(s)
    rows, warnings = read_rows(parse(text), date(2026, 11, 8))
    assert warnings == []
    acme = next(r for r in rows if r.company == "Acme, Inc.")
    assert (acme.role, acme.status, acme.location, acme.term, acme.next_action) == (
        "Software Engineer, Platform", "oa", "Vancouver, BC", "Summer 2027", "Prep OA")
    assert (acme.applied_date, acme.follow_up_date) == (date(2026, 10, 3), date(2026, 11, 20))
    assert (acme.job_url, acme.notes) == ("https://jobs.acme.com/1", "Referred by Sam\nSecond line")
    evil = next(r for r in rows if r.role == "@SUM(1)")  # guard undone on import
    assert evil.company == '=HYPERLINK("http://evil")'

    # importing the export into a database that already has them adds nothing
    with SessionLocal() as s:
        assert len(import_rows(s, rows).created) == 0
        assert len(s.query(Application).all()) == 2


def test_formulas_are_neutralised_in_the_file():
    with SessionLocal() as s:
        seed(s)
        cells = [c for row in parse(applications_csv(s)) for c in row]
    assert '\'=HYPERLINK("http://evil")' in cells and "'@SUM(1)" in cells
    assert not any(c.startswith(("=", "+", "@")) for c in cells)


def test_export_endpoint_downloads_a_file():
    with SessionLocal() as s:
        seed(s)
    r = TestClient(app).get("/api/export.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert 'attachment; filename="job-applications-' in r.headers["content-disposition"]
    assert parse(r.text)[0][:2] == ["Company", "Role"]
