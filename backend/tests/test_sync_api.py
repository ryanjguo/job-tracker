from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.mail import MailHeader
from app.main import app
from app.sync import run_sync


class FakeMailbox:
    def __init__(self, items):
        self.items = items

    def fetch_headers(self, since):
        return [h for h, _ in self.items]

    def fetch_body(self, uid):
        return {h.uid: b for h, b in self.items}[uid]


NOW = datetime.now(timezone.utc)
ITEMS = [
    (MailHeader("1", "<a@x>", "Acme <no-reply@greenhouse.io>", "Thank you for applying to Acme!", NOW),
     "We received your application for Backend Engineer, thanks."),
    (MailHeader("2", "<b@x>", "Acme <no-reply@greenhouse.io>", "Thank you for applying to Acme!", NOW),
     "Second copy of the same confirmation."),
    (MailHeader("3", "<c@x>", "noreply@jobs-mailer.net", "Thank you for applying!", NOW),
     "We received your application."),
    (MailHeader("4", "<d@x>", "Mom <mom@gmail.com>", "Dinner Sunday?", NOW), "hi"),
]


def test_sync_creates_dedupes_and_queues():
    with SessionLocal() as s:
        summary = run_sync(s, FakeMailbox(ITEMS))
    assert (summary.created, summary.duplicates, summary.review) == (1, 1, 1)
    assert summary.candidates == 3  # the personal email never got its body downloaded


def test_resync_is_idempotent():
    with SessionLocal() as s:
        run_sync(s, FakeMailbox(ITEMS))
        again = run_sync(s, FakeMailbox(ITEMS))
    assert again.candidates == 0 and again.created == 0


def test_review_accept_status_change_and_stats():
    with SessionLocal() as s:
        run_sync(s, FakeMailbox(ITEMS))
    c = TestClient(app, headers={"X-Job-Tracker": "1"})

    review = c.get("/api/emails").json()
    assert [r["subject"] for r in review] == ["Thank you for applying!"]

    a = c.post(f"/api/emails/{review[0]['id']}/accept", json={"company": "Jobs Co", "role": "Dev"}).json()
    assert a["source"] == "review"

    p = c.patch(f"/api/applications/{a['id']}", json={"status": "oa"}).json()
    assert p["status"] == "oa" and [e["status"] for e in p["events"]] == ["applied", "oa"]

    assert c.post("/api/applications", json={"company": "Manual Inc"}).status_code == 201
    stats = c.get("/api/stats").json()
    assert stats["total"] == 3 and stats["by_status"]["oa"] == 1

    assert c.delete(f"/api/applications/{a['id']}").status_code == 204
    assert c.get("/api/meta").json()["review_count"] == 0


def test_sync_without_imap_config_is_a_clear_400():
    r = TestClient(app, headers={"X-Job-Tracker": "1"}).post("/api/sync")
    assert r.status_code == 400 and "IMAP" in r.json()["detail"]


def test_location_term_next_action_and_follow_up_via_api():
    c = TestClient(app, headers={"X-Job-Tracker": "1"})
    a = c.post("/api/applications", json={
        "company": "Acme", "location": "Vancouver", "term": "Summer 2027",
        "next_action": "Follow up with recruiter", "follow_up_date": "2026-11-05",
    }).json()
    assert (a["location"], a["term"], a["next_action"], a["follow_up_date"]) == (
        "Vancouver", "Summer 2027", "Follow up with recruiter", "2026-11-05")

    p = c.patch(f"/api/applications/{a['id']}", json={"location": "Remote", "follow_up_date": None}).json()
    assert p["location"] == "Remote" and p["follow_up_date"] is None and p["term"] == "Summer 2027"
