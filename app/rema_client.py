#!/usr/bin/env python3
"""Rema 1000 (Æ) client — OAuth2+PKCE tokens (from login), auto-refresh, then
pulls offers, receipts and profile. Coupon activation supported via activate()."""
import json, os, uuid, datetime, sys
import requests
DATA=os.environ.get("REMA_DATA","/data")
TOKENS=os.path.join(DATA,"rema_tokens.json")
DEVICE=os.path.join(DATA,"rema_device.json")
PHONE=os.environ.get("REMA_PHONE","")
NTFY=os.environ.get("NTFY_URL")
API="https://api.rema.no"; SUBKEY="fb5e24884b504d0bad761098f77e6605"

def device_id():
    if os.path.exists(DEVICE): return json.load(open(DEVICE))["device_id"]
    d=str(uuid.uuid4()); json.dump({"device_id":d}, open(DEVICE,"w")); return d

def refresh(tok):
    r=requests.post("https://id.rema.no/token", data={"grant_type":"refresh_token",
        "refresh_token":tok["refresh_token"],"client_id":"android-251010"}, timeout=20)
    r.raise_for_status(); nt=r.json()
    # keep refresh_token if the server didn't rotate it
    nt.setdefault("refresh_token", tok["refresh_token"])
    json.dump(nt, open(TOKENS,"w")); return nt

def headers(tok):
    return {"Authorization":"Bearer "+tok["access_token"],"ocp-apim-subscription-key":SUBKEY,
        "x-platform":"android","x-correlation-id":str(uuid.uuid4()),"x-device-id":device_id(),
        "x-mobile-nr":PHONE,"x-app":"bella","x-app-version":"3.0.12 #110549","Accept":"application/json"}

def get(path, tok):
    r=requests.get(API+path, headers=headers(tok), timeout=30)
    if r.status_code==401:
        tok.update(refresh(tok)); r=requests.get(API+path, headers=headers(tok), timeout=30)
    return r


def activate_offers(tok, codes):
    """OPT-IN: activate specific Rema offers (POST array of codes). NOT called automatically."""
    r=requests.post(API+"/v1/bella/offers/activate", headers=headers(tok), json=list(codes), timeout=30)
    return r.status_code, r.ok

def main():
    tok=json.load(open(TOKENS))
    tok=refresh(tok)   # always start fresh (1h expiry)
    offers=get("/v1/bella/offers/v2/available-offers/", tok)
    heads=get("/v1/bella/transaction/v2/heads", tok)
    oj=offers.json() if offers.ok else None
    olist=oj if isinstance(oj,list) else (oj.get("offers") if isinstance(oj,dict) else []) or []
    offers_active=sum(1 for o in olist if o.get("activated"))
    # NOTE: coupons are NOT auto-activated (deliberate). Use activate_offers() manually if wanted.
    hj=heads.json() if heads.ok else None
    out={
        "offers_status":offers.status_code,
        "offers_activated": offers_active,
        "offers_available": len(oj) if isinstance(oj,list) else (len(oj.get("offers",[])) if isinstance(oj,dict) else None),
        "receipts_status":heads.status_code,
        "purchase_total": (hj or {}).get("purchaseTotal") if isinstance(hj,dict) else None,
        "discount_total": (hj or {}).get("discountTotal") if isinstance(hj,dict) else None,
        "transactions": len((hj or {}).get("transactions",[])) if isinstance(hj,dict) else None,
        "hentet": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    json.dump(out, open(os.path.join(DATA,"rema_status.json"),"w"), ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if NTFY and offers.ok:
        try: requests.post(NTFY, data=f"Rema: {out['offers_available']} tilbud · {out['transactions']} kjøp".encode(),
            headers={"Title":"Rema 1000","Tags":"shopping_cart"}, timeout=10)
        except: pass

if __name__=="__main__": main()
