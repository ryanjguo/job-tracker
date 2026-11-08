"""Other websites can't drive the API (#42)."""
from fastapi.testclient import TestClient

from app.main import app

DASHBOARD = {"X-Job-Tracker": "1"}


def test_writes_without_the_dashboard_header_are_refused():
    c = TestClient(app)  # no header: what a cross-site form post / no-cors fetch looks like
    assert c.post("/api/applications", json={"company": "Acme"}).status_code == 403
    assert c.post("/api/sync").status_code == 403
    assert c.post("/api/emails/1/dismiss").status_code == 403
    assert c.delete("/api/applications/1").status_code == 403
    assert "X-Job-Tracker" in c.post("/api/sync").json()["detail"]


def test_dashboard_writes_and_all_reads_work():
    c = TestClient(app)
    assert c.post("/api/applications", json={"company": "Acme"}, headers=DASHBOARD).status_code == 201
    assert c.get("/api/applications").status_code == 200  # reads need no header


def test_unknown_host_names_are_refused():
    # A DNS-rebinding page reaches 127.0.0.1 but under its own host name
    c = TestClient(app, base_url="http://evil.example")
    assert c.get("/api/applications").status_code == 400
    assert TestClient(app, base_url="http://localhost:8000").get("/api/meta").status_code == 200
