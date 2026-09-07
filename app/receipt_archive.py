"""Additive, private receipt archive. Originals are immutable and content-addressed."""
import csv, datetime as dt, hashlib, io, json, os, re, tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path

SOURCES = {'coop', 'rema', 'trumf', 'inbox'}

def root():
    return Path(os.environ.get('GROCERY_DATA', '/data')) / 'receipts'

def atomic_json(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,tmp=tempfile.mkstemp(prefix='.pending-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(value,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def key(source, source_id):
    if source not in SOURCES:raise ValueError('Unknown source')
    return hashlib.sha256((source+'\0'+str(source_id)).encode()).hexdigest()

def folder(source, rid):
    if source not in SOURCES or not re.fullmatch('[a-f0-9]{64}',rid):raise ValueError('Invalid receipt ID')
    return root()/source/rid

def original(directory, role, content, extension, mimetype):
    digest=hashlib.sha256(content).hexdigest()
    name=role+'-'+digest+'.'+extension
    p=Path(directory)/name;p.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    # Publish only complete files; retrying after a crash cannot see a partial original.
    fd,tmp=tempfile.mkstemp(prefix='.pending-',dir=p.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(content);f.flush();os.fsync(f.fileno())
        try:os.link(tmp,p)
        except FileExistsError:
            if hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise ValueError('Archive checksum mismatch')
    finally:os.unlink(tmp)
    return {'role':role,'filename':name,'sha256':digest,'bytes':len(content),'mimetype':mimetype}

def minor(value):
    if value is None or str(value).strip()=='':return None
    s=re.sub(r'[\s\u00a0\u202f]','',str(value)).replace('NOK','').replace('kr','')
    if ',' in s:s=s.replace('.','').replace(',','.')
    try:return int((Decimal(s)*100).quantize(Decimal('1')))
    except InvalidOperation:return None

def amount(value):
    n=minor(value);return n/100 if n is not None else None

def quantity(value):
    s=str(value or '').strip();m=re.fullmatch(r'(-?\d+(?:[.,]\d+)?)\s*(.*)',s)
    if not m:return None,None
    return str(Decimal(m[1].replace(',','.'))),m[2] or None

def normalize_coop(head, detail, year, month, pdf_text):
    s=detail.get('summary') or {};errors=[]
    display=s.get('dateTime') or head.get('dateTime') or ''
    d=re.match(r'(\d{1,2})\.',display);clock=re.search(r'(\d{2}:\d{2})',display)
    date=f'{year:04d}-{month:02d}-{int(d[1]):02d}' if d else None
    pdf_date=re.search(r'Salgskvittering\s+(\S+)\s+(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}:\d{2})',pdf_text)
    if pdf_date:
        date=f'{pdf_date[4]}-{pdf_date[3]}-{pdf_date[2]}'
        if int(pdf_date[4])!=year or int(pdf_date[3])!=month:errors.append('pdf_period_mismatch')
    if not date:errors.append('date_unparsed')
    lines=[]
    for i,l in enumerate(s.get('lines') or []):
        qty,unit=quantity(l.get('quantity'))
        lines.append({'line_number':i+1,'name':l.get('name'),'ean':l.get('ean'),
          'qty':qty,'quantity_text':l.get('quantity'),'unit':unit,
          'amount':amount(l.get('price')),'amount_minor':minor(l.get('price')),
          'discount':amount(l.get('discount')),'discount_minor':minor(l.get('discount')),
          'kind':'deposit' if re.match(r'^PANT\b',l.get('name') or '',re.I) else 'item','source':l})
    total=minor(s.get('totalSum') or head.get('totalSum'))
    line_sum=sum(l['amount_minor'] for l in lines if l['amount_minor'] is not None)
    if not lines:errors.append('no_structured_lines')
    if any(l['amount_minor'] is None for l in lines):errors.append('line_amount_unparsed')
    if total is None:errors.append('total_unparsed')
    elif line_sum!=total:errors.append('line_total_difference')
    tax=[];section='purchase'
    for l in pdf_text.splitlines():
        if 'Utbytte MVA' in l:section='benefit'
        m=re.fullmatch(r'\s*(-?[\d.,]+)\s+(\d+(?:[.,]\d+)?)%\s+(-?[\d.,]+)\s+(-?[\d.,]+)\s*',l)
        if m:tax.append({'section':section,'base_minor':minor(m[1]),'rate':m[2],'tax_minor':minor(m[3]),'total_minor':minor(m[4])})
    receipt_number=pdf_date[1] if pdf_date else None
    return {'schema_version':1,'parser_version':'coop-1','chain':'coop','id':head['summaryId'],
      'archive_id':key('coop',head['summaryId']),'date':date,'time':pdf_date[5] if pdf_date else (clock[1] if clock else None),
      'timezone':'Europe/Oslo','source_datetime':display,'store':s.get('storeName') or head.get('storeName'),
      'currency':'NOK','amount':total/100 if total is not None else None,'amount_minor':total,
      'bonus':amount(s.get('purchaseReturn')),'discount':None,'source_total_discount':s.get('totalDiscount'),
      'receipt_number':receipt_number,'receipt_id':detail.get('receiptId'),'type':s.get('type'),
      'lines':lines,'tax':tax,'benefits':{k:s.get(k) for k in ('purchaseReturn','memberDiscount','couponDiscount','coopMastercard','totalMemberBenefit','memberBonuses')},
      'document_text':pdf_text,'source':{'head':head,'details':detail},
      'validation':{'issues':errors,'line_sum_minor':line_sum,'difference_minor':None if total is None else line_sum-total},
      'archived_at':dt.datetime.now(dt.timezone.utc).isoformat()}

def read_receipt(source,rid):
    directory = folder(source,rid)
    record = json.loads((directory/'receipt.json').read_text())
    if source == 'inbox':
        from inbox.store import overlay
        record = overlay(record, directory)
    additions = directory / 'user-uploads.json'
    if additions.exists():
        extra = json.loads(additions.read_text())
        record['documents'] = record.get('documents', []) + extra['documents']
        record['linked_from'] = extra['linked_from']
    return record

def summary(source):
    if source not in SOURCES:raise ValueError('Unknown source')
    p=root()/source/'index.json'
    if not p.exists():return {'ok':False,'count':0,'receipts':[],'status':{'state':'not_started'}}
    data=json.loads(p.read_text());status=root()/source/'status.json'
    data['status']=json.loads(status.read_text()) if status.exists() else {}
    images=root()/source/'images_status.json'
    if images.exists():data['image_status']=json.loads(images.read_text())
    return data

def rebuild(source):
    records=[]
    for p in (root()/source).glob('*/receipt.json'):
        r=read_receipt(source,p.parent.name)
        records.append({k:r.get(k) for k in ('archive_id','id','date','time','store','amount','bonus','discount','receipt_id','validation','documents','amount_minor','currency','category','chain','review','intake','linked_to')})
    records.sort(key=lambda x:(x['date'] or '',x['time'] or '',x['id']),reverse=True)
    atomic_json(root()/source/'index.json',{'ok':True,'count':len(records),'receipts':records})
    return len(records)

def document(source,rid,filename):
    r=read_receipt(source,rid)
    entry=next((x for x in r['documents'] if x['filename']==filename),None)
    if not entry or Path(filename).name!=filename:raise FileNotFoundError()
    p=folder(source,rid)/filename
    if hashlib.sha256(p.read_bytes()).hexdigest()!=entry['sha256']:raise ValueError('Archive checksum mismatch')
    return p,entry

def receipt_csv(r):
    out=io.StringIO();w=csv.writer(out)
    w.writerow(['line','kind','name','ean','quantity','unit','quantity_text','amount','discount'])
    for l in r['lines']:w.writerow([l.get(k) for k in ('line_number','kind','name','ean','qty','unit','quantity_text','amount','discount')])
    return out.getvalue()
