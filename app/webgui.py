#!/usr/bin/env python3
"""grocious.bauneveien.no — self-hosted grocery dashboard (Trumf + Rema).
Bonus, offers/coupons (with manual activate), receipts + JSON/CSV/PDF export.
Read-only except opt-in Rema offer activation. Behind tinyauth; binds 127.0.0.1."""
import json, os, io, csv, re, uuid, datetime, functools
import requests
from flask import Flask, Response, render_template_string, redirect, abort

DATA = os.environ.get("GROCERY_DATA", "/data")
REMA_PHONE = os.environ.get("REMA_PHONE", "")
app = Flask(__name__)

def _cache(ttl):
    def deco(fn):
        box = {}
        @functools.wraps(fn)
        def wrap(*a):
            now = datetime.datetime.now().timestamp()
            if a not in box or now - box[a][0] > ttl:
                box[a] = (now, fn(*a))
            return box[a][1]
        wrap.clear = box.clear
        return wrap
    return deco

def _rsc_objects(txt, must_have):
    out = []
    for m in re.finditer('"' + must_have + '"', txt):
        start = txt.rfind("{", 0, m.start())
        if start < 0: continue
        depth = 0
        for j in range(start, min(start + 4000, len(txt))):
            if txt[j] == "{": depth += 1
            elif txt[j] == "}":
                depth -= 1
                if depth == 0:
                    try: out.append(json.loads(txt[start:j+1]))
                    except Exception: pass
                    break
    return out

# ---------------- Trumf ----------------
def trumf_session():
    st = json.load(open(f"{DATA}/trumf_state.json"))
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) Chrome/124.0 Safari/537.36"
    for c in st.get("cookies", []):
        if "trumf.no" in c.get("domain", ""):
            s.cookies.set(c["name"], c["value"], domain=c["domain"].lstrip("."), path=c.get("path", "/"))
    return s

@_cache(300)
def trumf_data():
    try:
        s = trumf_session()
        at = s.get("https://www.trumf.no/api/auth/session", timeout=20).json().get("accessToken")
        h = {"Authorization": "Bearer " + at, "Accept": "application/json"}
        B = "https://platform-rest-prod.ngdata.no"
        saldo = s.get(f"{B}/trumf/husstand/saldo", headers=h, timeout=20).json()
        offers = s.get(f"{B}/trumf/kampanjeavtale/beskrivelser", headers=h, timeout=20).json()
        txt = s.get("https://www.trumf.no/profil/kvitteringer", headers={"RSC": "1"}, timeout=25).content.decode("utf-8", "ignore")
        seen, recs = set(), []
        for o in _rsc_objects(txt, "batchId"):
            bid = o.get("batchId")
            if not bid or bid in seen or "belop" not in o: continue
            seen.add(bid)
            recs.append({"id": bid, "date": (o.get("bonusberegningTidspunkt") or "").replace("$D", "")[:10],
                         "store": o.get("beskrivelse"), "amount": o.get("belop"), "bonus": o.get("bonus"),
                         "chain": o.get("filterCategory"), "hasReceipt": o.get("harKvittering")})
        recs.sort(key=lambda x: x["date"], reverse=True)
        return {"ok": True, "saldo": saldo.get("trumfSaldo"), "akkumulert": saldo.get("totaltAkkumulertTrumf"),
                "oppdatert": (saldo.get("sistOppdatert") or "")[:10], "count": len(recs), "receipts": recs,
                "offers": [{"title": o.get("visningsTekst"), "desc": o.get("beskrivelse")}
                           for o in (offers if isinstance(offers, list) else [])]}
    except Exception as e:
        return {"ok": False, "err": str(e)}

def trumf_lines(bid):
    s = trumf_session()
    txt = s.get(f"https://www.trumf.no/profil/kvitteringer/{bid}", headers={"RSC": "1"}, timeout=25).content.decode("utf-8", "ignore")
    seen, out = set(), []
    for o in _rsc_objects(txt, "produktBeskrivelse"):
        g = o.get("varelinjeGuid")
        if g in seen: continue
        seen.add(g)
        ean = o.get("ean"); ean = None if ean == "$undefined" else ean
        out.append({"name": o.get("produktBeskrivelse"), "ean": ean, "qty": o.get("antall"), "amount": o.get("belop")})
    return out

