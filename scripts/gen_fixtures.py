"""Generate anonymised demo fixtures (deterministic). Run once: .venv/bin/python scripts_gen_fixtures.py"""

import json, random
from pathlib import Path

rng = random.Random(20260906)
FX = Path("app/fixtures")
TRUMF_STORES = [
    ("KIWI 335 Løkkeveien", "Kiwi"),
    ("MENY Stavanger", "Meny"),
    ("SPAR Hillevåg", "Spar"),
    ("JOKER Storhaug", "Joker"),
]
REMA_STORES = ["REMA 1000 Madla", "REMA 1000 Hinna", "REMA 1000 Tasta"]
ITEMS = [
    ("Melk 1 l Tine", 2199),
    ("Brød grovt", 3990),
    ("Egg 12 pk", 4890),
    ("Kaffe Evergood 250 g", 5990),
    ("Banan", 1873),
    ("Kyllingfilet 700 g", 9990),
    ("Tomater", 2450),
    ("Ost Norvegia 500 g", 8990),
    ("Yoghurt 4 pk", 2990),
    ("Pasta 500 g", 1590),
    ("Laks 400 g", 7990),
    ("Agurk", 1290),
    ("Havregryn 1 kg", 2490),
    ("Smør 500 g", 4990),
    ("Eple Pink Lady", 3277),
    ("Toalettpapir 8 pk", 5990),
    ("Pepsi Max 1,5 l", 2990),
    ("Grandiosa", 4490),
    ("Cottage cheese", 2690),
    ("Paprika 3 pk", 3490),
]


def lines(n):
    picked = rng.sample(ITEMS, n)
    out = []
    for name, ore in picked:
        qty = rng.choice([1, 1, 1, 2, 3])
        out.append(
            {
                "name": name,
                "ean": str(rng.randint(7020000000000, 7099999999999)),
                "qty": qty,
                "amount": round(qty * ore / 100, 2),
            }
        )
    return out


def dates(n, start="2026-05-03"):
    y, m, d = map(int, start.split("-"))
    import datetime as dt

    day = dt.date(y, m, d)
    out = []
    while len(out) < n:
        day += dt.timedelta(days=rng.choice([1, 2, 2, 3, 4]))
        out.append(day)
    return out


trumf = []
for i, day in enumerate(dates(28)):
    store, chain = rng.choice(TRUMF_STORES)
    ls = lines(rng.randint(3, 9))
    amount = round(sum(x["amount"] for x in ls), 2)
    bid = f"demo-trumf-{i + 1:03d}"
    trumf.append(
        {
            "id": bid,
            "date": day.isoformat(),
            "store": store,
            "amount": amount,
            "bonus": round(amount * 0.01, 2),
            "chain": chain,
            "hasReceipt": i % 7 != 3,
        }
    )
    json.dump({"id": bid, "lines": ls}, open(FX / "lines" / f"trumf-{bid}.json", "w"), ensure_ascii=False, indent=1)
trumf.sort(key=lambda x: x["date"], reverse=True)
json.dump(
    {
        "ok": True,
        "saldo": 412.37,
        "akkumulert": 6812.0,
        "oppdatert": "2026-09-05",
        "count": len(trumf),
        "receipts": trumf,
        "offers": [
            {"title": "3 % ekstra Trumf på frukt og grønt", "desc": "Gjelder alle Kiwi-butikker ut september."},
            {"title": "Dobbel Trumf-bonus torsdag", "desc": "Meny: dobbel bonus på hele kjøpet torsdag 11.09."},
            {"title": "10 % Trumf på Tine-produkter", "desc": "Spar og Joker, t.o.m. 30.09."},
        ],
    },
    open(FX / "trumf.json", "w"),
    ensure_ascii=False,
    indent=1,
)

