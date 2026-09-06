"""Every route and export format, in demo mode (fixtures, no tokens, no network)."""

import csv
import io
import json

import themes


def test_index_renders_everything(client):
    html = client.get("/").get_data(as_text=True)
    assert "grocious" in html and "DEMO" in html
    assert 'id="theme"' in html and "Catppuccin Mocha" in html and 'value="auto"' in html
    assert "Tilbud &amp; kuponger" in html and "Aktiver" in html and "✓ Aktivert" in html
    assert 'data-chain="trumf"' in html and 'data-chain="rema"' in html
    assert '<option value="2026-06">jun 2026</option>' in html
    assert "412,37\u00a0kr" in html  # NOK format as in Porteføljen (nbsp before kr)
    assert "<style>" not in html  # no inline CSS left


def test_index_survives_failed_sources(client, monkeypatch):
    import webgui

    monkeypatch.setattr(webgui, "trumf_data", lambda: {"ok": False, "err": "cookie expired"})
    monkeypatch.setattr(webgui, "rema_data", lambda: {"ok": False, "err": "401"})
    html = client.get("/").get_data(as_text=True)
    assert html.count("Kunne ikke oppdatere live-data. Arkiverte kjøp vises.") == 2
    assert "Ingen tilbud" in html


def test_themes_css_and_files(client):
    css = client.get("/themes.css").get_data(as_text=True)
    ids = [t["id"] for t in themes.load_themes()]
    assert ids[:5] == ["light", "dark", "gruvbox", "catppuccin-mocha", "ink"]
    assert css.startswith("/* generated") and ":root{color-scheme:light;" in css
    assert "@media (prefers-color-scheme: dark){:root:not([data-theme]){color-scheme:dark;" in css
    for i in ids:
        assert f'html[data-theme="{i}"]{{' in css
    assert all(f"--{k}:" in css for k in themes.COLOR_KEYS)


def test_new_theme_file_is_picked_up(client, tmp_path, monkeypatch):
    monkeypatch.setattr(themes, "THEMES_DIR", tmp_path)
    (tmp_path / "solarized.json").write_text(
        '{"label": "Solarized", "scheme": "light", "colors": {"bg": "#fdf6e3", "accent": "#268bd2"}}'
    )
    (tmp_path / "dark.json").write_text('{"scheme": "dark", "colors": {"bg": "#000"}}')
    ts = themes.load_themes()
    assert [t["id"] for t in ts] == ["dark", "solarized"]
    css = themes.render_css(ts)
    assert 'html[data-theme="solarized"]{color-scheme:light;' in css and "--bg:#fdf6e3;" in css
    assert "Solarized" in client.get("/").get_data(as_text=True)


def test_api_summary_shape_unchanged(client):
    d = client.get("/api/summary").get_json()
    assert set(d) == {"trumf", "rema", "coop"}
    assert d["trumf"]["ok"] and set(d["trumf"]) >= {"saldo", "akkumulert", "oppdatert", "count", "receipts", "offers"}
    assert set(d["trumf"]["receipts"][0]) == {"id", "date", "store", "amount", "bonus", "chain", "hasReceipt"}
    assert set(d["rema"]) >= {"purchaseTotal", "discountTotal", "count", "receipts", "offers"}
    assert set(d["rema"]["receipts"][0]) == {"id", "date", "store", "amount", "discount"}
    assert set(d["rema"]["offers"][0]) == {"code", "desc", "activated", "img"}


def test_api_export_json_and_csv(client):
    d = client.get("/api/export/2026-06.json").get_json()
    assert set(d) == {"month", "count", "total", "bonus", "discount", "receipts"} and d["count"] > 0
    assert all(x["date"].startswith("2026-06") for x in d["receipts"])
    assert set(d["receipts"][0]) == {"chain", "id", "date", "store", "amount", "bonus", "discount"}
    with_lines = client.get("/api/export/2026-06.json?lines=1").get_json()
    assert all("lines" in x for x in with_lines["receipts"] if x["chain"] == "rema")
    r = client.get("/api/export/2026-06.csv")
    rows = list(csv.reader(io.StringIO(r.get_data(as_text=True))))
    assert (
        rows[0] == ["chain", "receipt_id", "date", "store", "amount", "bonus", "discount"]
        and len(rows) == d["count"] + 1
    )
    rows = list(csv.reader(io.StringIO(client.get("/api/export/2026-06.csv?lines=1").get_data(as_text=True))))
    assert rows[0] == ["chain", "receipt_id", "date", "store", "item", "ean", "qty", "amount"]
    assert client.get("/api/export/2026-6.json").status_code == 404
    assert client.get("/api/export/2026-06.pdf").status_code == 404


def test_receipt_exports(client):
    j = client.get("/trumf/receipt/demo-trumf-001.json")
    assert j.status_code == 200 and j.headers["Content-Disposition"].endswith("trumf-demo-trumf-001.json")
    d = json.loads(j.get_data(as_text=True))
    assert d["id"] == "demo-trumf-001" and set(d["lines"][0]) == {"name", "ean", "qty", "amount"}
    c = client.get("/rema/receipt/900100.csv")
    assert c.status_code == 200 and c.get_data(as_text=True).splitlines()[0] == "vare,ean,antall,beløp"
    p = client.get("/rema/receipt/900100.pdf")
    assert p.status_code == 200 and p.data.startswith(b"%PDF") and p.mimetype == "application/pdf"
    assert client.get("/rema/receipt/900100.xml").status_code == 404
    assert client.get("/rema/receipt/abc.json").status_code == 404


def test_rema_activate_redirects_and_flips(client):
    offers = lambda: client.get("/api/summary").get_json()["rema"]["offers"]
    assert not next(o for o in offers() if o["code"] == "DEMO-LAKS")["activated"]
    r = client.post("/rema/offer/DEMO-LAKS/activate")
    assert r.status_code == 302 and r.headers["Location"].endswith("/")
    assert next(o for o in offers() if o["code"] == "DEMO-LAKS")["activated"]


def test_static_assets_and_no_cdn(client):
    css = client.get("/static/style.css").get_data(as_text=True)
    js = client.get("/static/app.js").get_data(as_text=True)
    head = client.get("/").get_data(as_text=True).split("<main")[0]
    assert "var(--bg)" in css and "grocious.theme" in js
    assert "http://" not in css and "https://" not in js and 'src="http' not in head and 'href="http' not in head


def test_nok_filters():
    import ui

    nb = "\u00a0"
    assert ui.nok(1234.5, 2) == f"1{nb}234,50{nb}kr" and ui.nok(0) == f"0{nb}kr" and ui.nok(None) == "–"
    assert ui.day("2026-09-04") == "04.09.2026" and ui.dt("2026-09-04 18:12") == "04.09.2026 18:12"
    assert ui.month_label("2026-06") == "jun 2026"
