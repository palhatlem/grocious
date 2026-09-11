from coop_receipt_ui import benefits


def test_discount_excludes_bonus_and_uses_pdf_not_allocated_rounding():
    r = {'document_text': ('Andre rabatter 26.70\nKupongrabatt: 30.00\n'
                           'Ordinært kjøpeutbytte 6.06\nFordel Coop Mastercard 3.08'),
         'benefits': {}, 'source_total_discount': '62,76'}
    b = benefits(r)
    assert b['list_discount'] == 56.70
    assert b['list_bonus'] == 9.14
    assert len(b['bonus_parts']) == 2


def test_pdf_member_discount_overrides_different_api_value():
    b = benefits({'document_text': 'Andre rabatter 9.80\nMedlemsrabatt: 34.64\nOrdinært kjøpeutbytte 2.16',
                  'benefits': {'memberDiscount': '38,84'}})
    assert b['list_discount'] == 44.44
    assert b['list_bonus'] == 2.16


def test_unknown_discount_and_extra_member_bonus():
    b = benefits({'benefits': {'purchaseReturn': '7,19', 'coopMastercard': '7,31',
                              'memberBonuses': [{'name': 'Frukt', 'amount': '9,92'}]}})
    assert b['list_discount'] is None
    assert b['list_bonus'] == 24.42
