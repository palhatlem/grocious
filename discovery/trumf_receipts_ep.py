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
            if ("ngdata.no" in u or "trumf.no/api" in u) and any(k in u.lower() for k in ("transak","kvitter","receipt","kjop","purchase","husstand")):
                HITS.append((r.request.method, r.status, u.split("?")[0]))
        pg.on("response", on_resp)
        for path in ["/profil/kvitteringer", "/profil/kvitteringer/"]:
            try:
                await pg.goto("https://www.trumf.no"+path, wait_until="networkidle", timeout=30000)
                await pg.wait_for_timeout(3500)
            except Exception as e: print(path,"ERR",str(e)[:40])
        print("=== receipt/transaction API calls ===")
        for m,s,u in sorted(set(HITS)): print(f"  {m} {s} {u}")
        await b.close()
asyncio.run(main())
