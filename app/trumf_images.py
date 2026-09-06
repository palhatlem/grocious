#!/usr/bin/env python3
"""Archive JPGs produced by Trumf's own download button, without re-rendering locally."""
import asyncio,datetime as dt,fcntl,json,os,tempfile
from pathlib import Path
from urllib.parse import urlencode
from playwright.async_api import async_playwright
import receipt_archive as a

async def main():
    os.umask(0o077);base=a.root()/'trumf';base.mkdir(parents=True,exist_ok=True,mode=0o700)
    with open(base/'sync.lock','w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Trumf raw sync is still running')
        records=[json.loads(p.read_text()) for p in base.glob('*/receipt.json')]
        eligible=[r for r in records if r['source']['head'].get('harKvittering')]
        pending=[r for r in eligible if r.get('images_need_refresh') or not any(d['role']=='original' for d in r['documents'])]
        for r in eligible:
            for d in r['documents']:
                if d['role']=='original':a.document('trumf',r['archive_id'],d['filename'])
        state={'state':'running','expected':len(eligible),'already_archived':len(eligible)-len(pending),'downloaded':0,'errors':[],'started_at':dt.datetime.now(dt.timezone.utc).isoformat()}
        a.atomic_json(base/'images_status.json',state);print('Trumf supplier images pending',len(pending),flush=True)
        if pending:
            async with async_playwright() as p:
                browser=await p.chromium.launch(headless=True,args=['--no-sandbox'])
                ctx=await browser.new_context(storage_state=str(Path(os.environ.get('GROCERY_DATA','/data'))/'trumf_state.json'),accept_downloads=True,locale='nb-NO')
                # Set necessary-only cookie preference once in this disposable context.
                page=await ctx.new_page();await page.goto('https://www.trumf.no/profil/kvitteringer',wait_until='domcontentloaded',timeout=60000)
                consent=page.get_by_role('button',name='Kun nødvendige',exact=True)
                try:await consent.click(timeout=15000)
                except Exception:pass
                await page.close()
                queue=asyncio.Queue()
                for r in pending:queue.put_nowait(r)
                async def worker():
                    page=await ctx.new_page()
                    while not queue.empty():
                        r=queue.get_nowait();sid=r['id'];head=r['source']['head'];details=r['source']['details']
                        try:
                            stamp=(head.get('transaksjonsTidspunkt') or details.get('transaksjonsTidspunkt') or '').replace('$D','')
                            if not stamp:raise RuntimeError('Missing supplier timestamp')
                            url='https://www.trumf.no/trumf-profil/kvitteringer/'+sid+'?'+urlencode({'transactionType':'ACCRUAL','timestamp':stamp,'description':head.get('beskrivelse','')})
                            await page.goto(url,wait_until='domcontentloaded',timeout=60000)
                            button=page.locator('#downloadReceipt');await button.wait_for(timeout=30000)
                            async with page.expect_download(timeout=60000) as info:await button.click()
                            download=await info.value
                            number=details.get('kvitteringsId') or details.get('ordreId') or details.get('parkeringId')
                            if number and not download.suggested_filename.endswith('-'+str(number)+'.jpg'):raise RuntimeError('Supplier filename receipt ID mismatch')
                            with tempfile.TemporaryDirectory() as tmp:
                                path=Path(tmp)/'receipt.jpg';await download.save_as(str(path));raw=path.read_bytes()
                            if not raw.startswith(b'\xff\xd8\xff') or not raw.endswith(b'\xff\xd9'):raise RuntimeError('Supplier download is not complete JPEG')
                            directory=a.folder('trumf',r['archive_id']);doc=a.original(directory,'original',raw,'jpg','image/jpeg')
                            doc.update(supplier_filename=download.suggested_filename,provenance='Trumf website downloadReceipt button',captured_at=dt.datetime.now(dt.timezone.utc).isoformat())
                            r['documents']=[d for d in r['documents'] if d['filename']!=doc['filename']]+[doc];r['images_need_refresh']=False;r['original_status']='supplier_image';a.atomic_json(directory/'receipt.json',r);state['downloaded']+=1
                        except Exception as e:state['errors'].append({'id':sid,'error':str(e) if isinstance(e,RuntimeError) else type(e).__name__})
                        a.atomic_json(base/'images_status.json',state)
                        if (state['downloaded']+len(state['errors']))%10==0:
                            a.rebuild('trumf');print('Supplier JPGs',state['downloaded'],'errors',len(state['errors']),flush=True)
                        await asyncio.sleep(.3)
                    await page.close()
                await asyncio.gather(worker(),worker());await browser.close()
        a.rebuild('trumf');state['state']='complete' if not state['errors'] else 'partial';state['archived_images']=state['already_archived']+state['downloaded'];state['finished_at']=dt.datetime.now(dt.timezone.utc).isoformat();a.atomic_json(base/'images_status.json',state);print(json.dumps(state),flush=True)
        if state['errors']:raise RuntimeError('Some Trumf images were not retrieved; see images_status.json')

if __name__=='__main__':asyncio.run(main())
