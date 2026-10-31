"""Reading email over IMAP (works with Gmail, Outlook, Fastmail, ...).

Headers are fetched first for everything since a date; bodies are only downloaded for emails
that pass the cheap prefilter. BODY.PEEK is used everywhere, so nothing gets marked as read.
"""
from __future__ import annotations

import hashlib
import imaplib
import re
from dataclasses import dataclass
from datetime import date, datetime
from email import message_from_bytes, policy
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Iterable, Protocol


@dataclass
class MailHeader:
    uid: str
    message_id: str
    sender: str
    subject: str
    received_at: datetime | None


class MailSource(Protocol):
    def fetch_headers(self, since: date) -> list[MailHeader]: ...
    def fetch_body(self, uid: str) -> str: ...


# --------------------------------------------------------------------------------------
# HTML -> text
# --------------------------------------------------------------------------------------
class _TextExtractor(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "section"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self._skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head"):
            self._skip = max(0, self._skip - 1)
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    p = _TextExtractor()
    try:
        p.feed(html)
    except Exception:
        return re.sub(r"<[^>]+>", " ", html)
    text = "".join(p.parts)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def message_text(raw: bytes) -> str:
    msg = message_from_bytes(raw, policy=policy.default)
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    try:
        content = part.get_content()
    except Exception:
        payload = part.get_payload(decode=True) or b""
        content = payload.decode("utf-8", errors="replace")
    if part.get_content_type() == "text/html":
        return html_to_text(content)
    return re.sub(r"[ \t\xa0]+", " ", content).strip()


def _parse_headers(raw: bytes, uid: str) -> MailHeader:
    msg = message_from_bytes(raw, policy=policy.default)
    sender = str(msg.get("From", "") or "")
    subject = str(msg.get("Subject", "") or "")
    received = None
    if msg.get("Date"):
        try:
            received = parsedate_to_datetime(str(msg["Date"]))
        except (TypeError, ValueError):
            received = None
    message_id = str(msg.get("Message-ID", "") or "").strip()
    if not message_id:
        digest = hashlib.sha1(f"{sender}|{subject}|{msg.get('Date', '')}".encode()).hexdigest()
        message_id = f"<generated-{digest}>"
    return MailHeader(uid=uid, message_id=message_id, sender=sender, subject=subject, received_at=received)


# --------------------------------------------------------------------------------------
# IMAP implementation
# --------------------------------------------------------------------------------------
class ImapSource:
    def __init__(self, host: str, port: int, user: str, password: str, folder: str = "INBOX"):
        self.host, self.port, self.user, self.password, self.folder = host, port, user, password, folder
        self.conn: imaplib.IMAP4_SSL | None = None

    def __enter__(self):
        self.conn = imaplib.IMAP4_SSL(self.host, self.port)
        self.conn.login(self.user, self.password)
        folder = self.folder if self.folder.startswith('"') else f'"{self.folder}"'
        typ, _ = self.conn.select(folder, readonly=True)
        if typ != "OK":
            raise RuntimeError(f"Could not open folder {self.folder!r}")
        return self

    def __exit__(self, *exc):
        if self.conn:
            try:
                self.conn.logout()
            except Exception:
                pass

    def fetch_headers(self, since: date) -> list[MailHeader]:
        assert self.conn
        typ, data = self.conn.uid("SEARCH", None, f"SINCE {since.strftime('%d-%b-%Y')}")
        if typ != "OK" or not data or not data[0]:
            return []
        uids = data[0].split()
        headers: list[MailHeader] = []
        for batch in _chunks(uids, 200):
            typ, resp = self.conn.uid(
                "FETCH", b",".join(batch).decode(),
                "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT MESSAGE-ID DATE)])",
            )
            if typ != "OK":
                continue
            for item in resp:
                if not isinstance(item, tuple):
                    continue
                m = re.search(rb"UID (\d+)", item[0])
                if m:
                    headers.append(_parse_headers(item[1], m.group(1).decode()))
        return headers

    def fetch_body(self, uid: str) -> str:
        assert self.conn
        typ, resp = self.conn.uid("FETCH", uid, "(BODY.PEEK[])")
        if typ != "OK":
            return ""
        for item in resp:
            if isinstance(item, tuple):
                return message_text(item[1])
        return ""


def _chunks(seq: list, n: int) -> Iterable[list]:
    for i in range(0, len(seq), n):
        yield seq[i : i + n]
