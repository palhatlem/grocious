#!/usr/bin/env python3
"""grocery.bauneveien.no — self-hosted grocery dashboard (Trumf + Rema).
Bonus balances, offers, and receipts with JSON/CSV/PDF download. Read-only.
Behind tinyauth; binds 127.0.0.1. Tokens/session read from /data."""
import json, os, io, csv, uuid, datetime, functools
import requests
from flask import Flask, Response, render_template_string, abort

DATA = os.environ.get("GROCERY_DATA", "/data")
REMA_PHONE = os.environ.get("REMA_PHONE", "")
app = Flask(__name__)

def _cache(ttl):
    def deco(fn):
        box = {"t": 0, "v": None}
        @functools.wraps(fn)
        def wrap(*a, **k):
            now = datetime.datetime.now().timestamp()
            if now - box["t"] > ttl or box["v"] is None:
                box["v"] = fn(*a, **k); box["t"] = now
            return box["v"]
        return wrap
    return deco

# ---------------- Trumf ----------------
def trumf_token():
    st = json.load(open(f"{DATA}/trumf_state.json"))
    s = requests.Session(); s.headers["User-Agent"] = "grocery"
    for c in st.get("cookies", []):
        if "trumf.no" in c.get("domain", ""):
            s.cookies.set(c["name"], c["value"], domain=c["domain"].lstrip("."), path=c.get("path", "/"))
    at = s.get("https://www.trumf.no/api/auth/session", timeout=20).json().get("accessToken")
    return at

@_cache(300)
def trumf_summary():
    try:
        h = {"Authorization": "Bearer " + trumf_token(), "Accept": "application/json"}
        B = "https://platform-rest-prod.ngdata.no"
        saldo = requests.get(f"{B}/trumf/husstand/saldo", headers=h, timeout=20).json()
        offers = requests.get(f"{B}/trumf/kampanjeavtale/beskrivelser", headers=h, timeout=20).json()
        return {"ok": True, "saldo": saldo.get("trumfSaldo"), "akkumulert": saldo.get("totaltAkkumulertTrumf"),
                "oppdatert": (saldo.get("sistOppdatert") or "")[:10],
                "offers": [{"tittel": o.get("visningsTekst"), "tekst": o.get("beskrivelse")}
                           for o in (offers if isinstance(offers, list) else [])]}
    except Exception as e:
        return {"ok": False, "err": str(e)}

# ---------------- Rema ----------------
def rema_headers():
    tok = json.load(open(f"{DATA}/rema_tokens.json"))
    r = requests.post("https://id.rema.no/token", data={"grant_type": "refresh_token",
        "client_id": "android-251010", "refresh_token": tok["refresh_token"]}, timeout=20).json()
    if "refresh_token" in r:
        json.dump(r, open(f"{DATA}/rema_tokens.json", "w"))
    return {"Authorization": "Bearer " + r["access_token"], "ocp-apim-subscription-key": "fb5e24884b504d0bad761098f77e6605",
            "x-platform": "android", "x-correlation-id": str(uuid.uuid4()), "x-device-id": str(uuid.uuid4()),
            "x-mobile-nr": REMA_PHONE, "x-app": "bella", "x-app-version": "3.0.12 #110549", "Accept": "application/json"}

@_cache(300)
def rema_receipts():
    try:
        H = rema_headers()
        heads = requests.get("https://api.rema.no/v1/bella/transaction/v2/heads", headers=H, timeout=30).json()
        offers = requests.get("https://api.rema.no/v1/bella/offers/v2/available-offers/", headers=H, timeout=20).json()
        olist = offers if isinstance(offers, list) else offers.get("offers", [])
        txs = []
        for t in heads.get("transactions", []):
            txs.append({"id": t["id"], "date": datetime.datetime.fromtimestamp(t["purchaseDate"]/1000).strftime("%Y-%m-%d %H:%M"),
                        "store": t.get("storeName"), "amount": t.get("amount"), "discount": t.get("discount", 0)})
        txs.sort(key=lambda x: x["date"], reverse=True)
        return {"ok": True, "purchaseTotal": heads.get("purchaseTotal"), "discountTotal": heads.get("discountTotal"),
                "count": len(txs), "receipts": txs, "offers": [{"desc": o.get("desc")} for o in olist]}
    except Exception as e:
        return {"ok": False, "err": str(e)}

def rema_lines(tid):
    H = rema_headers()
    rows = requests.get(f"https://api.rema.no/v1/bella/transaction/v2/rows/{tid}", headers=H, timeout=20).json()
    rows = rows if isinstance(rows, list) else rows.get("rows", [])
    out = []
    for r in rows:
        out.append({"name": r.get("productDescription") or r.get("prodtxt1"), "ean": r.get("prodtxt3"),
                    "qty": r.get("quantity", 1), "amount": r.get("amount"), "discount": r.get("discount", 0)})
    return out

