"""Presentation helpers: NOK formatting (as in Porteføljen), months/chains for the filters, themes."""

import datetime

import themes

NBSP = " "
MONTHS = ["jan", "feb", "mar", "apr", "mai", "jun", "jul", "aug", "sep", "okt", "nov", "des"]


def num(value, decimals=0, sign=False):
    if value is None:
        return "–"
    v = float(value)
    s = f"{abs(v):,.{decimals}f}".replace(",", NBSP).replace(".", ",")
    if float(s.replace(NBSP, "").replace(",", ".")) == 0:
        return s
    if v < 0:
        return "−" + s
    return ("+" + s) if (sign and v > 0) else s


def nok(value, decimals=0, sign=False):
    return "–" if value is None else num(value, decimals, sign) + NBSP + "kr"


def day(value):
    if not value:
        return "–"
    try:
        d = datetime.date.fromisoformat(str(value)[:10])
    except ValueError:
        return str(value)
    return d.strftime("%d.%m.%Y")


def dt(value):
    """'2026-09-04 18:12' -> '04.09.2026 18:12'; date only -> dd.mm.yyyy."""
    if not value:
        return "–"
    s = str(value)
    return day(s) + (f" {s[11:16]}" if len(s) >= 16 else "")


def month_label(ym):
    y, m = ym.split("-")
    return f"{MONTHS[int(m) - 1]} {y}"


FILTERS = {"nok": nok, "num": num, "day": day, "dt": dt, "month_label": month_label}


def context(t, r, c=None):
    """Months (newest first) present in the data, and the themes, for the filter bar/header."""
    months = set()
    for x in (t.get("receipts") or []) if t.get("ok") else []:
        months.add(x["date"][:7])
    for x in (r.get("receipts") or []) if r.get("ok") else []:
        months.add(x["date"][:7])
    for x in (c or {}).get("receipts") or []:
        if x.get("date"):
            months.add(x["date"][:7])
    month_list = [{"ym": ym, "label": month_label(ym)} for ym in sorted(months, reverse=True)]
    return {
        "months": month_list,
        "themes": themes.load_themes(),
        "current_month": month_list[0]["ym"] if month_list else "",
    }
