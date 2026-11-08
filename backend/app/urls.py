"""Job-posting links are rendered as <a href>, so only http(s) URLs are ever stored."""
import re

_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*:", re.I)
_HTTP_RE = re.compile(r"^https?://[^\s/$.?#][^\s]*$", re.I)


def normalize_job_url(value: str | None) -> str:
    """'' stays ''; 'jobs.acme.com/1' -> 'https://jobs.acme.com/1'; http(s) URLs pass.

    Anything else (javascript:, mailto:, data:, text with spaces) raises ValueError.
    """
    v = (value or "").strip()
    if not v:
        return ""
    if not _SCHEME_RE.match(v) and "." in v.split("/")[0] and " " not in v:
        v = "https://" + v
    if not _HTTP_RE.match(v):
        raise ValueError("Job link must be a web address starting with http:// or https://")
    return v
