"""Background sync: runs sync_from_imap every N minutes while the server is up.

Started from the FastAPI lifespan when SYNC_EVERY_MINUTES > 0 and IMAP is configured. One
daemon thread, its own DB session per run; a run that overlaps "Sync now" is simply skipped
(sync_from_imap holds a lock). With several server processes each would sync, which is
harmless (message IDs are unique) but wasteful: run one process.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable

log = logging.getLogger("job_tracker.sync")


class SyncScheduler:
    def __init__(self, every_seconds: float, first_delay: float = 15.0,
                 run: Callable[[], object] | None = None):
        self.every_seconds = every_seconds
        self.first_delay = first_delay
        self._run = run or _sync_once
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="sync-scheduler", daemon=True)
        self._thread.start()
        log.info("Auto-sync every %s minutes", round(self.every_seconds / 60, 1))

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)

    def _loop(self) -> None:
        delay = self.first_delay
        while not self._stop.wait(delay):
            try:
                self._run()
            except Exception:  # never let one bad run kill the loop
                log.exception("Scheduled sync failed")
            delay = self.every_seconds


def _sync_once() -> None:
    from .db import SessionLocal
    from .sync import SyncBusy, sync_from_imap

    with SessionLocal() as session:
        try:
            s = sync_from_imap(session)
        except SyncBusy:
            log.info("Skipped scheduled sync: another sync is running")
            return
        except Exception as e:  # already recorded as last_sync_error
            log.warning("Scheduled sync failed: %s", e)
            return
    log.info("Scheduled sync: %s new, %s to review, %s skipped", s.created, s.review, s.ignored)
