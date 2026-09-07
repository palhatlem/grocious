"""Synthetic reproductions of receipt layouts; no real customer documents."""

from inbox.heuristics import money, parse


def test_forwarded_markdown_purchase():
    text = """Forwarded message
Tracking version 2.1
31.99.2026
From: **noreply** <[noreply@finn.no](mailto:noreply@finn.no)>
Date: 03.09.2026
Hei, Demo Person. FINN-kode: 123 Kjøpsdato: 28.08.2026, kl 15:36 Adresse: Eksempelveien
Vare | 140,00 kr
Frakt | 19,00 kr
Totalt | 159,00 kr
"""
    parsed = parse(text, hints={"sender_domain": "gmail.com"})
    assert parsed["store"] == "FINN"
    assert parsed["date"] == "2026-08-28"
    assert parsed["time"] == "15:36"
    assert parsed["total"] == 159 and parsed["currency"] == "NOK"
    assert [line["amount"] for line in parsed["lines"]] == [140, 19]


def test_english_paid_receipt():
    text = """Receipt from Example Cloud
Invoice date August 31, 2026
Date paid September 6, 2026
$125.00 paid on September 6, 2026
Description Amount
Service $125.00
Subtotal $125.00
Total $125.00
Amount due $0.00
Visa - 1234
"""
    parsed = parse(text)
    assert parsed["date"] == "2026-09-06"
    assert parsed["store"] == "Example Cloud"
    assert parsed["total"] == 125 and parsed["currency"] == "USD"
    assert len(parsed["lines"]) == 1
    assert parsed["payment"]["method"] == "Visa"
    assert parsed["payment"]["card_last4"] == "1234"


def test_currencies_grouping_and_table_markup():
    for amount, expected in [("1,234.56", 123456), ("1.234,56", 123456), ("1 234,56", 123456)]:
        assert money(amount) == expected
    assert parse("| **Total** | €1.234,56 |")["total"] == 1234.56
    assert parse("Total\tUSD 1,234.56")["currency"] == "USD"
    assert parse("Currency CAD\nTotal $10.00")["currency"] == "CAD"
    assert parse("Dato 07.09.2026\nTotal €20,00")["currency"] == "EUR"


def test_unknowns_and_ambiguous_dates_stay_unknown():
    assert parse("Contact gmail.com\nTotal 2,00", hints={"sender_domain": "gmail.com"})["store"] is None
    assert parse("Order 2.1\n28.08.2026")["date"] == "2026-08-28"
    assert parse("28.08\nTotal 12,00")["date"] is None
    assert parse("28.08.2026\n29.08.2026")["date"] is None
    assert parse("Date paid\n6 September 2026")["date"] == "2026-09-06"
    assert parse("hello", hints={"sender_domain": "finn.no"})["store"] == "FINN"
    assert parse("hello", hints={"sender_domain": "shop.example.com"})["store"] == "shop.example.com"
