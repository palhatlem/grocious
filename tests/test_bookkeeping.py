import json
import receipt_archive as archive
from inbox import store
import bookkeeping


def test_registration_overlay_and_change(client, tmp_path, monkeypatch):
    monkeypatch.setenv('GROCERY_DATA', str(tmp_path))
    rid = store.ingest(b'KIWI\n11.09.2026\nTOTALT 25,00 NOK')['rid']
    original = (archive.folder('inbox', rid) / 'receipt.json').read_bytes()
    before_export = store.exports('2026-09', True)
    url = '/api/bookkeeping/inbox/' + rid
    assert client.post(url, json={'registered': True, 'reference': 'test-entry'}).json['state'] == 'registered'
    assert store.exports('2026-09', True) == before_export
    store.correct(rid, {'amount': '30,00'})
    assert bookkeeping.state('inbox', rid)['state'] == 'changed'
    assert client.get('/api/bookkeeping').json[0]['state'] == 'changed'
    assert client.post(url, json={'registered': True}).json['state'] == 'registered'
    assert client.post(url, json={'registered': False}).json['state'] == 'unregistered'
    assert len(json.loads(bookkeeping.path('inbox', rid).read_text())['history']) == 3
    assert (archive.folder('inbox', rid) / 'receipt.json').read_bytes() == original


def test_registration_validation(client, tmp_path, monkeypatch):
    monkeypatch.setenv('GROCERY_DATA', str(tmp_path))
    rid = store.ingest(b'KIWI\nTOTALT 25,00 NOK')['rid']
    url = '/api/bookkeeping/inbox/' + rid
    assert client.post(url, json={'registered': 'yes'}).status_code == 400
    assert client.post(url, json={'registered': True}, headers={'Origin': 'https://wrong.example'}).status_code == 403
    assert client.post('/api/bookkeeping/inbox/bad', json={'registered': True}).status_code == 404
    store.state(rid, 'discarded')
    assert client.post(url, json={'registered': True}).status_code == 409
