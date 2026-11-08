"""Background sync (#28): the scheduler loop, and remembering the last sync error."""
import threading

import pytest
from fastapi.testclient import TestClient

from app import sync as sync_mod
from app.config import Settings
from app.db import SessionLocal
from app.main import app
from app.scheduler import SyncScheduler
from app.sync import last_sync_error, sync_from_imap


def test_scheduler_runs_repeatedly_and_survives_errors():
    calls = []
    done = threading.Event()

    def run():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")  # a failing run must not stop the loop
        if len(calls) >= 3:
            done.set()

    s = SyncScheduler(every_seconds=0.01, first_delay=0, run=run)
    s.start()
    assert done.wait(2)
    s.stop()
    assert not s._thread.is_alive()


def test_stop_before_first_run_never_runs():
    calls = []
    s = SyncScheduler(every_seconds=60, first_delay=60, run=lambda: calls.append(1))
    s.start()
    s.stop()
    assert calls == []


CFG = Settings(imap_user="me@example.com", imap_password="x")


class BrokenImap:
    def __init__(self, *a):
        pass

    def __enter__(self):
        raise OSError("LOGIN failed: invalid credentials")

    def __exit__(self, *a):
        pass


class EmptyImap(BrokenImap):
    def __enter__(self):
        return self

    def fetch_headers(self, since):
        return []


def test_failed_sync_is_remembered_and_cleared_by_a_success(monkeypatch):
    with SessionLocal() as s:
        monkeypatch.setattr(sync_mod, "ImapSource", BrokenImap)
        with pytest.raises(OSError):
            sync_from_imap(s, CFG)
        assert "invalid credentials" in last_sync_error(s)

        monkeypatch.setattr(sync_mod, "ImapSource", EmptyImap)
        sync_from_imap(s, CFG)
        assert last_sync_error(s) is None


def test_meta_reports_schedule_and_error(monkeypatch):
    with SessionLocal() as s:
        monkeypatch.setattr(sync_mod, "ImapSource", BrokenImap)
        with pytest.raises(OSError):
            sync_from_imap(s, CFG)
    meta = TestClient(app).get("/api/meta").json()
    assert meta["sync_every_minutes"] == 0  # IMAP isn't configured in tests
    assert "invalid credentials" in meta["last_sync_error"]
