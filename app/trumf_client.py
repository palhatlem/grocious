#!/usr/bin/env python3
"""Trumf client — uses the saved NextAuth session cookie to pull bonus balance,
receipts and campaign offers via the (browser-free) BFF token. Playwright only
needed for the periodic re-login (login.py), not here."""
import json, os, sys, datetime, urllib.request, urllib.parse
import requests

STATE = os.environ.get("TRUMF_STATE", "/data/trumf_state.json")
NTFY  = os.environ.get("NTFY_URL")           # e.g. https://ntfy.bauneveien.no/alfreds-... (optional)
API   = "https://platform-rest-prod.ngdata.no"

def load_session():
    st = json.load(open(STATE))
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) grocery-bot"
    for c in st.get("cookies", []):
        if "trumf.no" in c.get("domain", ""):
            s.cookies.set(c["name"], c["value"], domain=c["domain"].lstrip("."), path=c.get("path","/"))
    return s

def access_token(s):
    r = s.get("https://www.trumf.no/api/auth/session", timeout=20)
    r.raise_for_status()
    tok = r.json().get("accessToken")
    if not tok:
        raise SystemExit("no accessToken in session — cookie expired, run login.py")
    return tok

def main():
    s = load_session()
    tok = access_token(s)
    h = {"Authorization": "Bearer " + tok, "Accept": "application/json"}
    saldo = requests.get(f"{API}/trumf/husstand/saldo", headers=h, timeout=20).json()
    today = datetime.date.today(); frm = today.replace(day=1) - datetime.timedelta(days=365)
    tx = requests.get(f"{API}/trumf/husstand/transaksjoner", headers=h, timeout=30, params={
        "felter":"dato,beskrivelse,belop,trumftotal,batchid","fra":frm.isoformat(),"til":today.isoformat(),"format":"crm"}).json()
    offers = requests.get(f"{API}/trumf/kampanjeavtale/beskrivelser", headers=h, timeout=20).json()
    out = {
        "trumf_saldo": saldo.get("trumfSaldo"),
        "trumf_akkumulert": saldo.get("totaltAkkumulertTrumf"),
        "saldo_oppdatert": saldo.get("sistOppdatert"),
        "transaksjoner_12mnd": len(tx) if isinstance(tx, list) else None,
        "kampanjer_tilgjengelig": len(offers) if isinstance(offers, list) else None,
        "hentet": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    os.makedirs("/data", exist_ok=True)
    json.dump(out, open("/data/status.json","w"), ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if NTFY:
        msg = f"Trumf: {out['trumf_saldo']} kr bonus · {out['kampanjer_tilgjengelig']} kampanjer · {out['transaksjoner_12mnd']} kjøp (12 mnd)"
        try: requests.post(NTFY, data=msg.encode(), headers={"Title":"Trumf bonus","Tags":"shopping_cart"}, timeout=10)
        except Exception as e: print("ntfy failed:", e, file=sys.stderr)

if __name__ == "__main__":
    main()
