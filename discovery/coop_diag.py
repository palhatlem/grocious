import asyncio, os, json
from playwright.async_api import async_playwright
USER=os.environ["COOP_USER"]
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True)
        ctx=await b.new_context(locale="nb-NO", user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36")
        pg=await ctx.new_page()
        await pg.goto("https://minside.coop.no/api/auth/login/", wait_until="domcontentloaded", timeout=45000)
        await pg.wait_for_timeout(4000)
        for t in ["Godta","Aksepter","Tillat alle","Godta alle","OK"]:
            el=await pg.query_selector(f'button:has-text("{t}")')
            if el:
                try: await el.click(timeout=2500); break
                except: pass
        u=await pg.query_selector('#username') or await pg.query_selector('input[name="username"]')
        await u.fill(USER)
        # press Enter first (most reliable), else force-click Fortsett
        try:
            await u.press("Enter"); await pg.wait_for_timeout(1500)
        except: pass
        if await pg.query_selector('#username'):  # still on identifier page -> force click
            el=await pg.query_selector('button[type=submit]') or await pg.query_selector('button:has-text("Fortsett")')
            if el:
                try: await el.click(timeout=4000, force=True)
                except Exception as e: print("click err:", e)
        await pg.wait_for_timeout(6000)
        print("URL:", pg.url)
        inputs=[]
        for el in await pg.query_selector_all("input"):
            vis=await el.is_visible()
            inputs.append({"type":await el.get_attribute("type"),"name":await el.get_attribute("name"),"vis":vis})
        print("INPUTS:", json.dumps([i for i in inputs if i["type"] not in ("hidden",)], ensure_ascii=False))
        btns=[]
        for el in await pg.query_selector_all("button,a[role=button]"):
            t=((await el.inner_text()) or "").strip()
            if t and await el.is_visible(): btns.append(t[:30])
        print("BUTTONS:", json.dumps(btns[:10], ensure_ascii=False))
        print("BODY:", (await pg.inner_text("body"))[:400].replace("\n"," "))
        await pg.screenshot(path="/work/discovery/coop_diag.png", full_page=True)
        await b.close()
asyncio.run(main())
