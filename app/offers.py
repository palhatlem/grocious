"""Provider offer presentation. Reading offers never activates them."""

import hashlib
import json
import os
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests


def url(value):
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value)
    return value if parsed.scheme in ("https", "http") and parsed.netloc else None


def normalize(source, raw):
    if source == "trumf":
        return {
            "id": raw.get("kampanjeId"),
            "title": raw.get("visningsTekst"),
            "desc": raw.get("beskrivelse"),
            "terms": raw.get("betingelser"),
            "notice": raw.get("advarselBeskrivelse"),
        }
    if source == "rema":
        return {
            "id": raw.get("id") or raw.get("code"),
            "code": raw.get("code"),
            "title": raw.get("header"),
            "desc": raw.get("desc"),
            "terms": raw.get("note"),
            "activated": raw.get("activated"),
            "img": url(raw.get("dutyText")),
            "url": url(raw.get("marketingUrl")),
        }
    photo = raw.get("productPhoto") or {}
    return {
        "id": raw.get("offerId"),
        "title": raw.get("promoName") or raw.get("description"),
        "desc": raw.get("promoDesc"),
        "terms": raw.get("finePrint"),
        "notice": raw.get("clarifyingText"),
        "img": url(photo.get("url")),
        "price": raw.get("priceBombText"),
        "expires": raw.get("expirationTextDetail"),
        "activated": bool(raw.get("activationDate")),
    }


def cards(source, rows):
    result = []
    for raw in rows or []:
        o = dict(raw)
        identity = (
            o.get("id")
            or o.get("code")
            or hashlib.sha256(json.dumps([o.get("title"), o.get("desc")], ensure_ascii=False).encode()).hexdigest()[:20]
        )
        o.update(
            source=source,
            id=str(identity),
            title=o.get("title") or o.get("desc") or "Tilbud uten tittel",
            img=url(o.get("img")),
            url=url(o.get("url")),
        )
        result.append(o)
    return result


def coop_data():
    try:
        headers = json.loads((Path(os.environ.get("GROCERY_DATA", "/data")) / "coop_session.json").read_text())[
            "headers"
        ]
        response = requests.get("https://cdcapp.coop.no/coupon/all", headers=headers, timeout=20)
        response.raise_for_status()
        raw = response.json()
        if raw.get("resultCode") != "SUCCESS":
            raise ValueError("Coop coupon response failed")
        now = time.time() * 1000
        rows = [
            r
            for m in raw["membershipCoupons"]
            for r in m["coupons"]
            if not (r.get("redemption") or {}).get("redemptionDate")
            and (not r.get("endTime") or r["endTime"] >= now)
            and (not r.get("publishDate") or r["publishDate"] <= now)
        ]
        return {"offers": [normalize("coop", r) for r in rows]}
    except (OSError, ValueError, KeyError, TypeError, requests.RequestException):
        return {"offers": [], "offers_error": "Kunne ikke hente Coop-kuponger akkurat nå."}
