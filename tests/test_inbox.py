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


def test_pwa(client):
    response = client.get("/manifest.webmanifest")
    assert response.mimetype == "application/manifest+json"
    assert response.json["share_target"]["action"] == "/inbox"
    assert {i["sizes"] for i in response.json["icons"]} == {"192x192", "512x512"}
    assert b"caches." not in client.get("/sw.js").data


def test_interpretations(client, inbox_data, monkeypatch):
    from inbox import llm
    import copy
    import json

    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GROCIOUS_LLM_LITELLM_URL"):
        monkeypatch.delenv(key, raising=False)
    assert [p["id"] for p in llm.providers() if p["available"]] == ["none"]
    rid = store.ingest(b"KIWI Test\n07.09.2026\nTOTALT 42,00 NOK")["rid"]
    original = (archive.folder("inbox", rid) / "receipt.json").read_bytes()

    class Fake:
        id, label, vision, available, model = "fake", "Fake", False, True, "fixture"

        def interpret(self, **kwargs):
            parsed = {k: None for k in llm.SCHEMA["properties"]}
            parsed.update(store="KIWI Test", total=99.0, currency="NOK", date="2026-09-07")
            return dict(parsed=copy.deepcopy(parsed), raw={"parsed": parsed}, input_tokens=1, output_tokens=2)

    monkeypatch.setitem(llm.REGISTRY, "fake", Fake())
    response = client.post(f"/inbox/{rid}/interpret", json={"provider": "fake"})
    assert response.status_code == 200, response.json
    assert "llm_total_not_in_text" in archive.read_receipt("inbox", rid)["validation"]["issues"]
    store.correct(rid, {"note": "Check"})
    assert "llm_total_not_in_text" in archive.read_receipt("inbox", rid)["validation"]["issues"]
    llm.run(rid, "none")
    assert len(llm.history(rid)) == 2
    assert archive.read_receipt("inbox", rid)["amount_minor"] == 4200
    llm.select(rid, 1)
    assert archive.read_receipt("inbox", rid)["amount_minor"] == 9900
    assert (archive.folder("inbox", rid) / "receipt.json").read_bytes() == original
    assert (
        json.loads((archive.folder("inbox", rid) / "interpretation-1.json").read_text())["request"]["image_sha256"]
        == []
    )


def test_mail_ingest(inbox_data):
    from inbox import mailworker
    from email.message import EmailMessage
    from unittest.mock import Mock

    msg = EmailMessage()
    msg["From"] = "shop@example.com"
    msg.set_content("Synthetic mail")
    msg.add_attachment(
        b"KIWI Demo\n07.09.2026\nTOTALT 22,00 NOK", maintype="text", subtype="plain", filename="receipt.txt"
    )
    client = Mock()
    result = mailworker.process_message(client, 12, msg.as_bytes())
    assert len(result["children"]) == 1
    client.move.assert_called_once_with([12], "Grocious/Done")
    assert archive.read_receipt("inbox", result["children"][0])["intake"]["parent"] == result["rid"]
    again = mailworker.process_message(client, 12, msg.as_bytes())
    assert again["duplicate"]


def test_link_survives_provider_refresh(client, inbox_data):
    from inbox import linking, llm

    rid = store.ingest(b"KIWI Test\n07.09.2026\nTOTALT 42,00 NOK")["rid"]
    target = archive.key("trumf", "demo-target")
    directory = archive.folder("trumf", target)
    raw = dict(archive.read_receipt("inbox", rid), archive_id=target, id="demo-target", documents=[])
    archive.atomic_json(directory / "receipt.json", raw)
    archive.rebuild("trumf")
    assert linking.candidates(rid)[0]["exact"]
    linking.link(rid, "trumf", target)
    linking.link(rid, "trumf", target)
    assert not store.exports("2026-09")
    archive.atomic_json(directory / "receipt.json", raw)  # normal fetcher refresh
    linked = archive.read_receipt("trumf", target)
    assert linked["linked_from"] == [rid]
    assert len(linked["documents"]) == 1
    archive.document("trumf", target, linked["documents"][0]["filename"])
    for action in (
        lambda: store.correct(rid, {"amount": 42}),
        lambda: store.state(rid, "confirmed"),
        lambda: llm.run(rid, "none"),
    ):
        with pytest.raises(ValueError):
            action()


def test_thumbnail(client, inbox_data):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (320, 800), "white").save(buf, "PNG")
    rid = store.ingest(buf.getvalue(), "test.png", "image/png")["rid"]
    response = client.get(f"/inbox/{rid}/thumbnail")
    assert response.status_code == 200
    assert response.mimetype == "image/jpeg"
    with Image.open(io.BytesIO(response.data)) as preview:
        assert preview.width <= 180 and preview.height <= 240


def test_sdk_requests_only_receipt_context(inbox_data, monkeypatch):
    from inbox import llm
    from types import SimpleNamespace
    from unittest.mock import Mock
    import sys
    import json

    parsed = {k: None for k in llm.SCHEMA["properties"]}
    response = SimpleNamespace(
        status="completed",
        output_text=json.dumps(parsed),
        usage=SimpleNamespace(input_tokens=3, output_tokens=4),
        model_dump=lambda **kwargs: {"output": "fixture"},
    )
    create = Mock(return_value=response)
    constructor = Mock(return_value=SimpleNamespace(responses=SimpleNamespace(create=create)))
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=constructor))
    result = llm.OpenAI().interpret(text="synthetic receipt", image=[(b"image", "image/jpeg")], mimetype=None, hints={})
    assert result["parsed"] == parsed
    request = create.call_args.kwargs
    assert request["store"] is False and "tools" not in request
    assert request["text"]["format"]["schema"] == llm.SCHEMA
    assert request["input"][0]["content"][1]["type"] == "input_image"
    assert constructor.call_args.kwargs["max_retries"] == 0
    response = SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text=json.dumps(parsed))],
        usage=SimpleNamespace(input_tokens=3, output_tokens=4),
        model_dump=lambda **kwargs: {"output": "fixture"},
    )
    create = Mock(return_value=response)
    monkeypatch.setitem(
        sys.modules,
        "anthropic",
        SimpleNamespace(Anthropic=Mock(return_value=SimpleNamespace(messages=SimpleNamespace(create=create)))),
    )
    llm.Claude().interpret(text="synthetic", image=[(b"image", "image/jpeg")], mimetype=None, hints={})
    assert create.call_args.kwargs["output_config"]["format"]["schema"] == llm.SCHEMA
    assert create.call_args.kwargs["messages"][0]["content"][1]["source"]["media_type"] == "image/jpeg"
