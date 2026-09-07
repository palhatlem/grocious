"""Conservative parsing of printed amounts; unknowns stay unknown."""

import datetime as dt
import re
from decimal import Decimal
from .payment import parse as parse_payment

CATEGORIES = ("mat", "alkohol", "apotek", "husholdning", "restaurant", "transport", "annet", "ukjent")
STORES = {
    "kiwi": "mat",
    "meny": "mat",
    "spar": "mat",
    "joker": "mat",
    "rema": "mat",
    "coop": "mat",
    "extra": "mat",
    "bunnpris": "mat",
    "oda": "mat",
    "vinmonopolet": "alkohol",
    "apotek": "apotek",
    "vitusapotek": "apotek",
    "boots": "apotek",
    "restaurant": "restaurant",
    "cafe": "restaurant",
    "kafé": "restaurant",
    "clas ohlson": "husholdning",
}
MONEY = r"-?\d[\d .\u00a0]*[,.]\d{2}"


def money(value):
    if value is None or str(value).strip() == "":
        return None
    s = str(value).strip().replace("\u00a0", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        n = Decimal(s)
        if not n.is_finite() or abs(n) > 100000000:
            raise ValueError("Ugyldig beløp")
        return int((n * 100).quantize(Decimal("1")))
    except ArithmeticError as e:
        raise ValueError("Ugyldig beløp") from e


def parse(text, received_at=None):
    rows = [s.strip() for s in text.splitlines() if s.strip()]
    result = dict(
        store=None,
        chain="other",
        date=None,
        time=None,
        currency=None,
        total=None,
        lines=[],
        vat=[],
        payment=parse_payment(text),
        receipt_number=None,
        category="ukjent",
        notes=None,
        confidence=dict(store=0, date=0, total=0, lines=0),
    )
    for row in rows[:12]:
        for name, category in STORES.items():
            if re.search(r"\b" + re.escape(name) + r"\b", row, re.I):
                result.update(store=row, chain="coop" if name == "extra" else name, category=category)
                result["confidence"]["store"] = 0.8
                break
        if result["store"]:
            break
    m = re.search(r"\b(\d{1,2})[./](\d{1,2})(?:[./](\d{4}|\d{2}))?\b", text)
    if m:
        year = int(m[3]) if m[3] else None
        if year is not None and year < 100:
            year += 2000
        # Missing year is never silently inferred from today's date.
        if year:
            try:
                result["date"] = dt.date(year, int(m[2]), int(m[1])).isoformat()
                result["confidence"]["date"] = 0.9
            except ValueError:
                pass
    iso = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
    if iso:
        try:
            result["date"] = dt.date.fromisoformat(iso[1]).isoformat()
            result["confidence"]["date"] = 0.95
        except ValueError:
            pass
    clock = re.search(r"\b([012]\d:[0-5]\d)\b", text)
    if clock and int(clock[1][:2]) < 24:
        result["time"] = clock[1]
    if re.search(r"\b(NOK|kr)\b", text, re.I):
        result["currency"] = "NOK"
    total_row = len(rows)
    for keyword in (r"å\s+betale", "totalt", "total", "sum", "bank", "kort"):
        matches = []
        for i, row in enumerate(rows):
            m = re.search(
                r"^\s*" + keyword + r"\b\s*[:=]?\s*(?:NOK|kr)?\s*(" + MONEY + r")\s*(?:NOK|kr)?\s*$", row, re.I
            )
            if m:
                matches.append((i, m[1]))
        if matches:
            total_row, value = matches[-1]
            result["total"] = money(value) / 100
            result["confidence"]["total"] = 0.9 if keyword not in ("bank", "kort") else 0.5
            break
    for row in rows[:total_row]:
        m = re.match(r"^(.+?)\s{1,}(" + MONEY + r")\s*$", row)
        if m and not re.search(r"\b(mva|org|konto|kort|total|sum|betale|bank)\b|\d[./]\d", m[1], re.I):
            name = m[1].strip()
            result["lines"].append(
                dict(
                    name=name,
                    qty=None,
                    unit=None,
                    amount=money(m[2]) / 100,
                    discount=None,
                    kind="deposit" if name.upper().startswith("PANT") else "item",
                )
            )
    if result["lines"]:
        result["confidence"]["lines"] = 0.5
    for row in rows:
        m = re.search(r"(\d+(?:[,.]\d+)?)\s*%\s+(" + MONEY + r")\s+(" + MONEY + r")", row)
        if m:
            result["vat"].append(
                dict(rate=float(m[1].replace(",", ".")), base=money(m[2]) / 100, tax=money(m[3]) / 100)
            )
    return result
