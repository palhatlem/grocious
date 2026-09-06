#!/usr/bin/env python3
"""grocious.bauneveien.no — self-hosted grocery dashboard (Trumf + Rema).
Bonus, offers/coupons (with manual activate), receipts + JSON/CSV/PDF export.
Read-only except opt-in Rema offer activation. Behind tinyauth; binds 127.0.0.1."""
import json, os, io, csv, re, uuid, datetime, functools
import requests
from flask import Flask, Response, render_template_string, redirect, abort, request, jsonify, send_file
import receipt_archive

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
 <div class="stat" style="border-top:3px solid #46b5d1"><div class=name>Coop</div>
  <div class=big>{{ c.count }} kvitteringer</div>
  <div class=row><span class=mut>Original-PDF-er</span><span>{{ c.status.get('original_pdf_count', c.count) }}</span></div>
  <div class=row><span class=mut>Arkiv</span><span>{{ c.status.get('state', 'not_started') }}</span></div>
  {% if c.status.get('oldest_date') %}<div class=mut>{{c.status.oldest_date}} – {{c.status.newest_date}}</div>{% endif %}
 </div>
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
<p><a href="/archive/trumf">Trumf-arkiv: originalbilder og rådata</a> · <a href="/archive/rema">Rema-arkiv: komplette rådata</a></p>
{% if t.ok and t.receipts %}<details><summary>Trumf <span class=pill>{{ t.receipts|length }}</span></summary><div class=inner>
<table><tr><th>Dato</th><th>Butikk</th><th class=rt>Beløp</th><th class=rt>Bonus</th><th>Last ned</th></tr>
{% for x in t.receipts %}<tr><td>{{ x.date }}</td><td>{{ x.store }}</td><td class=rt>{{ '%.2f'|format(x.amount) }}</td>
<td class="rt pos">{{ '%.2f'|format(x.bonus or 0) }}</td><td class=dl>{% if x.hasReceipt %}<a href="/trumf/receipt/{{x.id}}.json">json</a><a href="/trumf/receipt/{{x.id}}.csv">csv</a><a href="/trumf/receipt/{{x.id}}.pdf">laget PDF</a>{% else %}<span class=mut>—</span>{% endif %}</td></tr>{% endfor %}
</table></div></details>{% endif %}
{% if r.ok %}<details><summary>Rema 1000 <span class=pill>{{ r.receipts|length }}</span></summary><div class=inner>
<table><tr><th>Dato</th><th>Butikk</th><th class=rt>Beløp</th><th class=rt>Rabatt</th><th>Last ned</th></tr>
{% for x in r.receipts %}<tr><td>{{ x.date }}</td><td>{{ x.store }}</td><td class=rt>{{ '%.2f'|format(x.amount) }}</td>
<td class="rt {{ 'pos' if x.discount else 'mut' }}">{{ '%.2f'|format(x.discount or 0) }}</td>
<td class=dl><a href="/rema/receipt/{{x.id}}.json">json</a><a href="/rema/receipt/{{x.id}}.csv">csv</a><a href="/rema/receipt/{{x.id}}.pdf">laget PDF</a></td></tr>{% endfor %}
</table></div></details>{% endif %}
{% if c.ok %}<details><summary>Coop <span class=pill>{{c.count}}</span></summary><div class=inner>
<p class=mut>Originale Coop-PDF-er og komplette kildedata er bevart i arkivet.</p>
{% if c.status.get('errors') %}<p class=err>{{c.status.errors|length}} importavvik – se <a href="/api/coop/status">status</a>.</p>{% endif %}
<table><tr><th>Dato</th><th>Butikk</th><th class=rt>Beløp</th><th>Kvittering</th></tr>
{% for x in c.receipts %}<tr><td>{{x.date}} {{x.time or ''}}</td><td>{{x.store}}</td><td class=rt>{{'%.2f'|format(x.amount or 0)}}</td>
<td class=dl><a href="/coop/receipt/{{x.archive_id}}">Detaljer</a><a href="/coop/receipt/{{x.archive_id}}.pdf">Original PDF</a><a href="/coop/receipt/{{x.archive_id}}.json">JSON</a><a href="/coop/receipt/{{x.archive_id}}.csv">CSV</a>
{% if x.validation.issues %}<span class=mut>Kontrollavvik</span>{% endif %}</td></tr>{% endfor %}</table>
</div></details>{% endif %}
<p class=mut style="margin-top:26px;font-size:12px">Live oversikter caches 5 min · Kvitteringsarkiv lagres lokalt · <a href="/api/coop/status">importstatus</a></p>
</div></body></html>"""

@app.route("/")
def index():
    return render_template_string(TPL, t=trumf_data(), r=rema_data(), c=receipt_archive.summary('coop'))

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

# ---------------- machine API (agents / bookkeeping) ----------------
@app.route("/api/summary")
def api_summary():
    return jsonify({"trumf": trumf_data(), "rema": rema_data(), "coop": receipt_archive.summary('coop')})

@app.route('/api/coop/status')
def coop_status():
    return jsonify(receipt_archive.summary('coop')['status'])

def coop_record(rid):
    try: return receipt_archive.read_receipt('coop', rid)
    except (ValueError, FileNotFoundError): abort(404)

@app.route('/coop/receipt/<rid>')
def coop_detail(rid):
    r=coop_record(rid)
    return render_template_string('''<!doctype html><html lang=nb><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Coop-kvittering</title>
<style>body{background:#0f1116;color:#eceef2;font:15px/1.6 system-ui;max-width:1000px;margin:24px auto;padding:16px}a{color:#72cce1}table{border-collapse:collapse;width:100%}td,th{padding:8px;text-align:left;border-bottom:1px solid #333}pre{white-space:pre-wrap}details{margin:20px 0}.mut{color:#aaa}</style>
<a href="/">← Grocious</a><h1>{{r.store}}</h1><p>{{r.date}} {{r.time or ''}} · {{'%.2f'|format(r.amount or 0)}} NOK</p>
<p><a href="{{r.archive_id}}.pdf">Original PDF</a> · <a href="{{r.archive_id}}.json">Komplett JSON</a> · <a href="{{r.archive_id}}.csv">Varelinjer CSV</a></p>
<table><tr><th>Vare</th><th>Antall/enhet oppgitt av Coop</th><th>Beløp</th><th>Rabatt</th></tr>
{% for l in r.lines %}<tr><td>{{l.name}}</td><td>{{l.quantity_text or '—'}}</td><td>{{l.amount if l.amount is not none else '—'}}</td><td>{{l.discount if l.discount is not none else '—'}}</td></tr>{% endfor %}</table>
{% if r.tax %}<h2>MVA</h2><table><tr><th>Del</th><th>Grunnlag</th><th>Sats</th><th>MVA</th><th>Sum</th></tr>{% for t in r.tax %}<tr><td>{{'Kjøp' if t.section=='purchase' else 'Medlemsfordel'}}</td><td>{{'%.2f'|format(t.base_minor/100)}}</td><td>{{t.rate}}%</td><td>{{'%.2f'|format(t.tax_minor/100)}}</td><td>{{'%.2f'|format(t.total_minor/100)}}</td></tr>{% endfor %}</table>{% endif %}
<h2>Medlemsfordeler</h2>{% for name,value in benefits %}{% if value is not none %}<div>{{name}}: {{value}}</div>{% endif %}{% endfor %}
<details><summary>Hele originalteksten, inkludert betaling og referanser</summary><pre>{{r.document_text}}</pre></details>
{% if r.validation.issues %}<p>Kontrollavvik: {{r.validation.issues|join(', ')}}. Originalen og alle kildedata er bevart.</p>{% endif %}
<p class=mut>Arkivert {{r.archived_at}}. Ukjent antall eller rabatt vises som «—».</p></html>''', r=r,
      benefits=[(label,r['benefits'].get(k)) for k,label in [('purchaseReturn','Kjøpeutbytte'),('memberDiscount','Medlemsrabatt'),('couponDiscount','Kupongrabatt'),('coopMastercard','Coop Mastercard'),('totalMemberBenefit','Oppgitt medlemsfordel')]])

@app.route('/coop/receipt/<rid>.<fmt>')
def coop_download(rid,fmt):
    r=coop_record(rid)
    if fmt=='json':return Response(json.dumps(r,ensure_ascii=False,indent=2),mimetype='application/json',headers={'Content-Disposition':f'attachment;filename=coop-{r["archive_id"]}.json'})
    if fmt=='csv':return Response(receipt_archive.receipt_csv(r),mimetype='text/csv',headers={'Content-Disposition':f'attachment;filename=coop-{r["archive_id"]}.csv'})
    if fmt=='pdf':
        doc=next((d for d in r['documents'] if d['role']=='original' and d['mimetype']=='application/pdf'),None)
        if not doc:abort(404)
        path,_=receipt_archive.document('coop',rid,doc['filename'])
        return send_file(path,mimetype='application/pdf',as_attachment=True,download_name=f'coop-{r["receipt_id"]}.pdf')
    abort(404)

def _month_receipts(ym, with_lines=False):
    out = []
    t, r = trumf_data(), rema_data()
    if t.get("ok"):
        for x in t["receipts"]:
            if x["date"].startswith(ym):
                rec = {"chain": "trumf", "id": str(x["id"]), "date": x["date"], "store": x["store"],
                       "amount": x["amount"], "bonus": x.get("bonus") or 0, "discount": 0}
                if with_lines and x.get("hasReceipt"):
                    rec["lines"] = trumf_lines(x["id"])
                out.append(rec)
    if r.get("ok"):
        for x in r["receipts"]:
            if x["date"].startswith(ym):
                rec = {"chain": "rema", "id": str(x["id"]), "date": x["date"][:10], "store": x["store"],
                       "amount": x["amount"], "bonus": 0, "discount": x.get("discount") or 0}
                if with_lines:
                    rec["lines"] = rema_lines(int(x["id"]))
                out.append(rec)
    for x in receipt_archive.summary('coop')['receipts']:
        if (x.get('date') or '').startswith(ym):
            rec={"chain":"coop","id":x['id'],"date":x['date'],"store":x['store'],"amount":x['amount'],"bonus":x.get('bonus') or 0,"discount":0,"archive_id":x['archive_id']}
            if with_lines:
                full=receipt_archive.read_receipt('coop',x['archive_id'])
                rec.update(full)
                # Existing combined totals require numbers; the source value stays explicit.
                rec['bonus']=full.get('bonus') or 0;rec['discount']=full.get('discount') or 0
            out.append(rec)
    out.sort(key=lambda x: x["date"])
    return out

@app.route("/api/export/<ym>.<fmt>")
def api_export(ym, fmt):
    if not re.fullmatch(r"\d{4}-\d{2}", ym) or fmt not in ("json", "csv"):
        abort(404)
    with_lines = request.args.get("lines") == "1"
    recs = _month_receipts(ym, with_lines)
    if fmt == "json":
        return jsonify({"month": ym, "count": len(recs),
                        "total": round(sum(x["amount"] or 0 for x in recs), 2),
                        "bonus": round(sum(x["bonus"] for x in recs), 2),
                        "discount": round(sum(x["discount"] for x in recs), 2),
                        "receipts": recs})
    buf = io.StringIO(); w = csv.writer(buf)
    if with_lines:
        w.writerow(["chain", "receipt_id", "date", "store", "item", "ean", "qty", "amount"])
        for x in recs:
            for l in x.get("lines", []):
                w.writerow([x["chain"], x["id"], x["date"], x["store"], l["name"], l["ean"], l["qty"], l["amount"]])
    else:
        w.writerow(["chain", "receipt_id", "date", "store", "amount", "bonus", "discount"])
        for x in recs:
            w.writerow([x["chain"], x["id"], x["date"], x["store"], x["amount"], x["bonus"], x["discount"]])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment;filename=grocious-{ym}{'-lines' if with_lines else ''}.csv"})

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "3012")))


# Independent archive routes preserve existing download contracts.
def archived_record(source,rid):
    try:return receipt_archive.read_receipt(source,rid)
    except (ValueError,FileNotFoundError):abort(404)

@app.route('/api/archive/<source>')
def archived_summary(source):
    try:return jsonify(receipt_archive.summary(source))
    except ValueError:abort(404)

@app.route('/archive/<source>')
def archived_list(source):
    try:data=receipt_archive.summary(source)
    except ValueError:abort(404)
    return render_template_string(ARCHIVE_STYLE+'''<a href="/">← Grocious</a><h1>{{provider|capitalize}} – kvitteringsarkiv</h1>
<p>Komplette kildedata bevares. Nedlastede leverandørbilder vises der de finnes; en «laget PDF» i den gamle eksporten er en Grocious-visning.</p>
<p>{{data.count}} arkiverte kjøp · {{data.status.get('state')}} · <a href="/api/archive/{{provider}}">Status/indeks JSON</a></p>
{% if data.get('image_status') %}<p>Leverandørbilder: {{data.image_status.get('already_archived',0)+data.image_status.get('downloaded',0)}} / {{data.image_status.expected}} · {{data.image_status.state}}{% if data.image_status.errors %} · {{data.image_status.errors|length}} hente-feil{% endif %}</p>{% endif %}
<table><tr><th>Dato</th><th>Butikk</th><th>Beløp</th><th>Arkiv</th></tr>{% for r in data.receipts %}<tr><td>{{r.date}}</td><td>{{r.store}}</td><td>{{r.amount}}</td><td><a href="/archive/{{provider}}/{{r.archive_id}}">Alle detaljer og originalfiler</a></td></tr>{% endfor %}</table>''',provider=source,data=data)

ARCHIVE_STYLE='''<!doctype html><html lang=nb><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Grocious kvitteringsarkiv</title><style>body{background:#0f1116;color:#eceef2;font:15px/1.6 system-ui;max-width:1000px;margin:24px auto;padding:16px}a{color:#72cce1}table{border-collapse:collapse;width:100%}td,th{padding:8px;text-align:left;border-bottom:1px solid #333}pre{white-space:pre-wrap;overflow-wrap:anywhere}img{max-width:100%}</style>'''

@app.route('/archive/<source>/<rid>')
def archived_detail(source,rid):
    r=archived_record(source,rid)
    return render_template_string(ARCHIVE_STYLE+'''<a href="/archive/{{provider}}">← Arkiv</a><h1>{{r.store}}</h1><p>{{r.date}} {{r.time or ''}} · {{r.amount}} NOK</p>
<p><a href="/archive/{{provider}}/{{r.archive_id}}.json">Komplett JSON</a> · <a href="/archive/{{provider}}/{{r.archive_id}}.zip">Alle arkivfiler ZIP</a></p>
{% if r.original_status=='raw_data_only' %}<p>Komplette originale API-data er arkivert. Et eget kvitteringsbilde er ikke funnet i de undersøkte kallene.</p>{% elif r.original_status=='image_not_retrieved' %}<p>Rådata er arkivert. Leverandørbilde er ikke hentet ennå.</p>{% elif r.original_status=='not_offered' %}<p>Kilden oppgir at dette kjøpet ikke har egen kvittering. Kjøpsopplysningene er bevart.</p>{% endif %}
<h2>Originalfiler</h2><ul>{% for d in r.documents %}<li><a href="/archive/{{provider}}/{{r.archive_id}}/file/{{d.filename}}">{{'Leverandørens kvitteringsbilde' if d.mimetype.startswith('image/') else d.role}} ({{d.mimetype}})</a></li>{% endfor %}</ul>
{% for d in r.documents %}{% if d.mimetype.startswith('image/') %}<img loading=lazy alt="Leverandørens kvitteringsbilde" src="/archive/{{provider}}/{{r.archive_id}}/file/{{d.filename}}">{% endif %}{% endfor %}
<h2>Varelinjer</h2><table><tr><th>Vare</th><th>Antall</th><th>Enhet</th><th>Beløp</th></tr>{% for l in r.lines %}<tr><td>{{l.name}}</td><td>{{l.qty if l.qty is not none else '—'}}</td><td>{{l.unit or '—'}}</td><td>{{l.amount if l.amount is not none else '—'}}</td></tr>{% endfor %}</table>
<details><summary>Alle kildefelter, inkludert betaling, pant, MVA og bonus der oppgitt</summary><pre>{{raw}}</pre></details>
{% if r.validation.issues %}<p>Kontrollavvik: {{r.validation.issues|join(', ')}}</p>{% endif %}<p>Arkivert {{r.archived_at}}. Dokumenter kontrolleres mot SHA-256 ved nedlasting.</p>''',r=r,provider=source,raw=json.dumps(r['source'],ensure_ascii=False,indent=2))

@app.route('/archive/<source>/<rid>.<fmt>')
def archived_download(source,rid,fmt):
    r=archived_record(source,rid)
    if fmt=='json':return Response(json.dumps(r,ensure_ascii=False,indent=2),mimetype='application/json',headers={'Content-Disposition':f'attachment;filename={source}-{rid}.json'})
    if fmt=='zip':
        import zipfile
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w',compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('receipt.json',json.dumps(r,ensure_ascii=False,indent=2))
            for d in r['documents']:
                path,_=receipt_archive.document(source,rid,d['filename']);z.write(path,d['filename'])
        buf.seek(0);return send_file(buf,mimetype='application/zip',as_attachment=True,download_name=f'{source}-{rid}.zip')
    abort(404)

@app.route('/archive/<source>/<rid>/file/<filename>')
def archived_file(source,rid,filename):
    archived_record(source,rid)
    try:path,doc=receipt_archive.document(source,rid,filename)
    except (ValueError,FileNotFoundError):abort(404)
    return send_file(path,mimetype=doc['mimetype'],as_attachment=not doc['mimetype'].startswith('image/'),download_name=filename)
