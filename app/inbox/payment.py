"""Printed payment identifiers, without bank-account inference."""

import re

FIELDS = ("method", "card_last4", "terminal", "auth_code")


def normalize(value):
    if value is None:
        return dict.fromkeys(FIELDS)
    # Interpretations stored before the structured-payment contract used a string.
    if isinstance(value, str):
        return dict.fromkeys(FIELDS) | {"method": value}
    if not isinstance(value, dict) or set(value) - set(FIELDS):
        raise ValueError("Ugyldig betalingsinformasjon")
    result = {k: value.get(k) for k in FIELDS}
    if any(v is not None and (not isinstance(v, str) or len(v) > 200) for v in result.values()):
        raise ValueError("Ugyldig betalingsinformasjon")
    if result["card_last4"] is not None and not re.fullmatch(r"\d{4}", result["card_last4"]):
        raise ValueError("Kortreferansen skal være fire siffer")
    return result


def parse(text):
    result = normalize(None)
    method = re.search(r"\b(BankAxept|Visa|Mastercard|Vipps|Kontant)\b", text, re.I)
    if method:
        result["method"] = method[1]
    suffixes = set(re.findall(r"(?:\*|[xX•]){2,}[\s*-]*(\d{4})(?!\d)", text))
    if len(suffixes) == 1:
        result["card_last4"] = suffixes.pop()
    for field, label in [
        ("terminal", r"terminal(?:\s*(?:id|nr\.?))?"),
        ("auth_code", r"(?:autorisasjon(?:skode)?|auth(?:\s*code)?|godkjenningskode)"),
    ]:
        match = re.search(r"^\s*" + label + r"\s*[:=]\s*([\w-]+)\s*$", text, re.I | re.M)
        if match:
            result[field] = match[1]
    return result
