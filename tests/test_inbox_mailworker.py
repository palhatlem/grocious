"""Bridge folder-discovery regression, exercised through the real session setup."""

import logging
from unittest.mock import MagicMock

import pytest

from inbox import mailworker


class EndSession(BaseException):
    pass


@pytest.mark.parametrize("missing", [False, True])
def test_bridge_list_names_reach_idle(tmp_path, monkeypatch, missing):
    import imapclient

    monkeypatch.setenv("GROCERY_DATA", str(tmp_path))
    monkeypatch.setenv("IMAP_HOST", "imap.example.test")
    monkeypatch.setenv("IMAP_USER", "synthetic-user")
    monkeypatch.setenv("IMAP_PASSWORD", "synthetic-password")
    monkeypatch.setenv("IMAP_SECURITY", "starttls")
    names = ["Folders/Grocious/Inbox", "Folders/Grocious/Done", "Folders/Grocious/Failed"]
    for key, name in zip(("IMAP_FOLDER", "IMAP_DONE", "IMAP_FAILED"), names):
        monkeypatch.setenv(key, name)
    client = MagicMock()
    client.__enter__.return_value = client
    # Reproduce Bridge: folder_exists lies, unfiltered LIST contains the real names.
    client.folder_exists.return_value = False
    client.list_folders.return_value = [((), "/", name) for name in (names[:-1] if missing else names)]
    client.search.return_value = []
    client.idle_check.side_effect = EndSession
    monkeypatch.setattr(imapclient, "IMAPClient", lambda *args, **kwargs: client)
    with pytest.raises(EndSession):
        mailworker.session()
    client.list_folders.assert_called_once_with()
    client.folder_exists.assert_not_called()
    if missing:
        client.create_folder.assert_called_once_with(names[-1])
    else:
        client.create_folder.assert_not_called()
    client.select_folder.assert_called_once_with(names[0])
    client.starttls.assert_called_once()
    client.idle.assert_called_once()
    client.idle_done.assert_called_once()


def test_reconnect_logs_reason_with_credentials_redacted(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("GROCERY_DATA", str(tmp_path))
    monkeypatch.setenv("IMAP_PASSWORD", "synthetic-password")
    monkeypatch.setenv("IMAP_USER", "synthetic-user")

    def fail():
        raise RuntimeError("mailbox already exists; synthetic-user synthetic-password")

    def stop(_):
        raise EndSession

    monkeypatch.setattr(mailworker, "session", fail)
    monkeypatch.setattr(mailworker.time, "sleep", stop)
    with caplog.at_level(logging.WARNING), pytest.raises(EndSession):
        mailworker.main()
    assert "RuntimeError" in caplog.text
    assert "mailbox already exists" in caplog.text
    assert "Traceback" in caplog.text
    assert "synthetic-password" not in caplog.text
    assert "synthetic-user" not in caplog.text
