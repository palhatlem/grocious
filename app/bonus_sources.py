"""Provider-reported bonus metrics. Do not confuse annual earnings with account balance."""

import datetime as dt, fcntl, json, os, urllib.request, urllib.error
from pathlib import Path
from decimal import Decimal
import receipt_archive as archive


def coop_metrics(raw):
    year = raw.get("year")
    members = raw.get("perMembershipBenefits")
    if raw.get("resultCode") != "SUCCESS" or not isinstance(members, list) or not members:
        raise ValueError("Incomplete Coop benefits response")
    benefits = [m["benefitsForYear"] for m in members]
    if any(b.get("year") != year or b.get("memSavingsInMemberAccountVal") is None for b in benefits):
        raise ValueError("Coop benefit period mismatch")
    # This is earnings allocated to the member account for the stated year, NOT its balance.
    earned = sum((Decimal(str(b["memSavingsInMemberAccountVal"])) for b in benefits), Decimal(0))
    groups = {}
    for b in benefits:
        for group in b.get("memSavingsPerBenefitGroup", []):
            key = str(group["groupId"])
            groups.setdefault(key, Decimal(0))
            groups[key] += Decimal(str(group["benefitAmountVal"]))
    return {
        "discounts_year": float(groups["4"]) if "4" in groups else None,
        "coupons_year": float(groups["5"]) if "5" in groups else None,
        "savings_year_period": year,
        "savings_year_basis": "provider",
        "savings_year_note": (
            "Coops MedlemsKupp og kuponger vises hver for seg. Opptjent kjøpeutbytte/bonus er ikke prisrabatt."
        ),
        "bonus_year": float(earned),
        "bonus_year_period": year,
        "bonus_year_basis": "provider" if len(benefits) == 1 else "provider_sum",
        "bonus_year_note": (
            "Coops årsoversikt: kjøpeutbytte og bonus til medlemskonto. Prisrabatter og "
            "kuponger er ikke bonusopptjening."
        ),
        "bonus_balance": None,
        "bonus_accumulated": None,
        "bonus_balance_note": (
            "Coop viser medlemskontoen via separat innlogging på secure.coop.no. Saldo er ikke bekreftet i app-API-et."
        ),
        "bonus_source": "https://cdcapp.coop.no/user/benefits/overview",
    }


def coop_data():
    data = Path(os.environ.get("GROCERY_DATA", "/data"))
    path = data / "bonus" / "coop.json"
    old = {}
    try:
        old = json.loads(path.read_text())
    except (OSError, ValueError):
        pass
    if not (data / "coop_session.json").exists():
        return {"bonus_error": "Coop session unavailable"}
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(data / "receipts" / "coop" / "sync.lock", "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {**old.get("metrics", {}), "bonus_stale": True}
        try:
            headers = json.loads((data / "coop_session.json").read_text())["headers"]
            url = "https://cdcapp.coop.no/user/benefits/overview"
            for attempt in range(2):
                try:
                    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as response:
                        raw = json.load(response)
                    break
                except urllib.error.HTTPError as e:
                    if attempt or e.code not in (401, 403):
                        raise
                    from coop_archive import Client

                    headers = Client().headers
            metrics = coop_metrics(raw)
            metrics["bonus_updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
            archive.atomic_json(path, {"metrics": metrics, "source": raw})
            return metrics
        except Exception:
            return {**old.get("metrics", {}), "bonus_stale": True, "bonus_error": "Could not refresh Coop bonus"}


def account_rollforward(record, rows, today=None):
    """A user-supplied opening balance plus unique receipt earnings, not bank availability."""
    today = today or dt.datetime.now(dt.timezone.utc).astimezone().date()
    start = dt.date.fromisoformat(record["receipts_from"])
    opening = archive.minor(record["balance"])
    deposit = archive.minor(record.get("deposit", 0))
    seen, earned, missing = set(), 0, 0
    for row in rows:
        rid = row.get("archive_id")
        date = (row.get("date") or "")[:10]
        if not rid or rid in seen or not start.isoformat() <= date <= today.isoformat():
            continue
        seen.add(rid)
        bonus = archive.minor(row.get("list_bonus"))
        if bonus is None:
            missing += 1
        else:
            earned += bonus
    def nok(value):
        return f"{value / 100:.2f}".replace(".", ",")
    note = (
        f"Saldoen inkluderer {nok(deposit)} kr medlemsinnskudd, som tilbakebetales ved avslutning. "
        f"Startsaldo {nok(opening)} kr før handel {start.strftime('%d.%m.%Y')}, oppgitt av deg, "
        f"pluss {nok(earned)} kr bonus fra kvitteringer fra og med denne datoen. "
        "Kjøpeutbytte og kortbonus telles samlet; prisrabatter er ikke med. "
        "Dette er beregnet saldo inkludert opptjent bonus, ikke bekreftet disponibelt beløp. "
        "Ved uttak eller andre kontobevegelser må startsaldoen oppdateres."
    )
    if missing:
        note += f" Bonus mangler på {missing} kvitteringer."
    return {"account_balance": (opening + earned) / 100, "account_available": None,
            "account_basis": "opening_plus_receipts", "account_observed_at": record["observed_at"],
            "account_note": note}


def account_observation(source):
    """Optional user-reported snapshot or explicitly configured receipt roll-forward."""
    if source != "coop":
        return {}
    path = Path(os.environ.get("GROCERY_DATA", "/data")) / "bonus" / "coop-account-observation.json"
    try:
        record = json.loads(path.read_text())
        if record.get("mode") == "opening_plus_receipts":
            from coop_receipt_ui import enrich
            return account_rollforward(record, enrich(archive.summary("coop"))["receipts"])
        return {
            "account_balance": record["balance"],
            "account_available": record["available"],
            "account_basis": "user_reported",
            "account_observed_at": record["observed_at"],
            "account_note": (
                "Oppgitt av brukeren etter BankID-innlogging. Ikke automatisk oppdatert. "
                "Differansen mellom saldo og disponibelt er ikke klassifisert som bonus eller "
                "depositum."
            ),
        }
    except (OSError, ValueError, KeyError):
        return {}
