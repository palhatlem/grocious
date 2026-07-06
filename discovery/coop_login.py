import asyncio, os, json
from playwright.async_api import async_playwright
USER=os.environ["COOP_USER"]; PW=os.environ["COOP_PASSWORD"]; SMS="/data/coop_sms.txt"
caps={"api_bearer":None}
async def click_any(pg, texts):
    for t in texts:
        el=await pg.query_selector(f'button:has-text("{t}")') or await pg.query_selector(f'button[type=submit]')
        if el and await el.is_enabled():
            try: await el.click(timeout=4000); return t
            except: pass
    return None
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True)
        ctx=await b.new_context(locale="nb-NO", user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36")
        pg=await ctx.new_page()
        def on_req(r):
            if "api.coop.no" in r.url:
                a=r.headers.get("authorization")
                if a and a.lower().startswith("bearer"): caps["api_bearer"]=a
        pg.on("request", on_req)
        await pg.goto("https://minside.coop.no/api/auth/login/", wait_until="domcontentloaded", timeout=45000)
        await pg.wait_for_timeout(4000)
        for t in ["Godta","Aksepter","Tillat alle","Godta alle","OK"]:
            el=await pg.query_selector(f'button:has-text("{t}")')
            if el:
                try: await el.click(timeout=2500); break
                except: pass
        u=await pg.query_selector('#username') or await pg.query_selector('input[name="username"]')
        await u.fill(USER)
        print("SUBMIT_IDENTIFIER...", flush=True)
        try: await u.press("Enter")
        except: pass
        await pg.wait_for_selector('input[name="password"]:visible', timeout=15000)
        await pg.wait_for_timeout(1200)
        pwf=await pg.query_selector('input[name="password"]')
        await pwf.fill(PW)
        print("SUBMIT_PASSWORD...", flush=True)
        try: await pwf.press("Enter")
        except: pass
        await pg.wait_for_timeout(2000)
        if await pg.query_selector('input[name="password"]:visible'):
            await click_any(pg, ["Logg inn","Fortsett"])
        await pg.wait_for_timeout(6000)
        (await pg.screenshot(path="/work/discovery/coop_s2.png"))
        # MFA (SMS) challenge?
        if ("mfa" in pg.url.lower()) or ("challenge" in pg.url.lower()) or (await pg.query_selector('input[name="code"]')):
            print("MFA_SMS_SENT — waiting for code file /data/coop_sms.txt (6 min)...", flush=True)
            await pg.screenshot(path="/work/discovery/coop_mfa.png")
            _ins=await pg.query_selector_all("input:not([type=hidden])")
            _desc=[]
            for _e in _ins:
                if await _e.is_visible(): _desc.append({"type":await _e.get_attribute("type"),"name":await _e.get_attribute("name"),"maxlength":await _e.get_attribute("maxlength")})
            print("MFA_INPUTS:", json.dumps(_desc, ensure_ascii=False), flush=True)
            code=None
            for _ in range(120):
                if os.path.exists(SMS):
                    x=open(SMS).read().strip()
                    if x: code=x; break
                await asyncio.sleep(3)
            if not code:
                print("NO_CODE_TIMEOUT")
            else:
                print("GOT_CODE, entering...", flush=True)
                boxes=[e for e in await pg.query_selector_all('input[inputmode="numeric"], input[autocomplete="one-time-code"], input[name="code"], input#code, input[type="tel"], input[type="text"]') if await e.is_visible()]
                if len(boxes)==1:
                    await boxes[0].fill(code)
                elif len(boxes)>=len(code):
                    for i,ch in enumerate(code): await boxes[i].fill(ch)
                elif boxes:
                    await boxes[0].click(); await pg.keyboard.type(code)
                await pg.wait_for_timeout(1000)
                if boxes:
                    try: await boxes[-1].press("Enter")
                    except: pass
                await click_any(pg, ["Fortsett","Bekreft","Logg inn","Verifiser","Send"])
                await pg.wait_for_timeout(3000)
                await pg.screenshot(path="/work/discovery/coop_mfa_after.png")
        try: await pg.wait_for_url("**minside.coop.no/**", timeout=30000)
        except Exception as e: print("post-login wait:", e)
        await pg.wait_for_timeout(6000)
        await pg.screenshot(path="/work/discovery/coop_s3.png")
        print("FINAL_URL:", pg.url)
        # try to get token via session endpoint
        for ep in ["/api/auth/session/","/api/auth/me/","/api/auth/token/","/api/auth/access-token/"]:
            try:
                t=await pg.evaluate(f"async()=>{{try{{const r=await fetch('{ep}');return r.status+' '+(await r.text()).slice(0,200)}}catch(e){{return 'ERR'}}}}")
                print(f"SESSION {ep}: {t}")
            except: pass
        await ctx.storage_state(path="/data/coop_state.json")
        print("API_BEARER_SEEN:", (caps["api_bearer"] or "")[:30])
        if caps["api_bearer"]:
            open("/data/coop_bearer.txt","w").write(caps["api_bearer"])
            print("SUCCESS: captured api.coop.no bearer")
        await b.close()
asyncio.run(main())
