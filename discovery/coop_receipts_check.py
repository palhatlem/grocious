import asyncio, json
from playwright.async_api import async_playwright
HITS=[]
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True)
        try:
            ctx=await b.new_context(storage_state="/data/coop_state.json", locale="nb-NO",
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36")
        except Exception as e:
            print("no valid state:", e); return
        pg=await ctx.new_page()
        def on_resp(r):
            u=r.url
            if ("minside.coop.no/api" in u or "api.coop.no" in u or "cdcapp" in u or ".pdf" in u or "kvittering" in u.lower() or "receipt" in u.lower() or "history" in u.lower()):
                HITS.append((r.request.method, r.status, u.split("?")[0]))
        pg.on("response", on_resp)
        await pg.goto("https://minside.coop.no/", wait_until="networkidle", timeout=45000)
        # confirm still logged in
        txt=(await pg.inner_text("body"))[:80]
        print("HOME:", txt.replace("\n"," "))
        for path in ["/kjop","/kvitteringer","/kjopshistorikk","/mine-kjop","/historikk","/transaksjoner","/kuponger"]:
            try:
                r=await pg.goto("https://minside.coop.no"+path, wait_until="networkidle", timeout=20000)
                print(f"PAGE {path} -> {r.status if r else '?'}")
                await pg.wait_for_timeout(2000)
            except Exception as e: print(f"PAGE {path} ERR {str(e)[:30]}")
        # any receipt/pdf links on the page?
        links=await pg.eval_on_selector_all("a[href]","els=>els.map(e=>e.href).filter(h=>/kvittering|receipt|kjop|pdf|historikk/i.test(h)).slice(0,8)")
        print("RECEIPT-ISH LINKS:", links)
        print("=== captured receipt/api calls ===")
        for m,s,u in sorted(set(HITS)): print(f"  {m} {s} {u}")
        await b.close()
asyncio.run(main())
