"""Immutable source files, append-only interpretations, and review overlays."""

import datetime as dt
import fcntl
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path

import receipt_archive as archive
from .extract import extract
from .heuristics import CATEGORIES, money, parse


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


@contextmanager
def locked():
    directory = archive.root() / "inbox"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / "write.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def normalize(parsed):
    n = money(parsed.get("total"))
    lines = []
    for i, item in enumerate(parsed.get("lines") or []):
        amount, discount = money(item.get("amount")), money(item.get("discount"))
        lines.append(
            dict(
                line_number=i + 1,
                name=item.get("name"),
                ean=item.get("ean"),
                qty=item.get("qty"),
                unit=item.get("unit"),
                quantity_text=None,
                amount=None if amount is None else amount / 100,
                amount_minor=amount,
                discount=None if discount is None else discount / 100,
                discount_minor=discount,
                kind=item.get("kind") or "item",
                source=item,
            )
        )
    return dict(
        store=parsed.get("store"),
        chain=parsed.get("chain") or "other",
        date=parsed.get("date"),
        time=parsed.get("time"),
        currency=parsed.get("currency"),
        amount_minor=n,
        amount=None if n is None else n / 100,
        lines=lines,
        tax=parsed.get("vat") or [],
        category=parsed.get("category") or "ukjent",
        receipt_number=parsed.get("receipt_number"),
        payment=parsed.get("payment"),
    )


def validate(record):
    issues = []
    if record.get("amount_minor") is None:
        issues.append("total_unparsed")
    if not record.get("date"):
        issues.append("date_unparsed")
    if not record.get("store"):
        issues.append("store_unparsed")
    if not record.get("currency"):
        issues.append("currency_unparsed")
    lines = record.get("lines") or []
    if not lines:
        issues.append("no_structured_lines")
    known = bool(lines) and all(l.get("amount_minor") is not None for l in lines)
    total = sum(l["amount_minor"] for l in lines) if known else None
    difference = (
        total - record["amount_minor"] if total is not None and record.get("amount_minor") is not None else None
    )
    if difference not in (None, 0):
        issues.append("line_total_difference")
    return dict(issues=issues, line_sum_minor=total, difference_minor=difference)


def overlay(record, directory):
    record = dict(record)
    active = directory / "active.json"
    if active.exists():
        pointer = json.loads(active.read_text())
        run = json.loads((directory / f"interpretation-{int(pointer['run'])}.json").read_text())
        record.update(normalize(run["parsed"]))
        record["interpretation"] = run["metadata"]
    corrections = directory / "corrections.json"
    if corrections.exists():
        record.update({k: v for k, v in json.loads(corrections.read_text()).items() if k != "at"})
    review = directory / "review.json"
    if review.exists():
        data = json.loads(review.read_text())
        record["review"], record["linked_to"] = data["review"], data.get("linked_to")
    record["validation"] = validate(record)
    if active.exists() and record["interpretation"].get("provider") != "none" and record.get("document_text"):
        corrected = json.loads(corrections.read_text()) if corrections.exists() else {}
        if "amount_minor" in corrected:
            return record
        import re

        values = set()
        for v in re.findall(r"(?<![\d.])-?\d[\d ]*[,.]\d{2}(?![\d.])", record["document_text"]):
            try:
                values.add(money(v))
            except ValueError:
                pass
        if record.get("amount_minor") is not None and record["amount_minor"] not in values:
            record["validation"]["issues"].append("llm_total_not_in_text")
    return record


