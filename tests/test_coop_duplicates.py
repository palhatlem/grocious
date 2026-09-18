import copy
import json

import bookkeeping
import receipt_archive as archive
import webgui


def receipt(summary_id, receipt_id='purchase', pdf=b'%PDF-original'):
    head = {'summaryId': summary_id, 'dateTime': '11. September 12:00',
            'storeName': 'Testbutikk', 'totalSum': '25,00'}
    detail = {'receiptId': receipt_id,
              'summary': {**head, 'lines': [{'name': 'Vare', 'quantity': '1', 'price': '25,00'}]}}
    row = archive.normalize_coop(head, detail, 2026, 9, '')
    directory = archive.folder('coop', row['archive_id'])
    row['documents'] = [archive.original(directory, 'original', pdf, 'pdf', 'application/pdf')]
    archive.atomic_json(directory / 'receipt.json', row)
    return row


def test_same_purchase_once_in_views_exports_and_bonus_inputs(client, tmp_path, monkeypatch):
    monkeypatch.setenv('GROCERY_DATA', str(tmp_path))
    monkeypatch.setattr(webgui, 'trumf_data', lambda: {'ok': False})
    monkeypatch.setattr(webgui, 'rema_data', lambda: {'ok': False})
    old = receipt('A27:/purchase')
    new = receipt('A0:/purchase')
    originals = {r['archive_id']: (archive.folder('coop', r['archive_id']) / 'receipt.json').read_bytes()
                 for r in (old, new)}
    # An index produced by an older version must also be safe before the next sync.
    archive.atomic_json(archive.root() / 'coop/index.json', {'ok': True, 'count': 2, 'receipts': [old, new]})
    summary = client.get('/api/archive/coop').json
    assert summary['count'] == 1
    assert summary['archive_record_count'] == 2
    assert summary['duplicate_count'] == 1
    chosen = summary['receipts'][0]['archive_id']
    assert len(webgui.coop_dashboard()['receipts']) == 1
    html = client.get('/').data.decode()
    assert sum(html.count('data-lines="/coop/receipt/' + r['archive_id'] + '.json"') for r in (old, new)) == 1
    for suffix in ('', '?lines=1'):
        export = client.get('/api/export/2026-09.json' + suffix).json
        assert export['count'] == 1
        assert export['total'] == 25
    assert archive.rebuild('coop') == 2  # physical sync progress is unchanged
    assert archive.summary('coop')['receipts'][0]['archive_id'] == chosen
    for row in (old, new):
        rid = row['archive_id']
        assert (archive.folder('coop', rid) / 'receipt.json').read_bytes() == originals[rid]
        with client.get('/coop/receipt/' + rid + '.pdf') as response:
            assert response.data == b'%PDF-original'


def test_dedup_requires_identity_pdf_and_total_agreement(tmp_path, monkeypatch):
    monkeypatch.setenv('GROCERY_DATA', str(tmp_path))
    first = receipt('first')
    receipt('different-purchase', receipt_id='other')
    receipt('different-pdf', pdf=b'%PDF-revised')
    for name, changes in [('missing-identity', {'receipt_id': None}),
                          ('different-total', {'amount_minor': 2600}),
                          ('different-date', {'date': '2026-09-12'}),
                          ('missing-pdf', {'documents': []})]:
        row = copy.deepcopy(first)
        row.update(id=name, archive_id=archive.key('coop', name), **changes)
        archive.atomic_json(archive.folder('coop', row['archive_id']) / 'receipt.json', row)
    archive.rebuild('coop')
    assert archive.summary('coop')['count'] == 7


def test_representative_stays_stable_when_another_alias_arrives(tmp_path, monkeypatch):
    monkeypatch.setenv('GROCERY_DATA', str(tmp_path))
    receipt('A27:/purchase')
    receipt('A0:/purchase')
    archive.rebuild('coop')
    chosen = archive.summary('coop')['receipts'][0]['archive_id']
    receipt('Z99:/purchase')
    archive.rebuild('coop')
    row = archive.summary('coop')['receipts'][0]
    assert row['archive_id'] == chosen
    assert len(row['duplicate_aliases']) == 2


def test_registration_survives_alias_and_can_be_cleared(client, tmp_path, monkeypatch):
    monkeypatch.setenv('GROCERY_DATA', str(tmp_path))
    new = receipt('A0:/purchase')
    archive.rebuild('coop')
    old_url = '/api/bookkeeping/coop/' + new['archive_id']
    assert client.post(old_url, json={'registered': True, 'reference': 'ledger-entry'}).status_code == 200
    receipt('A27:/purchase')
    archive.rebuild('coop')
    canonical = archive.summary('coop')['receipts'][0]['archive_id']
    assert canonical != new['archive_id']  # marker was on the hidden copy
    markers = client.get('/api/bookkeeping').json
    assert len(markers) == 1
    assert markers[0]['state'] == 'registered'
    assert markers[0]['reference'] == 'ledger-entry'
    assert client.post(old_url, json={'registered': False}).json['state'] == 'unregistered'
    assert bookkeeping.state('coop', canonical)['state'] == 'unregistered'
    marker = json.loads(bookkeeping.path('coop', canonical).read_text())
    assert len(marker['history']) == 2
    assert client.post(old_url, json={'registered': True}).json['state'] == 'registered'
    p = archive.folder('coop', canonical) / 'receipt.json'
    row = json.loads(p.read_text())
    row['lines'][0]['name'] = 'Corrected description'
    archive.atomic_json(p, row)
    assert bookkeeping.state('coop', canonical)['state'] == 'changed'
