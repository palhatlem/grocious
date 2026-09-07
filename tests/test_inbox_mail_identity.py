"""Re-presented EML deliveries must not create another purchase."""

from email.message import EmailMessage
from unittest.mock import Mock

import pytest
import receipt_archive as archive
from inbox import mailworker, store


def message(text="Synthetic purchase", attachment=b"Example\nTOTALT 25,00 NOK", message_id="<fixture@example.test>"):
    msg = EmailMessage()
    if message_id:
        msg["Message-ID"] = message_id
    msg["From"] = "store@example.test"
    msg["To"] = "receipts@example.test"
    msg["Date"] = "Mon, 7 Sep 2026 01:00:00 +0000"
    msg["Subject"] = "Synthetic receipt"
    msg.set_content(text)
    msg.add_attachment(attachment, maintype="text", subtype="plain", filename="receipt.txt")
    return msg.as_bytes()


def test_replay_preserves_raw_variants_and_moves_both(tmp_path, monkeypatch):
    monkeypatch.setenv("GROCERY_DATA", str(tmp_path))
    client = Mock()
    first = message()
    second = b"Received: another transport hop\n" + first
    result = mailworker.process_message(client, 1, first)
    directory = archive.folder("inbox", result["rid"])
    baseline = (directory / "receipt.json").read_bytes()
    # Pre-upgrade archives did not have a cached identity: the original is enough to recover it.
    (directory / "mail-identity.json").unlink()
    duplicate = mailworker.process_message(client, 2, second)
    assert duplicate["rid"] == result["rid"]
    assert duplicate["duplicate_reason"] == "message_id_and_payload"
    assert duplicate["children"] == result["children"]
    assert archive.summary("inbox")["count"] == 2  # one EML plus one attachment
    assert (directory / "receipt.json").read_bytes() == baseline
    originals = [d for d in archive.read_receipt("inbox", result["rid"])["documents"] if d["role"] == "email"]
    assert len(originals) == 2
    assert {archive.document("inbox", result["rid"], d["filename"])[0].read_bytes() for d in originals} == {
        first,
        second,
    }
    mailworker.process_message(client, 3, second)
    assert len(archive.read_receipt("inbox", result["rid"])["documents"]) == 3  # two EML + extracted text
    assert client.move.call_count == 3


@pytest.mark.parametrize("change", ["body", "attachment", "missing_id"])
def test_same_id_cannot_hide_changed_content(tmp_path, monkeypatch, change):
    monkeypatch.setenv("GROCERY_DATA", str(tmp_path))
    first = message(message_id=None if change == "missing_id" else "<fixture@example.test>")
    a = store.ingest(first, "message.eml", "message/rfc822")
    if change == "body":
        second = message(text="Different purchase")
    elif change == "attachment":
        second = message(attachment=b"Other purchase\nTOTALT 50,00 NOK")
    else:
        second = b"Received: another hop\n" + first
    b = store.ingest(second, "message.eml", "message/rfc822")
    assert a["rid"] != b["rid"]
    assert not b["duplicate"]


def test_replay_does_not_resurrect_discarded_mail(tmp_path, monkeypatch):
    monkeypatch.setenv("GROCERY_DATA", str(tmp_path))
    first = message()
    a = store.ingest(first, "message.eml", "message/rfc822")
    store.state(a["rid"], "discarded")
    b = store.ingest(b"Received: replay\n" + first, "message.eml", "message/rfc822")
    assert b["rid"] == a["rid"] and b["state"] == "discarded"


def test_html_presentation_changes_preserve_one_record(tmp_path, monkeypatch):
    monkeypatch.setenv("GROCERY_DATA", str(tmp_path))

    def html(style, amount="25,00"):
        msg = EmailMessage()
        msg["Message-ID"] = "<html-fixture@example.test>"
        msg["From"] = "store@example.test"
        msg.set_content(f'<div style="{style}">Example<br>TOTALT {amount} NOK</div>', subtype="html")
        return msg.as_bytes()

    first = store.ingest(html("color:black"), "message.eml", "message/rfc822")
    second = store.ingest(html("color:blue; padding:10px"), "message.eml", "message/rfc822")
    assert first["rid"] == second["rid"]
    changed = store.ingest(html("color:blue", "50,00"), "message.eml", "message/rfc822")
    assert changed["rid"] != first["rid"]


def test_concurrent_deliveries_have_one_parent(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setenv("GROCERY_DATA", str(tmp_path))
    raw = message()

    def ingest(n):
        return store.ingest(f"Received: hop {n}\n".encode() + raw, "message.eml", "message/rfc822")["rid"]

    with ThreadPoolExecutor(max_workers=3) as pool:
        ids = list(pool.map(ingest, range(3)))
    assert len(set(ids)) == 1
    assert archive.summary("inbox")["count"] == 2
