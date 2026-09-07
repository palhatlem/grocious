"""Conservative mail replay identity; transport headers and MIME boundaries may change."""

import hashlib
import json
from email import policy
from email.parser import BytesParser

import receipt_archive as archive


def identify(data):
    message = BytesParser(policy=policy.default).parsebytes(data)
    message_id = str(message.get("Message-ID", "")).strip()
    if not message_id or len(message_id) > 998:
        return None
    # Compare rendered body text and exact attachment/inline-image bytes.
    # Bridge can rewrite HTML presentation as well as transport headers.
    parts = []
    for part in message.walk():
        if part.is_multipart():
            continue
        if part.get_content_type() in ("text/plain", "text/html") and not part.get_filename():
            body = part.get_content()
            if part.get_content_type() == "text/html":
                import html2text

                body = html2text.html2text(body)
            payload = body.replace("\r\n", "\n").strip().encode("utf-8")
        else:
            payload = part.get_payload(decode=True)
        if payload is None:
            payload = str(part.get_payload()).encode("utf-8")
        parts.append(
            [
                part.get_content_type(),
                part.get_content_charset(),
                part.get_filename(),
                hashlib.sha256(payload).hexdigest(),
            ]
        )
    material = {
        "message_id": message_id,
        "headers": {key: " ".join(str(message.get(key, "")).split()) for key in ("Date", "From", "To", "Subject")},
        "parts": parts,
    }
    digest = hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()
    return {"version": 1, "message_id": message_id, "fingerprint": digest}


def lookup(identity):
    """Called under the inbox write lock; lazily identify pre-upgrade EML receipts too."""
    if not identity:
        return None
    matches = []
    for path in (archive.root() / "inbox").glob("*/receipt.json"):
        record = json.loads(path.read_text())
        if record.get("extraction", {}).get("kind") != "eml":
            continue
        cached = path.parent / "mail-identity.json"
        if cached.exists():
            previous = json.loads(cached.read_text())
        else:
            doc = next(d for d in record["documents"] if d["role"] == "email")
            original, _ = archive.document("inbox", path.parent.name, doc["filename"])
            previous = identify(original.read_bytes())
            archive.atomic_json(cached, previous)
        if previous and previous["fingerprint"] == identity["fingerprint"]:
            matches.append((record.get("intake", {}).get("received_at") or record["archived_at"], path.parent.name))
    return min(matches)[1] if matches else None


def preserve_variant(directory, data):
    """Append the differing raw delivery without rewriting receipt.json or prior files."""
    doc = archive.original(directory, "email", data, "eml", "message/rfc822")
    baseline = json.loads((directory / "receipt.json").read_text())
    path = directory / "mail-variants.json"
    variants = json.loads(path.read_text()) if path.exists() else []
    if doc["filename"] not in {d["filename"] for d in baseline["documents"] + variants}:
        variants.append(doc)
        archive.atomic_json(path, variants)
