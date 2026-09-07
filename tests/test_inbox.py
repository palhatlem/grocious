import io
import pytest
import receipt_archive as archive
from inbox import store
from inbox.extract import extract
from inbox.heuristics import parse


@pytest.fixture
def inbox_data(tmp_path, monkeypatch):
    monkeypatch.setenv("GROCERY_DATA", str(tmp_path))
    return tmp_path


@pytest.mark.parametrize(
    "name", ["KIWI Test", "REMA 1000 Test", "Coop Extra Test", "Vinmonopolet Test", "Apotek 1 Test", "Restaurant Test"]
)
def test_rules(name):
    r = parse(name + "\n07.09.2026 12:35\nVare 20,50\nPANT 2,00\nÅ BETALE 22,50 kr")
    assert r["store"] == name
    assert r["date"] == "2026-09-07"
    assert r["total"] == 22.5
    assert r["lines"][1]["kind"] == "deposit"


def test_intake_overlay_and_idempotency(inbox_data):
    raw = b"KIWI Test\n07.09.2026\nVare 20,50\nTOTALT 20,50 NOK"
    a = store.ingest(raw)
    b = store.ingest(raw)
    assert a["rid"] == b["rid"] and b["duplicate"]
    path = archive.folder("inbox", a["rid"]) / "receipt.json"
    original = path.read_bytes()
    store.correct(a["rid"], {"store": "Rettet", "amount": "25,50"})
    assert path.read_bytes() == original
    r = archive.read_receipt("inbox", a["rid"])
    assert r["amount_minor"] == 2550 and r["store"] == "Rettet"
    assert archive.summary("inbox")["receipts"][0]["amount"] == 25.5
    for d in r["documents"]:
        archive.document("inbox", a["rid"], d["filename"])


def test_html_and_mail(inbox_data):
    from email.message import EmailMessage

    msg = EmailMessage()
    msg.set_content("Kvittering vedlagt")
    msg.add_alternative("<b>HTML body</b><script>alert(1)</script>", subtype="html")
    msg.add_attachment(b"KIWI Test\nSUM 42,00", maintype="text", subtype="plain", filename="receipt.txt")
    result = store.ingest(msg.as_bytes(), "mail.eml", "message/rfc822")
    assert len(result["children"]) == 1
    child = archive.read_receipt("inbox", result["children"][0])
    assert child["intake"]["parent"] == result["rid"]
    assert extract(b"<h1>Butikk</h1>", "receipt.html")["kind"] == "html"


def test_image_and_pdf():
    from PIL import Image
    from reportlab.pdfgen.canvas import Canvas

    image = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(image, "JPEG")
    result = extract(image.getvalue(), "photo.jpg")
    assert result["kind"] == "image" and result["derived"]
    pdf = io.BytesIO()
    c = Canvas(pdf)
    c.drawString(30, 750, "KIWI Testbutikk 07.09.2026 Vare 42,00 TOTALT 42,00 NOK")
    c.save()
    assert extract(pdf.getvalue(), "text.pdf")["kind"] == "pdf-text"
    pdf = io.BytesIO()
    c = Canvas(pdf)
    c.rect(10, 10, 20, 20)
    c.showPage()
    c.save()
    assert extract(pdf.getvalue(), "scan.pdf")["kind"] == "pdf-scan"


def test_routes_states_exports(client, inbox_data):
    response = client.post(
        "/inbox",
        data={"files": (io.BytesIO(b"KIWI Test\n07.09.2026\nTOTALT 42,00 NOK"), "x.txt")},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 201
    rid = response.json[0]["rid"]
    assert client.get("/inbox/" + rid).status_code == 200
    assert client.get("/inbox").status_code == 200
    assert client.post("/inbox/" + rid + "/state", json={"state": "confirmed"}).status_code == 200
    assert store.exports("2026-09")[0]["review_state"] == "confirmed"
    assert client.post("/inbox/" + rid + "/state", json={"state": "discarded"}).status_code == 200
    assert not store.exports("2026-09")
    assert client.get("/inbox/" + rid + ".pdf").status_code == 200
    assert client.get("/inbox/" + rid + ".csv").status_code == 200


def test_invalid_file_and_corrections(client, inbox_data):
    assert client.post("/inbox", data={"files": (io.BytesIO(b"not image"), "x.png")}).status_code == 400
    rid = store.ingest(b"Unknown receipt")["rid"]
    assert client.post("/inbox/" + rid + "/state", json={"state": "confirmed"}).status_code == 400
    assert client.post("/inbox/" + rid + "/corrections", json={"amount": "NaN"}).status_code == 400
    assert client.post("/inbox/" + rid + "/corrections", json={"documents": []}).status_code == 400
    assert client.get("/inbox/not-a-hash").status_code == 404
