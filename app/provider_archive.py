#!/usr/bin/env python3
"""Read-only Rema/Trumf receipt backfill. Preserve source fields and original downloads."""
import argparse,datetime as dt,fcntl,json,os,re,time
from pathlib import Path
from zoneinfo import ZoneInfo
import requests
import receipt_archive as a
import webgui as w

def get(session,url,**kwargs):
    for attempt in range(4):
        try:
            r=session.get(url,timeout=40,**kwargs)
            if r.status_code in (401,403):raise RuntimeError('Source login rejected')
            if r.status_code==429 or r.status_code>=500:
                if attempt<3:time.sleep(2**attempt);continue
            r.raise_for_status();return r
        except requests.RequestException:
            if attempt==3:raise RuntimeError('Source HTTP/network error') from None
            time.sleep(2**attempt)

def field(text,name):
    match=re.search('"'+re.escape(name)+'"\\s*:',text)
    if not match:raise ValueError('Missing source field '+name)
    return json.JSONDecoder().raw_decode(text[match.end():].lstrip())[0]

def trumf_heads(text):
    out={};decoder=json.JSONDecoder()
    for match in re.finditer('"batchId"',text):
        start=text.rfind('{',0,match.start())
        try:obj,_=decoder.raw_decode(text[start:])
        except ValueError:continue
        if 'harKvittering' in obj and 'belop' in obj:out[str(obj['batchId'])]=obj
    if not out:raise RuntimeError('No Trumf receipt list parsed; refuse silent empty import')
    return list(out.values())

def normalize(source,head,detail):
    if source=='rema':
        sid=str(head['id']);when=dt.datetime.fromtimestamp(head['purchaseDate']/1000,ZoneInfo('Europe/Oslo')).isoformat()
        rows=detail if isinstance(detail,list) else detail.get('rows',[])
        lines=[{'line_number':i+1,'name':r.get('productDescription') or r.get('prodtxt1'),'ean':r.get('prodtxt3'),
            'qty':r.get('pieces'),'unit':r.get('unit'),'volume':r.get('volume'),'amount':r.get('amount'),
            'amount_minor':a.minor(r.get('amount')),'discount':r.get('discount'),'deposit':r.get('deposit'),
            'unit_price':r.get('unitPrice'),'source':r} for i,r in enumerate(rows)]
        amount=head.get('amount');store=head.get('storeName');bonus=head.get('bonusPointsDecimal');discount=head.get('discount')
    else:
        sid=str(head['batchId']);when=(detail.get('transaksjonsTidspunkt') or head.get('bonusberegningTidspunkt') or '').replace('$D','')
        if when:
            parsed=dt.datetime.fromisoformat(when.replace('Z','+00:00'))
            when=parsed.astimezone(ZoneInfo('Europe/Oslo')).isoformat() if parsed.tzinfo else when
        rows=detail.get('varelinjer',[])
        lines=[{'line_number':i+1,'name':r.get('produktBeskrivelse'),'ean':None if r.get('ean')=='$undefined' else r.get('ean'),
            'qty':r.get('antall'),'unit':r.get('enhetsType'),'amount':r.get('belop'),'amount_minor':a.minor(r.get('belop')),
            'bonus':r.get('bonus'),'tax_rate':r.get('momsProsent'),'source':r} for i,r in enumerate(rows)]
        amount=head.get('belop');store=head.get('beskrivelse');bonus=head.get('bonus');discount=None
    issues=[]
    if not lines and (source=='rema' or head.get('harKvittering')):issues.append('no_structured_lines')
    if a.minor(amount) is None:issues.append('total_unparsed')
    return {'schema_version':1,'parser_version':source+'-1','chain':source,'id':sid,'archive_id':a.key(source,sid),
        'date':when[:10],'time':when[11:19],'source_datetime':when,'timezone':'Europe/Oslo','store':store,
        'amount':amount,'amount_minor':a.minor(amount),'bonus':bonus,'discount':discount,'currency':'NOK',
        'lines':lines,'source':{'head':head,'details':detail},'validation':{'issues':issues},
        'archived_at':dt.datetime.now(dt.timezone.utc).isoformat()}

