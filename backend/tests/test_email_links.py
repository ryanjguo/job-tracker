"""Gmail deep links open the account that received the email (#40)."""
import pytest

from app import main
from app.config import Settings


@pytest.fixture
def use(monkeypatch):
    def _use(**kw):
        monkeypatch.setattr(main, "settings", Settings(**kw))
    return _use


def test_link_names_the_account(use):
    use(imap_host="imap.gmail.com", imap_user="ryan@gmail.com", imap_password="x")
    assert main.email_url("<abc@mail.acme.com>") == (
        "https://mail.google.com/mail/?authuser=ryan@gmail.com#search/rfc822msgid%3Aabc%40mail.acme.com"
    )


def test_plus_addresses_are_escaped(use):
    use(imap_host="imap.gmail.com", imap_user="ryan+jobs@gmail.com", imap_password="x")
    assert "authuser=ryan%2Bjobs@gmail.com#" in main.email_url("<a@b>")


def test_no_user_falls_back_to_first_account(use):
    use(imap_host="imap.gmail.com", imap_user="")
    assert main.email_url("<a@b>").startswith("https://mail.google.com/mail/u/0/#search/")


def test_no_links_for_other_providers_or_fake_ids(use):
    use(imap_host="imap.fastmail.com", imap_user="me@fastmail.com", imap_password="x")
    assert main.email_url("<a@b>") is None
    use(imap_host="imap.gmail.com", imap_user="me@gmail.com", imap_password="x")
    assert main.email_url("<demo-1@example.com>") is None
    assert main.email_url("<generated-abc>") is None