def ingest(data, filename="receipt.txt", mimetype="text/plain", intake=None, depth=0):
    if depth > 2:
        raise ValueError("For mange nivåer med e-postvedlegg")
    digest = hashlib.sha256(data).hexdigest()
    rid = archive.key("inbox", digest)
    directory = archive.folder("inbox", rid)
    path = directory / "receipt.json"
    extracted = None
    with locked():
        duplicate = path.exists()
    if not duplicate:
        extracted = extract(data, filename, mimetype)
    with locked():
        duplicate = path.exists()
        if not duplicate:
            documents = [
                archive.original(
                    directory,
                    "email" if extracted["kind"] == "eml" else "original",
                    data,
                    extracted["extension"],
                    extracted["mimetype"],
                )
            ]
            for content, ext, mime in extracted["derived"]:
                documents.append(archive.original(directory, "derived", content, ext, mime))
            text = extracted["text"]
            if text:
                documents.append(archive.original(directory, "derived", text.encode(), "txt", "text/plain"))
            parsed = parse(text)
            record = dict(
                schema_version=1,
                parser_version="inbox-1",
                id=digest,
                archive_id=rid,
                timezone="Europe/Oslo",
                archived_at=now(),
                source={"baseline": parsed},
                source_datetime=None,
                bonus=None,
                discount=None,
                benefits={},
                receipt_id=None,
                documents=documents,
                document_text=text,
                linked_to=None,
                intake={
                    **(intake or {}),
                    "channel": (intake or {}).get("channel", "upload"),
                    "received_at": now(),
                    "filename": Path(filename).name,
                    "mimetype": extracted["mimetype"],
                },
                extraction=dict(
                    kind=extracted["kind"],
                    engine=extracted["engine"],
                    chars=len(text),
                    text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                ),
                interpretation=dict(
                    provider="none", model=None, prompt_version="rules-1", confidence=parsed["confidence"], ran_at=now()
                ),
                review=dict(state="needs_review", by=None, at=None),
                **normalize(parsed),
            )
            record["validation"] = validate(record)
            archive.atomic_json(path, record)
            archive.rebuild("inbox")
    # Retry attachment ingestion even after a partial prior mail ingestion.
    if extracted is None and (mimetype == "message/rfc822" or filename.lower().endswith(".eml")):
        extracted = extract(data, filename, mimetype)
    children = []
    if extracted:
        for content, name, mime in extracted["children"]:
            children.append(ingest(content, name, mime, {**(intake or {}), "parent": rid}, depth + 1)["rid"])
        if children:
            with locked():
                archive.atomic_json(directory / "children.json", children)
    import os

    if not duplicate and os.getenv("GROCIOUS_LLM_AUTO", "0") == "1":
        from . import llm

        chosen = os.getenv("GROCIOUS_LLM_DEFAULT", "none")
        if chosen != "none":
            try:
                llm.run(rid, chosen)
            except ValueError:
                # Intake remains durable even when an optional provider is down.
                archive.atomic_json(directory / "interpretation-error.json", {"at": now(), "error": "provider_failed"})
    return dict(
        rid=rid,
        state=archive.read_receipt("inbox", rid)["review"]["state"],
        duplicate=duplicate,
        duplicate_of_self=duplicate,
        children=children,
    )


