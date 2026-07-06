import asyncio, json
from playwright.async_api import async_playwright
HITS=[]
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True)
        ctx=await b.new_context(storage_state="/data/trumf_state.json", locale="nb-NO",
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36")
        pg=await ctx.new_page()
        def on_resp(r):
            u=r.url
            if ("ngdata.no" in u or "trumf.no/api" in u) and "auth/session" not in u and "gtm" not in u and "cookie" not in u.lower():
                HITS.append((r.request.method, r.status, u.split("?")[0]))
        pg.on("response", on_resp)
        await pg.goto("https://www.trumf.no/", wait_until="domcontentloaded", timeout=45000)
        await pg.wait_for_timeout(3000)
        # accept cookies
        for t in ["Godta alle","Godta","Tillat alle","Aksepter alle"]:
            el=await pg.query_selector(f'button:has-text("{t}")')
            if el:
                try: await el.click(timeout=3000); print("cookies:",t); break
                except: pass
        await pg.wait_for_timeout(1500)
        HITS.clear()
        # now the receipts page
        await pg.goto("https://www.trumf.no/profil/kvitteringer", wait_until="networkidle", timeout=30000)
        await pg.wait_for_timeout(4000)
        for _ in range(3):
            await pg.mouse.wheel(0,2500); await pg.wait_for_timeout(1500)
        # click a receipt row to trigger detail call
        try:
            el=await pg.query_selector('main a, main [role="button"], [class*="kvitter" i] [role="button"], li button')
            if el: await el.click(timeout=4000); await pg.wait_for_timeout(2500)
        except: pass
        print("=== API calls after cookie-accept on kvitteringer ===")
        for m,s,u in sorted(set(HITS)): print(f"  {m} {s} {u}")
        bodytxt=(await pg.inner_text("body"))
        print("page shows receipt-ish content:", any(w in bodytxt.lower() for w in ["kr","kvittering","meny","kiwi","spar","joker"]))
        await pg.screenshot(path="/work/discovery/trumf_kvitt.png", full_page=True)
        await b.close()
asyncio.run(main())