# ---------------- Rema ----------------
def rema_headers():
    tok = json.load(open(f"{DATA}/rema_tokens.json"))
    r = requests.post("https://id.rema.no/token", data={"grant_type": "refresh_token",
        "client_id": "android-251010", "refresh_token": tok["refresh_token"]}, timeout=20).json()
    if "refresh_token" in r: json.dump(r, open(f"{DATA}/rema_tokens.json", "w"))
    return {"Authorization": "Bearer " + r["access_token"], "ocp-apim-subscription-key": "fb5e24884b504d0bad761098f77e6605",
            "x-platform": "android", "x-correlation-id": str(uuid.uuid4()), "x-device-id": str(uuid.uuid4()),
            "x-mobile-nr": REMA_PHONE, "x-app": "bella", "x-app-version": "3.0.12 #110549", "Accept": "application/json"}

@_cache(300)
def rema_data():
    try:
        H = rema_headers()
        heads = requests.get("https://api.rema.no/v1/bella/transaction/v2/heads", headers=H, timeout=30).json()
        offers = requests.get("https://api.rema.no/v1/bella/offers/v2/available-offers/", headers=H, timeout=20).json()
        olist = offers if isinstance(offers, list) else offers.get("offers", [])
        txs = [{"id": t["id"], "date": datetime.datetime.fromtimestamp(t["purchaseDate"]/1000).strftime("%Y-%m-%d %H:%M"),
                "store": t.get("storeName"), "amount": t.get("amount"), "discount": t.get("discount", 0)}
               for t in heads.get("transactions", [])]
        txs.sort(key=lambda x: x["date"], reverse=True)
        return {"ok": True, "purchaseTotal": heads.get("purchaseTotal"), "discountTotal": heads.get("discountTotal"),
                "count": len(txs), "receipts": txs,
                "offers": [{"code": o.get("code"), "desc": o.get("desc"), "activated": o.get("activated"),
                            "img": o.get("dutyText") if str(o.get("dutyText", "")).startswith("http") else None} for o in olist]}
    except Exception as e:
        return {"ok": False, "err": str(e)}

def rema_lines(tid):
    rows = requests.get(f"https://api.rema.no/v1/bella/transaction/v2/rows/{tid}", headers=rema_headers(), timeout=20).json()
    rows = rows if isinstance(rows, list) else rows.get("rows", [])
    return [{"name": r.get("productDescription") or r.get("prodtxt1"), "ean": r.get("prodtxt3"),
             "qty": r.get("quantity", 1), "amount": r.get("amount")} for r in rows]

def rema_activate(code):
    requests.post("https://api.rema.no/v1/bella/offers/activate", headers=rema_headers(), json=[code], timeout=20)

# ---------------- downloads ----------------
def _download(chain, rid, fmt, lines, title):
    if fmt == "json":
        return Response(json.dumps({"id": rid, "lines": lines}, ensure_ascii=False, indent=2),
                        mimetype="application/json", headers={"Content-Disposition": f"attachment;filename={chain}-{rid}.json"})
    if fmt == "csv":
        buf = io.StringIO(); w = csv.writer(buf); w.writerow(["vare", "ean", "antall", "beløp"])
        for l in lines: w.writerow([l["name"], l["ean"], l["qty"], l["amount"]])
        return Response(buf.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment;filename={chain}-{rid}.csv"})
    if fmt == "pdf":
        from reportlab.lib.pagesizes import A6
        from reportlab.pdfgen import canvas
        buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=A6); w, h = A6
        y = h - 30; c.setFont("Helvetica-Bold", 10); c.drawString(20, y, title[:44]); y -= 18
        c.setFont("Helvetica", 8); tot = 0
        for l in lines:
            if y < 26: c.showPage(); y = h - 30; c.setFont("Helvetica", 8)
            c.drawString(20, y, str(l["name"] or "")[:32]); c.drawRightString(w-20, y, f"{(l['amount'] or 0):.2f}")
            y -= 12; tot += (l["amount"] or 0)
        y -= 6; c.setFont("Helvetica-Bold", 9); c.drawString(20, y, "Sum"); c.drawRightString(w-20, y, f"{tot:.2f}")
        c.showPage(); c.save(); buf.seek(0)
        return Response(buf.read(), mimetype="application/pdf", headers={"Content-Disposition": f"attachment;filename={chain}-{rid}.pdf"})
    abort(404)

