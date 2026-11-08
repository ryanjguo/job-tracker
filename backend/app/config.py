"""Settings, read from environment variables (or a .env file in backend/)."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./tracker.db")

    # IMAP (Gmail: imap.gmail.com + an App Password, see README)
    imap_host: str = os.getenv("IMAP_HOST", "imap.gmail.com")
    imap_port: int = _int("IMAP_PORT", 993)
    imap_user: str = os.getenv("IMAP_USER", "")
    imap_password: str = os.getenv("IMAP_PASSWORD", "")
    imap_folder: str = os.getenv("IMAP_FOLDER", "INBOX")

    # How far back the very first sync looks
    initial_lookback_days: int = _int("INITIAL_LOOKBACK_DAYS", 90)
    # An "applied" entry older than this gets flagged as possibly ghosted
    ghost_after_days: int = _int("GHOST_AFTER_DAYS", 30)
    # Two confirmations for the same company+role within this window = duplicate
    duplicate_window_days: int = _int("DUPLICATE_WINDOW_DAYS", 60)
    # Sync in the background every N minutes while the server runs (0 = only "Sync now" / cron)
    sync_every_minutes: int = _int("SYNC_EVERY_MINUTES", 0)
    # Host names the server answers to (blocks DNS-rebinding pages). Add your domain if you host
    # it, or "*" to allow any.
    allowed_hosts: tuple[str, ...] = tuple(
        h.strip() for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,::1").split(",") if h.strip()
    )

    @property
    def imap_configured(self) -> bool:
        return bool(self.imap_user and self.imap_password)

    @property
    def is_gmail(self) -> bool:
        return "gmail" in self.imap_host.lower()


settings = Settings()
