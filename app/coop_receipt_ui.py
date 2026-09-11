"""Receipt-list benefits from the store's PDF, without changing archive records."""
import re
import receipt_archive as archive


def benefits(record):
    text = record.get('document_text') or ''
    raw = record.get('benefits') or {}

    def printed(label):
        match = re.search(r'^\s*' + re.escape(label) + r':?\s+(-?[\d \u00a0]+[.,]\d{2})\s*$', text, re.M)
        return archive.minor(match[1]) if match else None

    other, member, coupon = (printed(k) for k in ('Andre rabatter', 'Medlemsrabatt', 'Kupongrabatt'))
    # Absent discount subcategories are zero only when the PDF savings section exists.
    discount = other + (member or 0) + (coupon or 0) if other is not None else None
    dividend = printed('Ordinært kjøpeutbytte')
    if dividend is None:
        dividend = archive.minor(raw.get('purchaseReturn'))
    card = printed('Fordel Coop Mastercard')
    if card is None:
        card = archive.minor(raw.get('coopMastercard'))
    parts = []
    for label, amount in [('Kjøpeutbytte', dividend), ('Kortbonus', card)]:
        if amount is not None:
            parts.append({'label': label, 'amount': amount / 100})
    for bonus in raw.get('memberBonuses') or []:
        amount = archive.minor(bonus.get('amount'))
        if amount is not None:
            parts.append({'label': bonus.get('name') or 'Medlemsbonus', 'amount': amount / 100})
    total = sum(archive.minor(p['amount']) for p in parts) / 100 if parts else None
    return {'list_bonus': total, 'list_discount': discount / 100 if discount is not None else None,
            'bonus_parts': parts}


def enrich(summary):
    rows = []
    for row in summary.get('receipts', []):
        try:
            extra = benefits(archive.read_receipt('coop', row['archive_id']))
        except (FileNotFoundError, ValueError):
            extra = {'list_bonus': row.get('bonus'), 'list_discount': None, 'bonus_parts': []}
        rows.append({**row, **extra})
    return {**summary, 'receipts': rows}
