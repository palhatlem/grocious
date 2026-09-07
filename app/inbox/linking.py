"""Reviewable duplicate candidates and durable attachments beside provider receipts."""

import datetime as dt
import json
import re
from pathlib import Path

import receipt_archive as archive
from . import store


def candidates(rid):
    r = archive.read_receipt("inbox", rid)
    if not r.get("date"):
        return []
    date = dt.date.fromisoformat(r["date"])
    normalized = lambda s: re.sub(r"\W+", "", (s or "").casefold())
    result = []
    for source in sorted(archive.SOURCES - {"inbox"}):
        for candidate in archive.summary(source)["receipts"]:
            try:
                days = abs((dt.date.fromisoformat(candidate["date"]) - date).days)
            except (ValueError, TypeError):
                continue
            n = candidate.get("amount_minor")
            if n is None:
                n = archive.minor(candidate.get("amount"))
            exact = (
                days <= 1
                and n is not None
                and n == r.get("amount_minor")
                and candidate.get("currency", "NOK") == r.get("currency")
            )
            same_store = (
                days == 0 and bool(r.get("store")) and normalized(r["store"]) == normalized(candidate.get("store"))
            )
            if exact or same_store:
                result.append(
                    {
                        **candidate,
                        "source": source,
                        "exact": exact,
                        "reason": "Samme beløp og dato ± én dag" if exact else "Samme butikk og dato",
                    }
                )
    return result


def link(rid, source, target):
    if source not in archive.SOURCES - {"inbox"}:
        raise ValueError("Velg en kjedekvittering")
    with store.locked():
        r = archive.read_receipt("inbox", rid)
        archive.read_receipt(source, target)
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
        archive.rebuild(source)
        archive.rebuild("inbox")
