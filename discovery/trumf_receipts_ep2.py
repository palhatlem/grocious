import asyncio
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
            if ("ngdata.no" in u or "trumf.no/api" in u or "graphql" in u.lower()) and "auth/session" not in u and "gtm" not in u:
                HITS.append((r.request.method, r.status, u.split("?")[0]))
        pg.on("response", on_resp)
        await pg.goto("https://www.trumf.no/profil/kvitteringer", wait_until="networkidle", timeout=30000)
        await pg.wait_for_timeout(3000)
        for _ in range(4):
            await pg.mouse.wheel(0, 3000); await pg.wait_for_timeout(1500)
        # click first receipt if any
        try:
            el=await pg.query_selector('[class*="kvitter" i] a, [class*="receipt" i], li a, [role="button"]')
            if el: await el.click(timeout=4000); await pg.wait_for_timeout(2500)
        except: pass
        print("=== ALL api calls on kvitteringer ===")
        for m,s,u in sorted(set(HITS)): print(f"  {m} {s} {u}")
        body=(await pg.inner_text("body"))
        print("PAGE mentions 'kvittering':", body.lower().count("kvittering"), "| sample:", body[:150].replace(chr(10)," "))
        await b.close()
asyncio.run(main())
