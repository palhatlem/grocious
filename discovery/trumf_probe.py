import asyncio, json
from playwright.async_api import async_playwright

CAPTURE = ("ngdata.no","/auth","/login","/token","/oauth","identity","oidc","husstand","medlem","api")

async def main():
    reqs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True)
        ctx=await b.new_context(locale="nb-NO", user_agent=("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"))
        pg=await ctx.new_page()
        pg.on("request", lambda r: reqs.append((r.method,r.url)))
        await pg.goto("https://www.trumf.no/", wait_until="domcontentloaded", timeout=45000)
        await pg.wait_for_timeout(4000)
        # accept cookies
        for t in ["Godta alle","Tillat alle","Aksepter alle","Godta","Tillat valgte","Kun nødvendige"]:
            el=await pg.query_selector(f'button:has-text("{t}")')
            if el:
                try: await el.click(timeout=4000); print("cookie-accepted:",t); break
                except: pass
        await pg.wait_for_timeout(2000)
        # click login
        el=await pg.query_selector('button:has-text("Logg inn")') or await pg.query_selector('a:has-text("Logg inn")')
        if el:
            try: await el.click(timeout=8000); print("clicked Logg inn")
            except Exception as e: print("click err:",e)
        await pg.wait_for_timeout(7000)
        print("URL_NOW:", pg.url)
        # dump inputs on whatever page/modal we're on
        inputs=[]
        for el in await pg.query_selector_all("input"):
            inputs.append({k: await el.get_attribute(k) for k in ("type","name","id","placeholder","autocomplete")})
        print("INPUTS:", json.dumps(inputs, ensure_ascii=False))
        # any buttons visible (next/continue)
        btns=[]
        for el in await pg.query_selector_all("button"):
            t=(await el.inner_text() or "").strip()
            if t: btns.append(t[:25])
        print("BUTTONS:", json.dumps(btns[:12], ensure_ascii=False))
        await pg.screenshot(path="/work/discovery/trumf_login.png", full_page=True)
        auth=sorted(set(u for m,u in reqs if any(h in u.lower() for h in CAPTURE) and "_next/static" not in u and "gtm" not in u))
        print("AUTH/API REQUESTS:")
        for u in auth[:30]: print("  ",u)
        await b.close()
asyncio.run(main())
