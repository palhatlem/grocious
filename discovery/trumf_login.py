import asyncio, os, json
from playwright.async_api import async_playwright
PHONE=os.environ["TRUMF_PHONE"]; PW=os.environ["TRUMF_PASSWORD"]
SMS_FILE="/work/data/sms_code.txt"
caps={"token_resp":None}
async def click_any(pg, texts):
    for t in texts:
        el=await pg.query_selector(f'button:has-text("{t}")')
        if el and await el.is_enabled():
            try: await el.click(timeout=4000); return t
            except: pass
    return None
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True)
        ctx=await b.new_context(locale="nb-NO", user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
        pg=await ctx.new_page()
        async def on_resp(r):
            if "id.trumf.no/connect/token" in r.url:
                try: caps["token_resp"]=await r.json()
                except: pass
        pg.on("response", on_resp)
        await pg.goto("https://www.trumf.no/", wait_until="domcontentloaded", timeout=45000); await pg.wait_for_timeout(3000)
        rq=pg.context.request
        csrf=(await(await rq.get("https://www.trumf.no/api/auth/csrf")).json())["csrfToken"]
        sr=await rq.post("https://www.trumf.no/api/auth/signin/trumf-personal", form={"csrfToken":csrf,"callbackUrl":"https://www.trumf.no/","json":"true"})
        await pg.goto(sr.url, wait_until="domcontentloaded", timeout=45000); await pg.wait_for_timeout(5000)
        ph=await pg.query_selector('input[type="tel"]') or await pg.query_selector('input:not([type="hidden"])')
        await ph.fill(PHONE)
        await click_any(pg, ["Neste","Fortsett","Logg inn","Videre"]); await pg.wait_for_timeout(4000)
        pwf=await pg.query_selector('input[type="password"]')
        await pwf.fill(PW)
        print("SUBMITTING_PASSWORD (triggers fresh SMS)...", flush=True)
        await click_any(pg, ["Logg inn","Neste","Fortsett"]); await pg.wait_for_timeout(6000)
        await pg.screenshot(path="/work/discovery/sms_step.png")
        if "smsCode" in pg.url or await pg.query_selector('input[autocomplete="one-time-code"]') or await pg.query_selector('input[inputmode="numeric"]'):
            print("SMS_SENT — waiting for code file (up to 6 min)...", flush=True)
            code=None
            for _ in range(120):
                if os.path.exists(SMS_FILE):
                    c=open(SMS_FILE).read().strip()
                    if c: code=c; break
                await asyncio.sleep(3)
            if not code: print("NO_CODE_TIMEOUT"); await b.close(); return
            print("GOT_CODE, entering...", flush=True)
            boxes=await pg.query_selector_all('input[autocomplete="one-time-code"], input[inputmode="numeric"], input[type="tel"]')
            if len(boxes)==1: await boxes[0].fill(code)
            elif len(boxes)>=len(code):
                for i,ch in enumerate(code): await boxes[i].fill(ch)
            else:
                await boxes[0].click(); await pg.keyboard.type(code)
            await click_any(pg, ["Bekreft","Logg inn","Fortsett","Send","Neste","Verifiser"])
        try: await pg.wait_for_url("**www.trumf.no/**", timeout=35000)
        except Exception as e: print("post-sms wait:", e)
        await pg.wait_for_timeout(6000); await pg.screenshot(path="/work/discovery/final.png")
        print("FINAL_URL:", pg.url)
        await ctx.storage_state(path="/work/data/trumf_state.json")
        tr=caps["token_resp"]
        if tr:
            open("/work/data/trumf_tokens.json","w").write(json.dumps(tr))
            print("TOKEN_KEYS:", list(tr.keys()), "HAS_REFRESH:", "refresh_token" in tr, "EXPIRES_IN:", tr.get("expires_in"))
            print("SUCCESS: tokens captured")
        else:
            print("NO_TOKEN_CAPTURED")
        await b.close()
asyncio.run(main())