rema = []
for i, day in enumerate(dates(22, "2026-05-06")):
    ls = lines(rng.randint(2, 8))
    amount = round(sum(x["amount"] for x in ls), 2)
    tid = 900100 + i
    rema.append(
        {
            "id": tid,
            "date": f"{day.isoformat()} {rng.randint(8, 21):02d}:{rng.randint(0, 59):02d}",
            "store": rng.choice(REMA_STORES),
            "amount": amount,
            "discount": round(rng.choice([0, 0, 12.5, 24.9, 8.0, 35.0]), 2),
        }
    )
    json.dump({"id": tid, "lines": ls}, open(FX / "lines" / f"rema-{tid}.json", "w"), ensure_ascii=False, indent=1)
rema.sort(key=lambda x: x["date"], reverse=True)
json.dump(
    {
        "ok": True,
        "purchaseTotal": round(sum(x["amount"] for x in rema), 2),
        "discountTotal": round(sum(x["discount"] for x in rema), 2),
        "count": len(rema),
        "receipts": rema,
        "offers": [
            {"code": "DEMO-KAFFE", "desc": "Evergood kaffe 250 g – 30 % Æ-rabatt", "activated": True, "img": None},
            {"code": "DEMO-LAKS", "desc": "Laksefilet 400 g – 25 % rabatt", "activated": False, "img": None},
            {"code": "DEMO-BROD", "desc": "Alle grovbrød – 2 for 1", "activated": False, "img": None},
            {"code": "DEMO-FRUKT", "desc": "10 % på all frukt og grønt", "activated": True, "img": None},
        ],
    },
    open(FX / "rema.json", "w"),
    ensure_ascii=False,
    indent=1,
)
print("fixtures:", len(trumf), "trumf,", len(rema), "rema")

# ---- Coop demo archive (uses the real receipt_archive normaliser, so every /coop route works in demo)
import os, sys

sys.path.insert(0, "app")
os.environ["GROCERY_DATA"] = str(FX / "data")
import receipt_archive as ra  # noqa: E402

for i, day in enumerate(dates(6, "2026-07-02")):
    ls = lines(rng.randint(3, 7))
    total = round(sum(x["amount"] for x in ls), 2)
    head = {
        "summaryId": f"A0:/demo-{i}",
        "dateTime": f"{day.day}. {['januar', 'februar', 'mars', 'april', 'mai', 'juni', 'juli', 'august', 'september', 'oktober', 'november', 'desember'][day.month - 1]} {rng.randint(9, 20):02d}:{rng.randint(0, 59):02d}",
        "storeName": rng.choice(["Coop Extra Madla", "Coop Mega Kvadrat", "Obs Forus"]),
        "totalSum": f"{total:.2f}".replace(".", ","),
    }
    details = {
        "receiptId": f"demo-coop-{i}",
        "summary": {
            **head,
            "lines": [
                {
                    "name": x["name"],
                    "quantity": str(x["qty"]) if x["qty"] != 1 else "",
                    "price": f"{x['amount']:.2f}".replace(".", ","),
                    "discount": None,
                }
                for x in ls
            ],
            "purchaseReturn": "1,50",
            "memberDiscount": None,
        },
    }
    r = ra.normalize_coop(
        head,
        details,
        day.year,
        day.month,
        f"Salgskvittering {i} {day.strftime('%d.%m.%Y')}\n {total:.2f} 15% {total * 0.15:.2f} {total * 1.15:.2f}\n",
    )
    d = ra.folder("coop", r["archive_id"])
    doc = ra.original(d, "original", b"%PDF-1.4 demo\n%%EOF\n", "pdf", "application/pdf")
    r.update(documents=[doc], archive_complete=True)
    ra.atomic_json(d / "receipt.json", r)
ra.rebuild("coop")
(FX / "data" / "receipts" / "coop" / "status.json").write_text(
    json.dumps(
        {
            "state": "complete",
            "original_pdf_count": 6,
            "oldest_date": "2026-07-04",
            "newest_date": "2026-07-20",
            "errors": [],
        }
    )
)
print("coop demo archive:", len(list((FX / "data" / "receipts" / "coop").glob("*/receipt.json"))))