# ---------------- routes ----------------
TPL = """<!doctype html><html lang=nb><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Grocery</title><style>
:root{--bg:#15171c;--card:#1e2129;--fg:#e6e8ec;--mut:#9aa0aa;--pos:#5fd08a;--neg:#e8735a;--acc:#7aa2f7}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
.wrap{max-width:960px;margin:0 auto;padding:20px}h1{font-size:20px}h2{font-size:16px;color:var(--mut);margin:24px 0 8px}
.cards{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:640px){.cards{grid-template-columns:1fr}}
.card{background:var(--card);border-radius:12px;padding:16px}.big{font-size:28px;font-weight:600}
.mut{color:var(--mut)}.pos{color:var(--pos)}.row{display:flex;justify-content:space-between;padding:3px 0}
table{width:100%;border-collapse:collapse;font-size:14px}td,th{text-align:left;padding:7px 8px;border-bottom:1px solid #2a2e37}
th{color:var(--mut);font-weight:500}a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline}
.dl a{margin-right:8px;font-size:12px}.tag{display:inline-block;background:#2a2e37;border-radius:6px;padding:1px 7px;font-size:12px;margin:2px 4px 2px 0}
.err{color:var(--neg)}</style></head><body><div class=wrap>
<h1>🛒 Grocery <span class=mut style="font-size:13px">· therack</span></h1>
<div class=cards>
 <div class=card><div class=mut>Trumf bonus</div>
  {% if t.ok %}<div class="big pos">{{ '%.2f'|format(t.saldo) }} kr</div>
   <div class=row><span class=mut>Akkumulert</span><span>{{ '%.0f'|format(t.akkumulert) }} kr</span></div>
   <div class=row><span class=mut>Kampanjer</span><span>{{ t.offers|length }}</span></div>
   <div class=row><span class=mut>Oppdatert</span><span>{{ t.oppdatert }}</span></div>
  {% else %}<div class=err>Trumf: {{ t.err }}</div>{% endif %}</div>
 <div class=card><div class=mut>Rema 1000</div>
  {% if r.ok %}<div class=big>{{ '%.0f'|format(r.purchaseTotal) }} kr</div>
   <div class=row><span class=mut>Rabatt spart</span><span class=pos>{{ '%.0f'|format(r.discountTotal) }} kr</span></div>
   <div class=row><span class=mut>Kvitteringer</span><span>{{ r.count }}</span></div>
   <div class=row><span class=mut>Tilbud</span><span>{{ r.offers|length }}</span></div>
  {% else %}<div class=err>Rema: {{ r.err }}</div>{% endif %}</div>
</div>
{% if t.ok and t.offers %}<h2>Trumf-kampanjer</h2>{% for o in t.offers %}<span class=tag title="{{o.tekst}}">{{ o.tittel }}</span>{% endfor %}{% endif %}
{% if r.ok %}<h2>Rema-kvitteringer <span class=mut style="font-size:12px">(siste {{ r.receipts|length }})</span></h2>
<table><tr><th>Dato</th><th>Butikk</th><th style="text-align:right">Beløp</th><th style="text-align:right">Rabatt</th><th>Last ned</th></tr>
{% for x in r.receipts %}<tr><td>{{ x.date }}</td><td>{{ x.store }}</td>
<td style="text-align:right">{{ '%.2f'|format(x.amount) }}</td>
<td style="text-align:right" class="{{ 'pos' if x.discount else 'mut' }}">{{ '%.2f'|format(x.discount or 0) }}</td>
<td class=dl><a href="/rema/receipt/{{x.id}}.json">json</a><a href="/rema/receipt/{{x.id}}.csv">csv</a><a href="/rema/receipt/{{x.id}}.pdf">pdf</a></td></tr>{% endfor %}
</table>{% endif %}
<p class=mut style="margin-top:28px;font-size:12px">Trumf-kvitteringer: endepunkt ikke wiret ennå · Coop: API edge-blokkert (se notat)</p>
</div></body></html>"""

@app.route("/")
def index():
    return render_template_string(TPL, t=trumf_summary(), r=rema_receipts())

@app.route("/rema/receipt/<int:tid>.<fmt>")
def rema_receipt(tid, fmt):
    lines = rema_lines(tid)
    if fmt == "json":
        return Response(json.dumps({"id": tid, "lines": lines}, ensure_ascii=False, indent=2),
                        mimetype="application/json", headers={"Content-Disposition": f"attachment;filename=rema-{tid}.json"})
    if fmt == "csv":
        buf = io.StringIO(); w = csv.writer(buf); w.writerow(["vare", "ean", "antall", "beløp", "rabatt"])
        for l in lines: w.writerow([l["name"], l["ean"], l["qty"], l["amount"], l["discount"]])
        return Response(buf.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment;filename=rema-{tid}.csv"})
    if fmt == "pdf":
        from reportlab.lib.pagesizes import A6
        from reportlab.pdfgen import canvas
        buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=A6); w, h = A6
        y = h - 30; c.setFont("Helvetica-Bold", 11); c.drawString(20, y, f"Rema 1000 — kvittering {tid}"); y -= 20
        c.setFont("Helvetica", 8); tot = 0
        for l in lines:
            if y < 30: c.showPage(); y = h - 30; c.setFont("Helvetica", 8)
            c.drawString(20, y, str(l["name"])[:34]); c.drawRightString(w-20, y, f"{l['amount']:.2f}"); y -= 12; tot += (l["amount"] or 0)
        y -= 6; c.setFont("Helvetica-Bold", 9); c.drawString(20, y, "Sum"); c.drawRightString(w-20, y, f"{tot:.2f}")
        c.showPage(); c.save(); buf.seek(0)
        return Response(buf.read(), mimetype="application/pdf", headers={"Content-Disposition": f"attachment;filename=rema-{tid}.pdf"})
    abort(404)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "3012")))
