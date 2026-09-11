import datetime as dt
from bonus_sources import account_rollforward


def test_opening_balance_cutoff_and_dedup():
    config = {'balance': 300, 'deposit': 300, 'receipts_from': '2026-09-11', 'observed_at': '2026-09-11'}
    rows = [{'archive_id': 'old', 'date': '2026-09-10', 'list_bonus': 100},
            {'archive_id': 'today', 'date': '2026-09-11', 'list_bonus': 9.14},
            {'archive_id': 'today', 'date': '2026-09-11', 'list_bonus': 9.14},
            {'archive_id': 'future', 'date': '2026-09-12', 'list_bonus': 20}]
    result = account_rollforward(config, rows, dt.date(2026, 9, 11))
    assert result['account_balance'] == 309.14
    assert result['account_available'] is None
    assert '300,00 kr medlemsinnskudd' in result['account_note']
    assert account_rollforward(config, [], dt.date(2026, 9, 11))['account_balance'] == 300


def test_missing_bonus_is_disclosed():
    config = {'balance': 300, 'receipts_from': '2026-09-11', 'observed_at': '2026-09-11'}
    result = account_rollforward(config, [{'archive_id': 'x', 'date': '2026-09-11', 'list_bonus': None}],
                                 dt.date(2026, 9, 11))
    assert 'Bonus mangler på 1' in result['account_note']
