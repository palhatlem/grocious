import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import receipt_archive as a
import webgui

class ArchiveTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'GROCERY_DATA':self.tmp.name});self.env.start()
  self.head={'summaryId':'A0:/sample','dateTime':'4. September 16:52','storeName':'Testbutikk','totalSum':'24,00'}
  self.details={'receiptId':'sample','summary':{**self.head,'unknown_future_field':{'keep':True},'lines':[{'name':'Vare','quantity':'','price':'20,00','discount':None},{'name':'PANT','quantity':'','price':'2,00'},{'name':'PANT','quantity':'','price':'2,00'}]}}
 def tearDown(self):self.env.stop();self.tmp.cleanup()
 def record(self):
  r=a.normalize_coop(self.head,self.details,2026,9,'Salgskvittering 12 04.09.2026 16:52\n 4.00 0% 0.00 4.00\n')
  d=a.folder('coop',r['archive_id']);doc=a.original(d,'original',b'%PDF-test','pdf','application/pdf');r.update(documents=[doc],archive_complete=True);a.atomic_json(d/'receipt.json',r);a.rebuild('coop');return r
 def test_money_quantity_and_missing_values(self):
  self.assertEqual(a.minor('1\u00a0234,50'),123450);self.assertEqual(a.minor('-2,50'),-250)
  self.assertIsNone(a.minor(''));self.assertEqual(a.quantity('0,325 kg'),('0.325','kg'));self.assertEqual(a.quantity(''),(None,None))
 def test_preserves_repeated_deposits_and_unknown_fields(self):
  r=self.record();self.assertEqual(len(r['lines']),3);self.assertEqual(r['validation']['issues'],[])
  self.assertIsNone(r['lines'][0]['qty']);self.assertTrue(r['source']['details']['summary']['unknown_future_field']['keep'])
  self.assertEqual(r['tax'][0]['base_minor'],400)
 def test_idempotency_and_checksum(self):
  r=self.record();d=a.folder('coop',r['archive_id']);first=r['documents'][0]
  again=a.original(d,'original',b'%PDF-test','pdf','application/pdf');self.assertEqual(first,again)
  a.original(d,'original',b'%PDF-new-version','pdf','application/pdf');self.assertEqual(len(list(d.glob('original-*'))),2)
  (d/first['filename']).write_bytes(b'broken')
  with self.assertRaises(ValueError):a.document('coop',r['archive_id'],first['filename'])
 def test_bad_total_is_flagged_without_losing_data(self):
  self.details['summary']['totalSum']='25,00';r=self.record();self.assertIn('line_total_difference',r['validation']['issues']);self.assertEqual(len(r['lines']),3)
 def test_coop_routes_and_combined_export(self):
  r=self.record();client=webgui.app.test_client()
  with patch.object(webgui,'trumf_data',return_value={'ok':False}),patch.object(webgui,'rema_data',return_value={'ok':False}):
   self.assertEqual(client.get('/').status_code,200)
   self.assertEqual(client.get('/coop/receipt/'+r['archive_id']).status_code,200)
   with client.get('/coop/receipt/'+r['archive_id']+'.pdf') as response:self.assertEqual(response.data,b'%PDF-test')
   full=client.get('/api/export/2026-09.json?lines=1').get_json();self.assertEqual(full['count'],1);self.assertEqual(full['total'],24)
   self.assertTrue(full['receipts'][0]['source']['details']['summary']['unknown_future_field']['keep'])
   self.assertEqual(client.get('/coop/receipt/not-a-valid-id.json').status_code,404)
 def test_existing_download_contract_unchanged(self):
  client=webgui.app.test_client()
  with patch.object(webgui,'trumf_lines',return_value=[{'name':'old','ean':'123','qty':1,'amount':10}]):
   j=client.get('/trumf/receipt/old-id.json').get_json();self.assertEqual(j['id'],'old-id');self.assertEqual(j['lines'][0]['ean'],'123')

if __name__=='__main__':unittest.main()
