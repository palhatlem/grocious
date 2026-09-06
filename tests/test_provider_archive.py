import io,json,os,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import receipt_archive as a
import provider_archive as p
import webgui as w
class ProvidersTest(unittest.TestCase):
 def test_rsc_nested_and_escaped(self):
  h={'batchId':'abc','belop':12,'harKvittering':True,'nested':{'text':'a}b'}}
  text='0:'+json.dumps({'head':h,'purchaseDetails':{'varelinjer':[{'produktBeskrivelse':'å"}'}],'future':{'x':1}}})
  self.assertEqual(p.trumf_heads(text),[h]);self.assertEqual(p.field(text,'purchaseDetails')['future'],{'x':1})
 def test_rema_all_fields_no_default_quantity(self):
  r=p.normalize('rema',{'id':123,'purchaseDate':1700000000000,'amount':12}, {'rows':[{'productDescription':'Pant','amount':12,'deposit':2,'future':True}], 'transactionPayments':[{'method':'card'}]})
  self.assertIsNone(r['lines'][0]['qty']);self.assertEqual(r['source']['details']['transactionPayments'][0]['method'],'card');self.assertTrue(r['lines'][0]['source']['future'])
 def test_archive_downloads_and_path_rejection(self):
  with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'GROCERY_DATA':tmp}):
   r=p.normalize('rema',{'id':123,'purchaseDate':1700000000000,'amount':12}, {'rows':[{'productDescription':'<script>','amount':12}]});rid=r['archive_id'];folder=a.folder('rema',rid)
   d=a.original(folder,'details',b'{"original":true}','json','application/json');r.update(documents=[d],original_status='raw_data_only');a.atomic_json(folder/'receipt.json',r);a.rebuild('rema')
   c=w.app.test_client();self.assertEqual(c.get('/archive/rema').status_code,200)
   body=c.get('/archive/rema/'+rid).data;self.assertIn(b'&lt;script&gt;',body)
   with c.get('/archive/rema/'+rid+'.zip') as response:
    with zipfile.ZipFile(io.BytesIO(response.data)) as z:self.assertEqual(z.read(d['filename']),b'{"original":true}')
   self.assertEqual(c.get('/archive/rema/'+rid+'/file/unlisted.json').status_code,404)
   self.assertEqual(c.get('/archive/unknown').status_code,404)
