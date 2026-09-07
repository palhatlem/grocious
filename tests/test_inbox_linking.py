from email.message import EmailMessage
import io
import zipfile

import pytest
import receipt_archive as archive
from inbox import linking, store


@pytest.fixture
def pair(tmp_path, monkeypatch):
    monkeypatch.setenv("GROCERY_DATA", str(tmp_path))
    monkeypatch.setenv("GROCIOUS_LLM_AUTO", "0")
    msg = EmailMessage()
    msg.set_content("Example\n07.09.2026\nTOTALT 42,00 NOK")
    msg.add_attachment(
        b"Example invoice\n07.09.2026\nTOTALT 42,00 NOK", maintype="text", subtype="plain", filename="invoice.txt"
    )
    result = store.ingest(msg.as_bytes(), "mail.eml", "message/rfc822")
    ids = result["rid"], result["children"][0]
    for rid in ids:
        store.correct(rid, {"store": "Example", "date": "2026-09-07", "amount": "42", "currency": "NOK"})
        store.state(rid, "confirmed")
    return ids


def test_manual_inbox_link_preserves_originals_and_single_export(client, pair):
    mail, invoice = pair
    before = {rid: (archive.folder("inbox", rid) / "receipt.json").read_bytes() for rid in pair}
    assert linking.candidates(mail)[0]["archive_id"] == invoice
    assert linking.candidates(invoice)[0]["related"]
    page = client.get("/inbox/" + mail)
    assert page.status_code == 200
    assert "Begge er bekreftet" in page.text
    assert len(store.exports("2026-09")) == 2  # suggestions do not change anything
    response = client.post("/inbox/" + mail + "/link", data={"source": "inbox", "target": invoice})
    assert response.status_code == 303 and response.location == "/inbox/" + invoice
    linking.link(mail, "inbox", invoice)  # retry is idempotent
    primary = archive.read_receipt("inbox", invoice)
    assert primary["review"]["state"] == "confirmed"
    assert primary["amount_minor"] == 4200
    assert primary["linked_from"] == [mail]
    assert len([d for d in primary["documents"] if d["role"] == "user-upload"]) == 1
    for rid in pair:
        assert (archive.folder("inbox", rid) / "receipt.json").read_bytes() == before[rid]
        for doc in archive.read_receipt("inbox", rid)["documents"]:
            archive.document("inbox", rid, doc["filename"])
    assert [r["archive_id"] for r in store.exports("2026-09")] == [invoice]
    for fmt in ("json", "csv"):
        exported = client.get("/api/export/2026-09." + fmt)
        assert exported.status_code == 200
        assert invoice in exported.text and mail not in exported.text
    zipped = client.get("/inbox/" + invoice + ".zip")
    assert zipped.status_code == 200
    with zipfile.ZipFile(io.BytesIO(zipped.data)) as bundle:
        for doc in primary["documents"]:
            assert any(name.endswith(doc["filename"]) for name in bundle.namelist())
    assert client.get("/inbox/" + invoice).status_code == 200
    assert "hovedposten" in client.get("/inbox/" + mail).text


def test_link_graph_guards(pair):
    mail, invoice = pair
    with pytest.raises(ValueError):
        linking.link(mail, "inbox", mail)
    store.state(invoice, "discarded")
    assert not linking.candidates(mail)
    with pytest.raises(ValueError):
        linking.link(mail, "inbox", invoice)
    store.state(invoice, "needs_review")
    linking.link(mail, "inbox", invoice)
    assert archive.read_receipt("inbox", invoice)["review"]["state"] == "needs_review"
    with pytest.raises(ValueError):
        linking.link(invoice, "inbox", mail)
    third = store.ingest(b"Other\n07.09.2026\nTOTALT 42,00 NOK")["rid"]
    with pytest.raises(ValueError):
        linking.link(invoice, "inbox", third)
    with pytest.raises(ValueError):
        linking.link(third, "inbox", mail)
    assert mail not in [r["archive_id"] for r in linking.candidates(third)]


def test_parent_candidates_without_date_or_amount(pair):
    mail, invoice = pair
    store.correct(mail, {"date": None, "amount": None})
    candidates = linking.candidates(mail)
    assert len(candidates) == 1
    assert candidates[0]["archive_id"] == invoice and candidates[0]["related"]
