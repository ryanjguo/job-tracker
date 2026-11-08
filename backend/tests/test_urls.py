"""Only http(s) job links are stored (#41)."""
import pytest
from fastapi.testclient import TestClient

from app.importer import read_rows
from app.main import app
from app.urls import normalize_job_url


@pytest.mark.parametrize("raw,expected", [
    ("", ""),
    ("  https://jobs.acme.com/123  ", "https://jobs.acme.com/123"),
    ("http://acme.com/careers?id=1", "http://acme.com/careers?id=1"),
    ("jobs.acme.com/123", "https://jobs.acme.com/123"),
])
def test_accepted(raw, expected):
    assert normalize_job_url(raw) == expected


@pytest.mark.parametrize("raw", [
    "javascript:alert(1)", "JaVaScRiPt:alert(1)", "data:text/html,hi", "mailto:hr@acme.com",
    "see email", "https://", "ftp://acme.com/x",
])
def test_rejected(raw):
    with pytest.raises(ValueError):
        normalize_job_url(raw)


def test_api_rejects_bad_links_everywhere():
    c = TestClient(app, headers={"X-Job-Tracker": "1"})
    r = c.post("/api/applications", json={"company": "Acme", "job_url": "javascript:alert(1)"})
    assert r.status_code == 422 and "http" in r.text
    ok = c.post("/api/applications", json={"company": "Acme", "job_url": "jobs.acme.com/1"}).json()
    assert ok["job_url"] == "https://jobs.acme.com/1"
    r = c.patch(f"/api/applications/{ok['id']}", json={"job_url": "javascript:alert(1)"})
    assert r.status_code == 422
    assert c.patch(f"/api/applications/{ok['id']}", json={"job_url": ""}).json()["job_url"] == ""


def test_import_keeps_a_bad_link_as_a_note():
    from datetime import date
    rows, warnings = read_rows(
        [["Company", "Role", "Job Link"], ["Acme", "Intern", "javascript:alert(1)"],
         ["Globex", "Analyst", "globex.com/jobs/7"]],
        date(2026, 11, 8),
    )
    assert rows[0].job_url == "" and "Link in spreadsheet: javascript:alert(1)" in rows[0].notes
    assert rows[1].job_url == "https://globex.com/jobs/7"
    assert any("isn't a web address" in w for w in warnings)
