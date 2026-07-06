import asyncio, json
from playwright.async_api import async_playwright
HITS=[]; BEARERS=set()
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True)
        ctx=await b.new_context(storage_state="/data/coop_state.json", locale="nb-NO",
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36")
        pg=await ctx.new_page()
        def on_req(r):
            u=r.url
            if "api.coop.no" in u or ("minside.coop.no/api/" in u):
                a=r.headers.get("authorization","")
                if a.lower().startswith("bearer"): BEARERS.add(a[:40])
                HITS.append((r.method, u.split("?")[0]))
        pg.on("request", on_req)
        await pg.goto("https://minside.coop.no/", wait_until="networkidle", timeout=45000)
        for path in ["/kvitteringer","/kjop","/kuponger","/tilbud","/mine-tilbud","/bonus","/medlemskap","/fordeler"]:
            try:
                r=await pg.goto("https://minside.coop.no"+path, wait_until="networkidle", timeout=25000)
                print(f"{path} -> {r.status if r else '?'}")
                await pg.wait_for_timeout(2500)
            except Exception as e: print(f"{path} ERR {str(e)[:40]}")
        print("\n=== BEARER on api.coop.no calls? ===", "YES" if BEARERS else "NO (server-side proxy)")
        for x in list(BEARERS)[:2]: print("  ", x)
        print("=== API CALLS ===")
        for m,u in sorted(set(HITS)): print(f"  {m} {u}")
        await b.close()
asyncio.run(main())
