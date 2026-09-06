#!/usr/bin/env python3
"""Archive Coop's available receipt history without changing other providers."""
import argparse, base64, datetime as dt, fcntl, hashlib, json, os, subprocess, time
import urllib.request, urllib.parse, urllib.error
from pathlib import Path
import receipt_archive as archive

API='https://coopay.coop.no/user/pay/history/'
DATA=Path(os.environ.get('GROCERY_DATA','/data'))

class Client:
    def __init__(self):
        self.session=DATA/'coop_session.json';self.tokens=DATA/'coop_tokens.json'
        self.headers=json.loads(self.session.read_text())['headers']
        self.headers={k:v for k,v in self.headers.items() if k.lower() not in ('host','accept-encoding','content-length')}
        self.refresh()
    def refresh(self):
        old=json.loads(self.tokens.read_text())
        body=json.dumps({'grant_type':'refresh_token','client_id':'7WrQEdeXwUudArpQVjmZEvrTgVs1WkRr','refresh_token':old['refresh_token']}).encode()
        req=urllib.request.Request('https://login.coop.no/oauth/token',body,{'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=30) as r:new=json.load(r)
        new.setdefault('refresh_token',old['refresh_token']);archive.atomic_json(self.tokens,new)
        self.headers['x-token']=new['access_token']
        archive.atomic_json(self.session,{'headers':self.headers})
        payload=new['access_token'].split('.')[1];claims=json.loads(base64.urlsafe_b64decode(payload+'='*(-len(payload)%4)))
        self.account=hashlib.sha256(claims['sub'].encode()).hexdigest()
    def get(self,path,**params):
        url=API+path+('?' + urllib.parse.urlencode(params) if params else '')
        for attempt in range(4):
            try:
                with urllib.request.urlopen(urllib.request.Request(url,headers=self.headers),timeout=30) as r:
                    body=r.read();ctype=r.headers.get('Content-Type','')
                if 'json' in ctype:
                    j=json.loads(body)
                    if j.get('resultCode')!='SUCCESS':raise RuntimeError('Coop response did not report SUCCESS')
                return body,ctype
            except urllib.error.HTTPError as e:
                if e.code in (401,403):raise RuntimeError('Coop authentication rejected; login/session needs attention') from None
                if e.code not in (429,500,502,503,504) or attempt==3:raise RuntimeError('Coop HTTP '+str(e.code)) from None
            except (TimeoutError,urllib.error.URLError):
                if attempt==3:raise RuntimeError('Coop network timeout') from None
            time.sleep(2**attempt)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int);parser.add_argument('--incremental',action='store_true');args=parser.parse_args()
    os.umask(0o077);base=archive.root()/'coop';base.mkdir(parents=True,exist_ok=True,mode=0o700)
    lock=open(base/'sync.lock','w')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:print('Coop sync already running');return
    previous=json.loads((base/'status.json').read_text()) if (base/'status.json').exists() else {}
    state={'state':'running','started_at':dt.datetime.now(dt.timezone.utc).isoformat(),'errors':[]}
    archive.atomic_json(base/'status.json',state)
    try:
        client=Client()
        if previous.get('account_fingerprint') not in (None,client.account):raise RuntimeError('Different Coop account; separate archive required')
        state['account_fingerprint']=client.account
        raw,_=client.get('dashboard');dash=json.loads(raw)
        archive.original(base/'periods','dashboard',raw,'json','application/json')
        first=dash['oldestPeriod'];last=dash['currentPeriod']
        start=first['year']*12+first['month']-1;end=last['year']*12+last['month']-1
        if args.incremental:start=max(start,end-1)
        state.update({'source_oldest_period':first,'source_current_period':last,'mode':'incremental' if args.incremental else 'full'})
        heads={};periods={}
        for ordinal in range(end,start-1,-1):
            y,m=divmod(ordinal,12);m+=1
            raw,_=client.get('month',year=y,month=m);data=json.loads(raw)
            archive.original(base/'periods',f'{y:04d}-{m:02d}',raw,'json','application/json')
            purchases=data['purchases']
            ids=[p['summaryId'] for p in purchases]
            if len(ids)!=len(set(ids)):state['errors'].append({'period':f'{y:04d}-{m:02d}','error':'duplicate_source_ids'})
            total=sum(archive.minor(p.get('totalSum')) or 0 for p in purchases)
            reported=archive.minor(data.get('aggregatedTotalSum'))
            periods[f'{y:04d}-{m:02d}']={'count':len(purchases),'ids':ids,'reported_total_minor':reported,'listed_total_minor':total}
            if reported is not None and total!=reported:state['errors'].append({'period':f'{y:04d}-{m:02d}','error':'period_total_difference','difference_minor':total-reported})
            for h in purchases:
                sid=h['summaryId']
                if sid in heads and heads[sid][1:]!=(y,m):raise RuntimeError('Source ID occurs in multiple periods')
                heads[sid]=(h,y,m)
            time.sleep(.1)
        manifest={'periods':periods,'discovered':len(heads),'captured_at':dt.datetime.now(dt.timezone.utc).isoformat()}
        archive.atomic_json(base/'manifest.json',manifest)
        if not args.incremental and args.limit is None:archive.atomic_json(base/'full_manifest.json',manifest)
        state['discovered']=len(heads);state['processed']=0;archive.atomic_json(base/'status.json',state)
        print('Discovered',len(heads),'receipts in',len(periods),'months',flush=True)
        for sid,(head,year,month) in heads.items():
            if args.limit is not None and state['processed']>=args.limit:break
            rid=archive.key('coop',sid);directory=archive.folder('coop',rid)
            try:
                existing=directory/'receipt.json'
                # Full backfills resume from verified complete artifacts. Daily overlap refreshes details.
                if existing.exists() and not args.incremental:
                    old=json.loads(existing.read_text())
                    if old.get('archive_complete') and old.get('parser_version')=='coop-1':
                        for doc in old['documents']:archive.document('coop',rid,doc['filename'])
                        state['processed']+=1;continue
                raw,_=client.get('details',summaryId=sid);details=json.loads(raw)
                receipt_id=details.get('receiptId')
                docs=[archive.original(directory,'head',json.dumps(head,ensure_ascii=False).encode(),'json','application/json'),archive.original(directory,'details',raw,'json','application/json')]
                text='';pdf_present=False
                if receipt_id:
                    pdf,ctype=client.get('receipt.pdf',receiptId=receipt_id)
                    if not pdf.startswith(b'%PDF-'):raise RuntimeError('Coop did not return a PDF')
                    doc=archive.original(directory,'original',pdf,'pdf','application/pdf');docs.append(doc);pdf_present=True
                    result=subprocess.run(['pdftotext','-layout',str(directory/doc['filename']),'-'],capture_output=True,timeout=30)
                    if result.returncode:raise RuntimeError('PDF text extraction failed')
                    text=result.stdout.decode('utf-8',errors='replace')
                    docs.append(archive.original(directory,'text',result.stdout,'txt','text/plain; charset=utf-8'))
                record=archive.normalize_coop(head,details,year,month,text)
                record['documents']=docs;record['archive_complete']=pdf_present
                if not pdf_present:record['validation']['issues'].append('source_pdf_missing')
                archive.atomic_json(directory/'receipt.json',record)
                state['processed']+=1
            except Exception as e:
                state['errors'].append({'id':sid,'error':str(e) if isinstance(e,RuntimeError) else type(e).__name__})
            if state['processed']%25==0:
                archive.rebuild('coop');archive.atomic_json(base/'status.json',state)
                print('Archived',state['processed'],'/',len(heads),'errors',len(state['errors']),flush=True)
            time.sleep(.1)
        state['archived_count']=archive.rebuild('coop')
        records=[json.loads(p.read_text()) for p in base.glob('*/receipt.json')]
        state['original_pdf_count']=sum(r.get('archive_complete',False) for r in records)
        state['validation_issue_count']=sum(bool(r.get('validation',{}).get('issues')) for r in records)
        dates=sorted(r['date'] for r in records if r.get('date'))
        state['oldest_date']=dates[0] if dates else None;state['newest_date']=dates[-1] if dates else None
        state['state']='sample' if args.limit is not None else ('complete' if not state['errors'] and state['processed']==len(heads) and all(archive.read_receipt('coop',archive.key('coop',sid)).get('archive_complete') for sid in heads) else 'partial')
        state['finished_at']=dt.datetime.now(dt.timezone.utc).isoformat()
        if state['state']=='complete' and not args.incremental:
            archive.atomic_json(base/'full_sync.json',{k:v for k,v in state.items() if k!='account_fingerprint'})
        full=base/'full_sync.json'
        if full.exists():state['last_full_sync']=json.loads(full.read_text())
        archive.atomic_json(base/'status.json',state)
        print(json.dumps({k:v for k,v in state.items() if k not in ('errors','account_fingerprint')},ensure_ascii=False),flush=True)
        if state['state']=='partial':raise RuntimeError('Coop sync incomplete; inspect status.json')
    except Exception as e:
        state['state']='failed';state['errors'].append({'error':str(e) if isinstance(e,RuntimeError) else type(e).__name__})
        archive.rebuild('coop');archive.atomic_json(base/'status.json',state);raise

if __name__=='__main__':main()
