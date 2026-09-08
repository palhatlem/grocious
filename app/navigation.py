"""User-configured navigation links, stored outside the source tree."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from flask import Blueprint, abort, jsonify, request

from receipt_archive import atomic_json

bp = Blueprint("navigation", __name__)


def path():
    return Path(os.environ.get("GROCERY_DATA", "/data")) / "navigation.json"


def validate(value):
    if not isinstance(value, dict) or not isinstance(value.get("enabled"), bool):
        raise ValueError("Velg om lenkelisten skal vises.")
    links = value.get("links")
    if not isinstance(links, list) or len(links) > 20:
        raise ValueError("Du kan lagre opptil 20 lenker.")
    result = []
    for item in links:
        if not isinstance(item, dict):
            raise ValueError("Ugyldig lenke.")
        label, url = item.get("label"), item.get("url")
        if not isinstance(label, str) or not isinstance(url, str):
            raise ValueError("Hver lenke trenger visningsnavn og nettadresse.")
        label, url = label.strip(), url.strip()
        if not label or len(label) > 60 or len(url) > 2000 or any(ord(c) < 32 for c in url):
            raise ValueError("Bruk et navn på maks. 60 tegn og en gyldig nettadresse.")
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Nettadressen må begynne med https:// eller http://, uten innloggingsinformasjon.")
        result.append({"label": label, "url": url})
    return {"enabled": value["enabled"], "links": result}


def load():
    try:
        return validate(json.loads(path().read_text()))
    except (OSError, ValueError):
        return {"enabled": True, "links": []}


@bp.post("/api/navigation")
def save():
    if not request.is_json:
        abort(415)
    origin = request.headers.get("Origin")
    if request.headers.get("Sec-Fetch-Site") == "cross-site" or (
        origin and urlsplit(origin).netloc != request.host
    ):
        abort(403)
    try:
        value = validate(request.get_json())
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    atomic_json(path(), value)
    return jsonify(value)
