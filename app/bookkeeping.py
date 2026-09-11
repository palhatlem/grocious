"""Manual registration markers, independent of receipt originals and exports."""
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from flask import Blueprint, abort, jsonify, request
import receipt_archive as archive

bp = Blueprint('bookkeeping', __name__)


def path(source, rid):
    archive.folder(source, rid)  # validate source and content-addressed ID
    return Path(os.environ.get('GROCERY_DATA', '/data')) / 'bookkeeping' / source / (rid + '.json')


def fingerprint(record):
    fields = ('date', 'store', 'amount_minor', 'amount', 'currency', 'lines', 'payment')
    return hashlib.sha256(json.dumps({k: record.get(k) for k in fields}, sort_keys=True,
                                    ensure_ascii=False).encode()).hexdigest()


def state(source, rid):
    p = path(source, rid)
    if not p.exists():
        return {'state': 'unregistered'}
    marker = json.loads(p.read_text())
    if not marker.get('registered'):
        return {'state': 'unregistered'}
    current = archive.read_receipt(source, rid)
    return {'state': 'registered' if marker['fingerprint'] == fingerprint(current) else 'changed',
            'registered_at': marker['registered_at'], 'reference': marker.get('reference', '')}


@bp.get('/api/bookkeeping')
def listing():
    result = []
    for source in sorted(archive.SOURCES):
        for row in archive.summary(source)['receipts']:
            rid = row['archive_id']
            result.append({'source': source, 'id': str(row['id']), 'archive_id': rid, **state(source, rid)})
    return jsonify(result)


@bp.post('/api/bookkeeping/<source>/<rid>')
def save(source, rid):
    if not request.is_json:
        abort(415)
    origin = request.headers.get('Origin')
    if request.headers.get('Sec-Fetch-Site') == 'cross-site' or (origin and urlsplit(origin).netloc != request.host):
        abort(403)
    data = request.get_json()
    if not isinstance(data, dict) or type(data.get('registered')) is not bool:
        return jsonify(error='Velg registrert eller ikke registrert.'), 400
    reference = data.get('reference', '')
    if not isinstance(reference, str) or len(reference) > 500:
        return jsonify(error='Referansen kan være opptil 500 tegn.'), 400
    try:
        target = path(source, rid)
        record = archive.read_receipt(source, rid)
    except (ValueError, FileNotFoundError):
        abort(404)
    if record.get('review', {}).get('state') in ('linked', 'discarded') and data['registered']:
        return jsonify(error='Koblede eller forkastede poster registreres ikke separat.'), 409
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with target.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        previous = json.loads(target.read_text()) if target.exists() else {}
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        entry = {'registered': data['registered'], 'registered_at': now,
                 'reference': reference.strip(), 'fingerprint': fingerprint(record)}
        entry['history'] = previous.get('history', []) + [{k: v for k, v in entry.items()}]
        archive.atomic_json(target, entry)
    return jsonify(state(source, rid))
