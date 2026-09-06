import unittest
from unittest.mock import patch
import dashboard_stats as d
class DashboardStatsTest(unittest.TestCase):
 def test_year_deduplication_and_bonus_withdrawal(self):
  t={'ok':True,'saldo':17,'receipts':[{'id':'a','date':'2026-02-01','amount':20},{'id':'cash','date':'2026-02-02','amount':100,'transaction_category':'CONSUME'}]}
  stored={'ok':True,'receipts':[{'id':'a','archive_id':'a','date':'2026-02-01','amount':20},{'id':'old','archive_id':'old','date':'2025-12-01','amount':30}]}
  with patch.object(d.archive,'summary',side_effect=lambda source:stored if source=='trumf' else {'ok':False}),patch.object(d.archive,'read_receipt',return_value={'source':{'head':{'transaksjonKategori':'ACCRUAL'}}}):
   t,r,c=d.cards(t,{'ok':False},{'ok':False},2026)
  self.assertEqual(t['spent_year'],20);self.assertEqual(t['spent_all'],50);self.assertEqual(t['count'],2);self.assertEqual(t['bonus_balance'],17)
  self.assertIsNone(r['spent_year']);self.assertIsNone(c['bonus_balance'])
 def test_missing_balance_is_not_earned_bonus(self):
  with patch.object(d.archive,'summary',return_value={'ok':False}):
   _,_,c=d.cards({'ok':False},{'ok':False},{'ok':True,'receipts':[{'id':'x','date':'2026-01-01','amount':10.10,'bonus':5}]},2026)
  self.assertEqual(c['spent_year'],10.10);self.assertIsNone(c['bonus_balance'])
 def test_provider_year_total_preferred_over_receipts(self):
  with patch.object(d.archive,'summary',return_value={'ok':False}):
   _,_,c=d.cards({'ok':False},{'ok':False},{'ok':True,'bonus_year':77,'bonus_year_period':2026,'bonus_year_basis':'provider','receipts':[{'id':'x','date':'2026-01-01','amount':10,'bonus':5}]},2026)
  self.assertEqual(c['bonus_year'],77);self.assertEqual(c['bonus_year_basis'],'provider');self.assertIsNone(c['bonus_balance'])
 def test_receipt_fallback_is_labeled_and_missing_not_zero(self):
  with patch.object(d.archive,'summary',return_value={'ok':False}):
   t,r,_=d.cards({'ok':True,'receipts':[{'id':'a','date':'2026-01-01','amount':10,'bonus':1.25}]},{'ok':True,'receipts':[{'id':'b','date':'2026-01-01','amount':10}]},{'ok':False},2026)
  self.assertEqual(t['bonus_year'],1.25);self.assertEqual(t['bonus_year_basis'],'receipts');self.assertIsNone(r['bonus_year'])
 def test_coop_benefits_are_not_all_discounts_or_balance(self):
  from bonus_sources import coop_metrics
  m=coop_metrics({'resultCode':'SUCCESS','year':2026,'perMembershipBenefits':[{'benefitsForYear':{'year':2026,'totalSumVal':120.50,'memSavingsInMemberAccountVal':35.25}}]})
  self.assertEqual(m['bonus_year'],35.25);self.assertEqual(m['bonus_year_period'],2026);self.assertIsNone(m['bonus_balance']);self.assertIsNone(m['bonus_accumulated'])
 def test_coop_separates_member_deals_and_coupons(self):
  from bonus_sources import coop_metrics
  m=coop_metrics({'resultCode':'SUCCESS','year':2026,'perMembershipBenefits':[{'benefitsForYear':{'year':2026,'memSavingsInMemberAccountVal':30,'memSavingsPerBenefitGroup':[{'groupId':'4','benefitAmountVal':50},{'groupId':'5','benefitAmountVal':20}]}}]})
  self.assertEqual(m['discounts_year'],50);self.assertEqual(m['coupons_year'],20);self.assertEqual(m['bonus_year'],30)
 def test_rema_unsplit_discount_is_not_zero_coupons(self):
  with patch.object(d.archive,'summary',return_value={'ok':False}):
   _,r,_=d.cards({'ok':False},{'ok':True,'receipts':[{'id':'a','date':'2026-01-01','amount':10,'discount':2.50}]},{'ok':False},2026)
  self.assertEqual(r['discounts_year'],2.5);self.assertIsNone(r['coupons_year'])
 def test_trumf_coupon_split_and_unrounded_components(self):
  stored={'ok':True,'receipts':[{'id':'a','archive_id':'a','date':'2026-01-01','amount':10}]}
  raw={'source':{'head':{'transaksjonKategori':'ACCRUAL'},'details':{'besparelserSum':1.01,'varelinjer':[{'besparelser':[{'type':'OFFER','belop':.3333},{'type':'OFFER','belop':.3333},{'type':'COUPON','belop':.34}]}]}}}
  with patch.object(d.archive,'summary',side_effect=lambda s:stored if s=='trumf' else {'ok':False}),patch.object(d.archive,'read_receipt',return_value=raw):
   t,_,_=d.cards({'ok':False},{'ok':False},{'ok':False},2026)
  self.assertEqual(t['discounts_year'],.67);self.assertEqual(t['coupons_year'],.34)
 def test_user_account_snapshot_kept_separate_from_bonus(self):
  with patch.object(d.archive,'summary',return_value={'ok':False}):
   _,_,c=d.cards({'ok':False},{'ok':False},{'ok':True,'account_balance':450.50,'account_available':150.50,'account_basis':'user_reported'},2026)
  self.assertEqual(c['account_balance'],450.50);self.assertEqual(c['account_available'],150.50);self.assertIsNone(c['bonus_balance']);self.assertEqual(c['account_basis'],'user_reported')
 def test_rema_missing_header_uses_signed_line_discount(self):
  stored={'ok':True,'receipts':[{'id':'a','archive_id':'a','date':'2026-01-01','amount':10,'discount':None}]}
  with patch.object(d.archive,'summary',side_effect=lambda s:stored if s=='rema' else {'ok':False}),patch.object(d.archive,'read_receipt',return_value={'lines':[{'source':{'discount':-3.25}}]}):
   _,r,_=d.cards({'ok':False},{'ok':False},{'ok':False},2026)
  self.assertEqual(r['discounts_year'],3.25);self.assertIsNone(r['coupons_year'])
