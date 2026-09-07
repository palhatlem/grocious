"""Reviewable duplicate candidates and durable attachments beside provider receipts."""

import datetime as dt
import json
import re
from pathlib import Path

import receipt_archive as archive
from . import store


def candidates(rid):
    r = archive.read_receipt("inbox", rid)
    date = dt.date.fromisoformat(r["date"]) if r.get("date") else None
    normalized = lambda s: re.sub(r"\W+", "", (s or "").casefold())
    result = []
    parent = r.get("intake", {}).get("parent")
    for source in sorted(archive.SOURCES):
        for candidate in archive.summary(source)["receipts"]:
            related = False
            if source == "inbox":
                if candidate["archive_id"] == rid:
                    continue
                # Read current review overlays; an index can lag behind a link/discard.
                candidate = archive.read_receipt("inbox", candidate["archive_id"])
                if candidate.get("review", {}).get("state") == "linked":
                    continue
                other_parent = candidate.get("intake", {}).get("parent")
                related = candidate["archive_id"] == parent or other_parent == rid
            try:
                days = abs((dt.date.fromisoformat(candidate["date"]) - date).days) if date else None
            except (ValueError, TypeError):
                days = None
            n = candidate.get("amount_minor")
            if n is None:
                n = archive.minor(candidate.get("amount"))
            exact = (
                days is not None
                and days <= 1
                and n is not None
                and n == r.get("amount_minor")
                and candidate.get("currency", "NOK") == r.get("currency")
            )
            same_store = (
                days == 0
                and bool(r.get("store"))
                and normalized(r["store"]) == normalized(candidate.get("store"))
                and candidate.get("currency", "NOK") == r.get("currency")
            )
            siblings = source == "inbox" and bool(parent) and candidate.get("intake", {}).get("parent") == parent
            if related or exact or same_store:
                reason = (
                    "E-post og vedlegg"
                    if related
                    else "Vedlegg fra samme e-post"
                    if siblings
                    else "Samme beløp og dato ± én dag"
                    if exact
                    else "Samme butikk og dato"
                )
                result.append(
                    {
                        **candidate,
                        "source": source,
                        "exact": exact,
                        "related": related or siblings,
                        "reason": reason + (" · samme beløp og valuta" if related and exact else ""),
                        "url": "/inbox/" + candidate["archive_id"]
                        if source == "inbox"
                        else "/archive/" + source + "/" + candidate["archive_id"],
                    }
                )
    return sorted(result, key=lambda c: (not c["related"], not c["exact"]))


def link(rid, source, target):
    if not isinstance(source, str) or not isinstance(target, str) or source not in archive.SOURCES:
        raise ValueError("Velg en kvittering som hovedpost")
    with store.locked():
        r = archive.read_receipt("inbox", rid)
        primary = archive.read_receipt(source, target)
        if source == "inbox" and target == rid:
            raise ValueError("En kvittering kan ikke kobles til seg selv")
        if source == "inbox" and primary.get("review", {}).get("state") in ("linked", "discarded"):
            raise ValueError("Velg en hovedpost som ikke er koblet eller forkastet")
        if r.get("linked_from"):
            raise ValueError("Denne hovedposten har allerede koblede bilag. Behold den som hovedpost.")
        if r.get("linked_to") and r["linked_to"] != {"source": source, "archive_id": target}:
            raise ValueError("Kvitteringen er allerede koblet til en annen original")
        directory = archive.folder(source, target)
        path = directory / "user-uploads.json"
        additions = json.loads(path.read_text()) if path.exists() else {"documents": [], "linked_from": []}
        for doc in r["documents"]:
            if doc["role"] not in ("original", "email"):
                continue
            original, _ = archive.document("inbox", rid, doc["filename"])
            attached = archive.original(
                directory,
                "user-upload",
                original.read_bytes(),
                Path(doc["filename"]).suffix.lstrip("."),
                doc["mimetype"],
            )
            if attached not in additions["documents"]:
                additions["documents"].append(attached)
        if rid not in additions["linked_from"]:
            additions["linked_from"].append(rid)
        # Provider sync may rewrite receipt.json. This independently merged overlay survives it.
        archive.atomic_json(path, additions)
        archive.atomic_json(
            archive.folder("inbox", rid) / "review.json",
            {
                "review": {"state": "linked", "by": "user", "at": store.now()},
                "linked_to": {"source": source, "archive_id": target},
            },
        )
        if source != "inbox":
            archive.rebuild(source)
        archive.rebuild("inbox")
