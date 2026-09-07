"""Consistent summary cards, calculated from dated purchases rather than lifetime totals."""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo
import receipt_archive as archive


def cards(t, r, c, year=None):
    year = year or datetime.now(ZoneInfo("Europe/Oslo")).year
    result = []
    for source, name, live in [("trumf", "Trumf", t), ("rema", "Rema 1000", r), ("coop", "Coop", c)]:
        stored = c if source == "coop" else archive.summary(source)
        rows = {str(x["id"]): dict(x) for x in live.get("receipts", [])}
        for x in stored.get("receipts", []):
            item = dict(x)
            if source == "trumf":
                full = archive.read_receipt(source, x["archive_id"])
                head = full.get("source", {}).get("head", {})
                item["transaction_category"] = head.get("transaksjonKategori")
                item["bonus_date"] = (head.get("bonusberegningTidspunkt") or item.get("date") or "").replace("$D", "")
                item["savings_detail"] = full.get("source", {}).get("details", {})
            elif source == "rema" and item.get("discount") is None:
                full = archive.read_receipt(source, x["archive_id"])
                adjustments = [l.get("source", {}).get("discount") for l in full.get("lines", [])]
                if adjustments and all(v is not None for v in adjustments):
                    # Rema line discounts are signed price adjustments; heads report positive savings.
                    item["discount"] = float(-sum((Decimal(str(v)) for v in adjustments), Decimal(0)))
            rows[str(x["id"])] = item
        # Bonus withdrawals are ledger entries, not grocery expenditure/receipts.
        purchases = [x for x in rows.values() if x.get("transaction_category") != "CONSUME"]
        dated = [x for x in purchases if (x.get("date") or "").startswith(str(year) + "-")]
        known = bool(live.get("ok") or stored.get("ok"))

        def total(items):
            if not known or any(x.get("amount") is None for x in items):
                return None
            return float(sum((Decimal(str(x["amount"])) for x in items), Decimal(0)))

        bonus_rows = [x for x in purchases if (x.get("bonus_date") or x.get("date") or "").startswith(str(year) + "-")]
        bonus_year = live.get("bonus_year") if live.get("bonus_year_period") == year else None
        bonus_basis = live.get("bonus_year_basis") if bonus_year is not None else None
        if (
            bonus_year is None
            and source in ("rema", "trumf")
            and known
            and bonus_rows
            and all(x.get("bonus") is not None for x in bonus_rows)
        ):
            bonus_year = float(sum((Decimal(str(x["bonus"])) for x in bonus_rows), Decimal(0)))
            bonus_basis = "receipts"
        discounts = coupons = None
        savings_basis = None
        savings_note = None
        if live.get("savings_year_period") == year:
            discounts = live.get("discounts_year")
            coupons = live.get("coupons_year")
            savings_basis = live.get("savings_year_basis")
            savings_note = live.get("savings_year_note")
        elif source == "trumf" and dated:
            parts = []
            valid = True
            for x in dated:
                detail = x.get("savings_detail", {})
                if "varelinjer" not in detail or detail.get("besparelserSum") is None:
                    valid = False
                    break
                items = []
                for line in detail["varelinjer"]:
                    if not isinstance(line.get("besparelser"), list):
                        valid = False
                        break
                    items.extend(line["besparelser"])
                if not valid or any(
                    v.get("type") not in ("OFFER", "TREFORTO", "KNALL", "MARKDOWN", "COUPON") or v.get("belop") is None
                    for v in items
                ):
                    valid = False
                    break
                line_total = sum((Decimal(str(v["belop"])) for v in items), Decimal(0))
                if abs(line_total - Decimal(str(detail["besparelserSum"]))) > Decimal(".01"):
                    valid = False
                    break
                parts.extend(items)
            if valid:

                def savings(coupon):
                    return float(
                        sum(
                            (Decimal(str(v["belop"])) for v in parts if (v["type"] == "COUPON") == coupon), Decimal(0)
                        ).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
                    )

                discounts = savings(False)
                coupons = savings(True)
                savings_basis = "receipts"
                savings_note = (
                    "Summerer Trumfs kategorier på årets kvitteringer: tilbud, faste lavpriskjøp, "
                    "nedprising og 3 for 2. Kuponger holdes separat. Kategoriene betyr ikke "
                    "nødvendigvis medlemspris."
                )
        elif source == "rema" and dated and all(x.get("discount") is not None for x in dated):
            discounts = float(
                sum((Decimal(str(x["discount"])) for x in dated), Decimal(0)).quantize(
                    Decimal(".01"), rounding=ROUND_HALF_UP
                )
            )
            savings_basis = "receipts"
            savings_note = (
                "Samlet rabatt oppgitt på årets Rema-kjøp; eventuell kupongrabatt inngår. Kilden "
                "skiller ikke kuponger pålitelig fra andre tilbud."
            )
        account_balance = live.get("account_balance")
        if account_balance is None:
            account_balance = live.get("saldo") if source == "trumf" else live.get("bonus_balance")
        dates = sorted(x["date"][:10] for x in purchases if x.get("date"))
        result.append(
            {
                "source": source,
                "name": name,
                "year": year,
                "spent_year": total(dated),
                "bonus_year": bonus_year,
                "bonus_year_basis": bonus_basis,
                "bonus_year_note": live.get("bonus_year_note"),
                "bonus_stale": live.get("bonus_stale", False),
                "bonus_updated_at": live.get("bonus_updated_at"),
                "bonus_balance": live.get("saldo") if source == "trumf" else live.get("bonus_balance"),
                "account_balance": account_balance,
                "account_available": live.get("account_available"),
                "account_basis": live.get("account_basis", "provider"),
                "account_observed_at": live.get("account_observed_at"),
                "account_note": live.get("account_note"),
                "discounts_year": discounts,
                "coupons_year": coupons,
                "savings_year_basis": savings_basis,
                "savings_year_note": savings_note,
                "count": len(purchases) if known else None,
                "year_count": len(dated) if known else None,
                "spent_all": total(purchases),
                "bonus_accumulated": live.get("akkumulert")
                if source == "trumf"
                else live.get("bonus_accumulated")
                if source == "rema"
                else None,
                "first_date": dates[0] if dates else None,
                "last_date": dates[-1] if dates else None,
                "error": live.get("err") if not live.get("ok") else None,
            }
        )
    return result
