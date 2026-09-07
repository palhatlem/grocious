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
MONEY = r"-?(?:\d{1,3}(?:[ ,.\u00a0]\d{3})+|\d+)[,.]\d{2}"
CURRENCY = r"(?:NOK|USD|EUR|GBP|CAD|AUD|SEK|DKK|kr|US\$|CA\$|AU\$|[$€£])"
MONTHS = {
    name: i
    for i, name in enumerate(
        (
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ),
        1,
    )
}
DOMAIN_STORES = {"finn.no": "FINN", "anthropic.com": "Anthropic"}
MAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "outlook.com",
    "hotmail.com",
    "icloud.com",
    "yahoo.com",
    "proton.me",
    "protonmail.com",
    "pm.me",
    "stripe.com",
}
RULES_VERSION = "rules-2"


def dates_in(text):
    candidates = []
    for match in re.finditer(r"(?<![\d.])(\d{1,2})[./](\d{1,2})[./](\d{4}|\d{2})(?![\d.])", text):
        year = int(match[3])
        candidates.append((year + 2000 if year < 100 else year, int(match[2]), int(match[1])))
    for match in re.finditer(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text):
        candidates.append(tuple(map(int, match.groups())))
    months = "|".join(MONTHS)
    for match in re.finditer(r"\b(" + months + r")\s+(\d{1,2})(?:st|nd|rd|th)?[,]?\s+(20\d{2})\b", text, re.I):
        candidates.append((int(match[3]), MONTHS[match[1].lower()], int(match[2])))
    for match in re.finditer(r"\b(\d{1,2})\s+(" + months + r")[,]?\s+(20\d{2})\b", text, re.I):
        candidates.append((int(match[3]), MONTHS[match[2].lower()], int(match[1])))
    result = set()
    for values in candidates:
        try:
            result.add(dt.date(*values).isoformat())
        except ValueError:
            pass
    return result


def receipt_date(rows):
    # Prefer an explicitly labelled purchase/payment date over invoice or due dates.
    labels = (r"kjøpsdato|date paid|payment date|paid on", r"kvitteringsdato|receipt date|dato|date")
    for label in labels:
        found = set()
        for i, row in enumerate(rows):
            matched = re.search(r"\b(?:" + label + r")\b", row, re.I)
            if matched:
                tail = row[matched.end() :]
                found.update(dates_in(tail) or dates_in(rows[i + 1] if i + 1 < len(rows) else ""))
        if found:
            return next(iter(found)) if len(found) == 1 else None
    found = dates_in("\n".join(rows))
    return next(iter(found)) if len(found) == 1 else None


def currency_in(text):
    codes = set(re.findall(r"\b(NOK|USD|EUR|GBP|CAD|AUD|SEK|DKK)\b", text, re.I))
    codes = {code.upper() for code in codes}
    if len(codes) == 1:
        return codes.pop()
    if len(codes) > 1:
        return None
    symbols = set()
    for token, code in (("€", "EUR"), ("£", "GBP"), ("$", "USD")):
        if token in text:
            symbols.add(code)
    if re.search(r"\bkr\b", text, re.I):
        symbols.add("NOK")
    return symbols.pop() if len(symbols) == 1 else None


def store_hint(rows, sender_domain):
    for row in rows:
        heading = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", row)
        heading = re.sub(r"[#*_\[\]]", "", heading).strip()
        if heading.casefold() in ("finn", "anthropic"):
            return {"finn": "FINN", "anthropic": "Anthropic"}[heading.casefold()]
    for row in rows:
        if re.match(r"^Anthropic(?:,|\s|$)", row, re.I):
            return "Anthropic"
        if re.match(r"^(?:From|Fra):", row, re.I):
            for domain, merchant in DOMAIN_STORES.items():
                if re.search(r"@" + re.escape(domain) + r"(?=[>\]\s)]|$)", row, re.I):
                    return merchant
    for row in rows:
        labelled = re.match(r"^(?:receipt from|kvittering fra|merchant|butikk)\s*[:|]?\s+(.{2,80})$", row, re.I)
        if labelled and "@" not in labelled[1]:
            return labelled[1].strip()
    domain = (sender_domain or "").lower().strip()
    if domain in DOMAIN_STORES:
        return DOMAIN_STORES[domain]
    # A forwarding mailbox or payment processor is not evidence of the merchant.
    if domain in MAIL_DOMAINS or not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", domain):
        return None
    return domain


def money(value):
    if value is None or str(value).strip() == "":
        return None
    s = str(value).strip().replace("\u00a0", "").replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        n = Decimal(s)
        if not n.is_finite() or abs(n) > 100000000:
            raise ValueError("Ugyldig beløp")
        return int((n * 100).quantize(Decimal("1")))
    except ArithmeticError as e:
        raise ValueError("Ugyldig beløp") from e


def parse(text, received_at=None, hints=None):
    # html2text tables and bold headings retain Markdown delimiters.
    rows = [s.strip().strip("|#* ").strip() for s in text.splitlines() if s.strip()]
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
    if not result["store"]:
        hint = store_hint(rows, (hints or {}).get("sender_domain"))
        if hint:
            result["store"] = hint
            result["confidence"]["store"] = 0.5
    result["date"] = receipt_date(rows)
    if result["date"]:
        result["confidence"]["date"] = 0.9
    clock = re.search(r"\b([012]\d:[0-5]\d)\b", text)
    if clock and int(clock[1][:2]) < 24:
        result["time"] = clock[1]
    result["currency"] = currency_in(text)
    total_row = len(rows)
    for keyword in (r"å\s+betale", "totalt", "total", "amount paid", "sum", "bank", "kort", "amount due"):
        matches = []
        for i, row in enumerate(rows):
            m = re.search(
                r"^\s*"
                + keyword
                + r"\b[|:*\s=]*(?:"
                + CURRENCY
                + r")?\s*("
                + MONEY
                + r")[|*\s]*(?:"
                + CURRENCY
                + r")?\s*$",
                row,
                re.I,
            )
            if m:
                matches.append((i, m[1]))
        if matches:
            total_row, value = matches[-1]
            result["total"] = money(value) / 100
            row_currency = currency_in(rows[total_row])
            explicit = re.search(r"\b(NOK|USD|EUR|GBP|CAD|AUD|SEK|DKK)\b|[€£]", rows[total_row], re.I)
            if explicit or result["currency"] is None:
                result["currency"] = row_currency or result["currency"]
            result["confidence"]["total"] = 0.9 if keyword not in ("bank", "kort") else 0.5
            break
    for row in rows[:total_row]:
        m = re.match(r"^(.+?)[|\s]+(?:" + CURRENCY + r")?\s*(" + MONEY + r")\s*(?:" + CURRENCY + r")?\s*$", row)
        if m and not re.search(
            r"\b(mva|org|konto|kort|total|subtotal|sum|betale|bank|paid|due)\b|\d[./]\d", m[1], re.I
        ):
            name = m[1].strip(" |*")
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