def sync(source,incremental=False,limit=None):
    base=a.root()/source;base.mkdir(parents=True,exist_ok=True,mode=0o700)
    with open(base/'sync.lock','w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        status={'state':'running','mode':'incremental' if incremental else 'full','started_at':dt.datetime.now(dt.timezone.utc).isoformat(),'errors':[]}
        a.atomic_json(base/'status.json',status)
        try:
            session=requests.Session()
            if source=='rema':
                session.headers.update(w.rema_headers())
                response=get(session,'https://api.rema.no/v1/bella/transaction/v2/heads');data=response.json();heads=data['transactions']
                a.original(base/'periods','heads',response.content,'json','application/json')
            else:
                session=w.trumf_session()
                response=get(session,'https://www.trumf.no/profil/kvitteringer',headers={'RSC':'1'})
                heads=trumf_heads(response.content.decode('utf-8'))
                a.original(base/'periods','heads',json.dumps(heads,ensure_ascii=False).encode(),'json','application/json')
            ids=[str(h['id'] if source=='rema' else h['batchId']) for h in heads]
            if len(ids)!=len(set(ids)):raise RuntimeError('Duplicate source IDs')
            a.atomic_json(base/'manifest.json',{'ids':ids,'discovered':len(ids),'captured_at':status['started_at']})
            status.update(discovered=len(ids),processed=0);a.atomic_json(base/'status.json',status)
            print(source,'discovered',len(ids),flush=True)
            cutoff=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=60)).date().isoformat()
            for head,sid in zip(heads,ids):
                if limit is not None and status['processed']>=limit:break
                directory=a.folder(source,a.key(source,sid));previous=directory/'receipt.json'
                try:
                    old=json.loads(previous.read_text()) if previous.exists() else None
                    if old and old.get('archive_complete') and old.get('parser_version')==source+'-1' and old['source']['head']==head and (not incremental or old['date']<cutoff):
                        for d in old['documents']:a.document(source,old['archive_id'],d['filename'])
                        status['processed']+=1;continue
                    docs=[a.original(directory,'head',json.dumps(head,ensure_ascii=False).encode(),'json','application/json')]
                    if source=='rema':
                        response=get(session,'https://api.rema.no/v1/bella/transaction/v2/rows/'+sid);detail=response.json()
                        if not isinstance(detail,(dict,list)) or isinstance(detail,dict) and 'rows' not in detail:raise RuntimeError('Unexpected Rema receipt response')
                        docs.append(a.original(directory,'details',response.content,'json','application/json'))
                    elif head.get('harKvittering'):
                        response=get(session,'https://www.trumf.no/profil/kvitteringer/'+sid,headers={'RSC':'1'})
                        text=response.content.decode('utf-8');detail=field(text,'purchaseDetails')
                        if not detail:
                            detail=field(text,'parkingDetails')
                        if not isinstance(detail,dict):raise RuntimeError('Missing Trumf details')
                        if str(detail.get('batchId',sid))!=sid:raise RuntimeError('Trumf receipt ID mismatch')
                        docs.append(a.original(directory,'details',json.dumps(detail,ensure_ascii=False).encode(),'json','application/json'))
                    else:detail={'availability':'Source says no receipt'}
                    record=normalize(source,head,detail)
                    record['images_need_refresh']=bool((old or {}).get('images_need_refresh') or old and old.get('source')!=record['source'])
                    # Keep supplier image versions when refreshing JSON data.
                    docs.extend(d for d in (old or {}).get('documents',[]) if d['role']=='original')
                    record.update(documents=docs,archive_complete=True,original_status='supplier_image' if any(d['role']=='original' for d in docs) else ('not_offered' if source=='trumf' and not head.get('harKvittering') else 'image_not_retrieved' if source=='trumf' else 'raw_data_only'))
                    a.atomic_json(previous,record);status['processed']+=1
                except Exception as e:status['errors'].append({'id':sid,'error':str(e) if isinstance(e,RuntimeError) else type(e).__name__})
                if status['processed']%20==0:
                    a.rebuild(source);a.atomic_json(base/'status.json',status);print(source,'archived',status['processed'],'errors',len(status['errors']),flush=True)
                time.sleep(.15)
            status['archived_count']=a.rebuild(source)
            records=[json.loads(p.read_text()) for p in base.glob('*/receipt.json')]
            dates=sorted(r['date'] for r in records if r['date']);status.update(oldest_date=dates[0] if dates else None,newest_date=dates[-1] if dates else None,validation_issue_count=sum(bool(r['validation']['issues']) for r in records))
            status['state']='sample' if limit is not None else 'complete' if status['processed']==len(ids) and not status['errors'] else 'partial'
            status['finished_at']=dt.datetime.now(dt.timezone.utc).isoformat();a.atomic_json(base/'status.json',status);print(json.dumps(status),flush=True)
            if status['state']=='partial':raise RuntimeError('Incomplete receipt sync')
        except Exception as e:
            status['state']='failed';status['errors'].append({'error':str(e) if isinstance(e,RuntimeError) else type(e).__name__});a.atomic_json(base/'status.json',status);raise

if __name__=='__main__':
    os.umask(0o077);p=argparse.ArgumentParser();p.add_argument('source',choices=['rema','trumf']);p.add_argument('--incremental',action='store_true');p.add_argument('--limit',type=int);args=p.parse_args();sync(args.source,args.incremental,args.limit)