def correct(rid, edits):
    if not isinstance(edits, dict):
        raise ValueError("Ugyldige korrigeringer")
    allowed = {"store", "date", "time", "amount", "category", "currency", "lines", "note"}
    if set(edits) - allowed:
        raise ValueError("Ukjent korrigeringsfelt")
    values = dict(edits)
    for field in ("store", "note"):
        if field in values and values[field] is not None:
            if not isinstance(values[field], str) or len(values[field]) > 4000:
                raise ValueError("Ugyldig tekstfelt")
    for field in ("date", "time", "store", "currency"):
        if field in values:
            if values[field] is not None and not isinstance(values[field], str):
                raise ValueError("Ugyldig tekstfelt")
            values[field] = (values[field] or "").strip() or None
    if values.get("date"):
        values["date"] = dt.date.fromisoformat(values["date"]).isoformat()
    if values.get("time"):
        dt.time.fromisoformat(values["time"])
    if "category" in values and values["category"] not in CATEGORIES:
        raise ValueError("Ukjent kategori")
    if values.get("currency") and values["currency"] not in ("NOK", "SEK", "DKK", "EUR", "USD", "GBP"):
        raise ValueError("Ugyldig valuta")
    if "amount" in values:
        values["amount_minor"] = money(values["amount"])
        values["amount"] = None if values["amount_minor"] is None else values["amount_minor"] / 100
    if "lines" in values:
        if (
            not isinstance(values["lines"], list)
            or len(values["lines"]) > 1000
            or any(not isinstance(v, dict) for v in values["lines"])
        ):
            raise ValueError("Ugyldige varelinjer")
        values["lines"] = normalize({"lines": values["lines"]})["lines"]
    with locked():
        directory = archive.folder("inbox", rid)
        if archive.read_receipt("inbox", rid).get("linked_to"):
            raise ValueError("Kvitteringen er koblet. Gjennomgå den via kjedekvitteringen.")
        path = directory / "corrections.json"
        old = json.loads(path.read_text()) if path.exists() else {}
        archive.atomic_json(path, {**old, **values, "at": now()})
        archive.atomic_json(directory / "review.json", dict(review=dict(state="needs_review", by="user", at=now())))
        archive.rebuild("inbox")


def state(rid, value):
    if value not in ("confirmed", "discarded", "needs_review"):
        raise ValueError("Ugyldig status")
    with locked():
        r = archive.read_receipt("inbox", rid)
        if r.get("linked_to"):
            raise ValueError("En koblet kvittering beholdes som vedlegg; den kan ikke eksporteres på nytt")
        if value == "confirmed" and (
            r.get("amount_minor") is None or any(not r.get(k) for k in ("store", "date", "currency"))
        ):
            raise ValueError("Butikk, dato, beløp og valuta må fylles ut før bekreftelse")
        archive.atomic_json(
            archive.folder("inbox", rid) / "review.json",
            dict(review=dict(state=value, by="user", at=now()), linked_to=None),
        )
        archive.rebuild("inbox")


def summary():
    data = archive.summary("inbox")
    rows = data["receipts"]
    counts = {
        s: sum(r.get("review", {}).get("state") == s for r in rows)
        for s in ("needs_review", "confirmed", "discarded", "linked")
    }
    month = dt.date.today().isoformat()[:7]
    monthly = [
        r
        for r in rows
        if (r.get("date") or "").startswith(month) and r.get("review", {}).get("state") not in ("linked", "discarded")
    ]
    totals = {}
    for r in monthly:
        if r.get("currency") and r.get("amount_minor") is not None:
            totals[r["currency"]] = totals.get(r["currency"], 0) + r["amount_minor"]
    from .llm import providers

    return dict(
        month=month,
        month_count=len(monthly),
        totals={k: v / 100 for k, v in totals.items()},
        providers=providers(),
        mail=json.loads((archive.root() / "inbox" / "mail_status.json").read_text())
        if (archive.root() / "inbox" / "mail_status.json").exists()
        else {"connected": False},
        count=len(rows),
        **counts,
        last_ingest=max((r.get("intake", {}).get("received_at", "") for r in rows), default=None),
    )


def exports(ym, with_lines=False):
    result = []
    for item in archive.summary("inbox")["receipts"]:
        if (item.get("date") or "").startswith(ym) and item.get("review", {}).get("state") not in (
            "discarded",
            "linked",
        ):
            r = archive.read_receipt("inbox", item["archive_id"])
            out = {
                k: r.get(k)
                for k in (
                    "archive_id",
                    "id",
                    "chain",
                    "store",
                    "date",
                    "amount",
                    "amount_minor",
                    "currency",
                    "category",
                    "linked_to",
                )
            }
            out.update(
                source="inbox",
                review_state=r["review"]["state"],
                confidence=r["interpretation"].get("confidence"),
                bonus=0,
                discount=0,
            )
            if with_lines:
                out["lines"] = r["lines"]
            result.append(out)
    return result