TPL = """<!doctype html><html lang=nb><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>grocious</title><style>
:root{--bg:#0f1116;--card:#1a1d26;--line:#262b36;--fg:#eceef2;--mut:#8b93a1;--pos:#5fd08a;--neg:#e8735a;
--trumf:#9b8cff;--rema:#4a90d9}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,-apple-system,sans-serif}
.wrap{max-width:1040px;margin:0 auto;padding:0 20px 48px}
header{background:linear-gradient(120deg,#1c1740,#132033 60%,#0f1116);border-radius:0 0 20px 20px;padding:26px 24px 22px;margin:0 -20px 24px}
.brand{font-size:26px;font-weight:700;letter-spacing:-.5px}.brand .cart{filter:drop-shadow(0 2px 6px #0006)}
.tag-line{color:var(--mut);font-size:13px;margin-top:2px}
h2{font-size:14px;text-transform:uppercase;letter-spacing:.5px;color:var(--mut);margin:30px 0 12px;font-weight:600}
.cards{display:grid;grid-template-columns:1fr 1fr;gap:16px}@media(max-width:640px){.cards{grid-template-columns:1fr}}
.stat{background:var(--card);border-radius:16px;padding:18px 20px;border-left:4px solid var(--line);box-shadow:0 1px 0 #ffffff08 inset}
.stat.trumf{border-left-color:var(--trumf)}.stat.rema{border-left-color:var(--rema)}
.stat .name{font-weight:600;font-size:13px;color:var(--mut);text-transform:uppercase;letter-spacing:.4px}
.big{font-size:32px;font-weight:700;margin:4px 0 6px}.row{display:flex;justify-content:space-between;padding:2px 0;font-size:14px}
.mut{color:var(--mut)}.pos{color:var(--pos)}.rt{text-align:right}
.offers{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px}
.offer{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden;display:flex;flex-direction:column}
.offer img{width:100%;height:120px;object-fit:cover;background:#0c0e13}
.offer .b{padding:12px 13px;display:flex;flex-direction:column;gap:8px;flex:1}
.badge{align-self:flex-start;font-size:11px;font-weight:600;padding:2px 8px;border-radius:20px}
.badge.trumf{background:#2a2350;color:#c3b8ff}.badge.rema{background:#173049;color:#9fc7ef}
.offer .t{font-size:14px;font-weight:500;line-height:1.35;flex:1}
.btn{border:0;border-radius:9px;padding:8px 12px;font-weight:600;font-size:13px;cursor:pointer;background:var(--rema);color:#fff}
.btn:hover{filter:brightness(1.1)}.done{color:var(--pos);font-size:13px;font-weight:600}
table{width:100%;border-collapse:collapse;font-size:14px}td,th{text-align:left;padding:8px 9px;border-bottom:1px solid var(--line)}
th{color:var(--mut);font-weight:500}tr:hover td{background:#ffffff05}
a{color:#7aa2f7;text-decoration:none}a:hover{text-decoration:underline}
.dl a{margin-right:9px;font-size:12px}
details{background:var(--card);border:1px solid var(--line);border-radius:14px;margin-bottom:14px;overflow:hidden}
summary{padding:14px 18px;cursor:pointer;font-weight:600;list-style:none}summary::-webkit-details-marker{display:none}
summary::before{content:"▸ ";color:var(--mut)}details[open] summary::before{content:"▾ "}
details .inner{padding:0 8px 8px}.err{color:var(--neg)}.pill{display:inline-block;background:var(--line);border-radius:20px;padding:1px 9px;font-size:12px;color:var(--mut);margin-left:6px}
</style></head><body>
<header><div class=wrap style="padding:0"><div class=brand><span class=cart>🛒</span> grocious</div>
<div class=tag-line>dagligvarebonus &amp; kvitteringer · therack</div></div></header>
<div class=wrap>
<div class=cards>
 <div class="stat trumf"><div class=name>Trumf</div>
  {% if t.ok %}<div class="big pos">{{ '%.2f'|format(t.saldo) }} kr</div>
   <div class=row><span class=mut>Akkumulert</span><span>{{ '%.0f'|format(t.akkumulert) }} kr</span></div>
   <div class=row><span class=mut>Kvitteringer</span><span>{{ t.count }}</span></div>
   <div class=row><span class=mut>Kampanjer</span><span>{{ t.offers|length }}</span></div>
  {% else %}<div class=err>{{ t.err }}</div>{% endif %}</div>
 <div class="stat rema"><div class=name>Rema 1000</div>
  {% if r.ok %}<div class=big>{{ '%.0f'|format(r.purchaseTotal) }} kr</div>
   <div class=row><span class=mut>Rabatt spart</span><span class=pos>{{ '%.0f'|format(r.discountTotal) }} kr</span></div>
   <div class=row><span class=mut>Kvitteringer</span><span>{{ r.count }}</span></div>
   <div class=row><span class=mut>Tilbud</span><span>{{ r.offers|length }}</span></div>
  {% else %}<div class=err>{{ r.err }}</div>{% endif %}</div>
</div>

<h2>Tilbud &amp; kuponger <span class=pill>aktiver de du vil selv</span></h2>
<div class=offers>
{% if r.ok %}{% for o in r.offers %}<div class=offer>
  {% if o.img %}<img src="{{o.img}}" loading=lazy onerror="this.style.display='none'">{% endif %}
  <div class=b><span class="badge rema">Rema</span><div class=t>{{ o.desc }}</div>
   {% if o.activated %}<span class=done>✓ Aktivert</span>
   {% else %}<form method=post action="/rema/offer/{{o.code}}/activate" style=margin:0><button class=btn>Aktiver</button></form>{% endif %}
  </div></div>{% endfor %}{% endif %}
{% if t.ok %}{% for o in t.offers %}<div class=offer><div class=b><span class="badge trumf">Trumf</span>
  <div class=t><b>{{ o.title }}</b><br><span class=mut style=font-size:13px>{{ o.desc }}</span></div></div></div>{% endfor %}{% endif %}
</div>

<h2>Kvitteringer</h2>
{% if t.ok and t.receipts %}<details open><summary>Trumf <span class=pill>{{ t.receipts|length }}</span></summary><div class=inner>
<table><tr><th>Dato</th><th>Butikk</th><th class=rt>Beløp</th><th class=rt>Bonus</th><th>Last ned</th></tr>
{% for x in t.receipts %}<tr><td>{{ x.date }}</td><td>{{ x.store }}</td><td class=rt>{{ '%.2f'|format(x.amount) }}</td>
<td class="rt pos">{{ '%.2f'|format(x.bonus or 0) }}</td><td class=dl>{% if x.hasReceipt %}<a href="/trumf/receipt/{{x.id}}.json">json</a><a href="/trumf/receipt/{{x.id}}.csv">csv</a><a href="/trumf/receipt/{{x.id}}.pdf">pdf</a>{% else %}<span class=mut>—</span>{% endif %}</td></tr>{% endfor %}
</table></div></details>{% endif %}
{% if r.ok %}<details><summary>Rema 1000 <span class=pill>{{ r.receipts|length }}</span></summary><div class=inner>
<table><tr><th>Dato</th><th>Butikk</th><th class=rt>Beløp</th><th class=rt>Rabatt</th><th>Last ned</th></tr>
{% for x in r.receipts %}<tr><td>{{ x.date }}</td><td>{{ x.store }}</td><td class=rt>{{ '%.2f'|format(x.amount) }}</td>
<td class="rt {{ 'pos' if x.discount else 'mut' }}">{{ '%.2f'|format(x.discount or 0) }}</td>
<td class=dl><a href="/rema/receipt/{{x.id}}.json">json</a><a href="/rema/receipt/{{x.id}}.csv">csv</a><a href="/rema/receipt/{{x.id}}.pdf">pdf</a></td></tr>{% endfor %}
</table></div></details>{% endif %}
<p class=mut style="margin-top:26px;font-size:12px">Coop: API edge-blokkert (kun innlogging mulig) · data caches 5 min</p>
</div></body></html>"""

@app.route("/")
def index():
    return render_template_string(TPL, t=trumf_data(), r=rema_data())

@app.route("/rema/offer/<code>/activate", methods=["POST"])
def rema_offer_activate(code):
    rema_activate(code); rema_data.clear()
    return redirect("/")

@app.route("/trumf/receipt/<bid>.<fmt>")
def trumf_receipt(bid, fmt):
    return _download("trumf", bid, fmt, trumf_lines(bid), f"Trumf kvittering {bid[:10]}")

@app.route("/rema/receipt/<int:tid>.<fmt>")
def rema_receipt(tid, fmt):
    return _download("rema", tid, fmt, rema_lines(tid), f"Rema 1000 — {tid}")

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "3012")))
