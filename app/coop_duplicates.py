"""Coop can reissue a summary ID for the same receipt after a membership change.

Collapse only matching receipt identities with identical original PDF checksums
and totals. All archived records remain addressable; this is a read model.
"""


def identity(row):
    originals = [d for d in row.get('documents', []) or []
                 if d.get('role') == 'original' and d.get('mimetype') == 'application/pdf']
    if (not row.get('receipt_id') or len(originals) != 1 or not originals[0].get('sha256')
            or not row.get('date') or row.get('amount_minor') is None):
        return None
    return (row['receipt_id'], originals[0]['sha256'], row['date'],
            row['amount_minor'], row.get('currency'))


def collapse(records, previous=()):
    # Keep an established representative stable across subsequent archive refreshes.
    preferred = {identity(r): r['archive_id'] for r in previous if r.get('duplicate_aliases')}
    groups = {}
    for row in records:
        key = identity(row) or ('archive', row['archive_id'])
        groups.setdefault(key, []).append(row)
    result = []
    for key, rows in groups.items():
        if len(rows) == 1:
            result.append(rows[0])
            continue
        rows = sorted(rows, key=lambda r: (r['archive_id'] == preferred.get(key), str(r['id'])), reverse=True)
        canonical = dict(rows[0])
        canonical['duplicate_aliases'] = [
            {'archive_id': r['archive_id'], 'id': r['id']} for r in rows[1:]
        ]
        result.append(canonical)
    result.sort(key=lambda r: (r.get('date') or '', r.get('time') or '', str(r['id'])), reverse=True)
    return result
