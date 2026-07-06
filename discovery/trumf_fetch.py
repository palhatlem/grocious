import asyncio, json
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True)
        ctx=await b.new_context(storage_state="/work/data/trumf_state.json", locale="nb-NO",
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
        pg=await ctx.new_page()
        await pg.goto("https://www.trumf.no/", wait_until="domcontentloaded", timeout=45000)
        s=json.loads(await pg.evaluate("async()=>await(await fetch('/api/auth/session')).text()"))
        tok=s.get("accessToken")
        print("access token present:", bool(tok), "| len:", len(tok or ""))
        rq=pg.context.request
        H={"Authorization":"Bearer "+tok,"Accept":"application/json"}
        for label,url in [
            ("SALDO","https://platform-rest-prod.ngdata.no/trumf/husstand/saldo"),
            ("KAMPANJEAVTALE","https://platform-rest-prod.ngdata.no/trumf/kampanjeavtale/beskrivelser"),
        ]:
            r=await rq.get(url, headers=H)
            body=await r.text()
            print(f"\n=== {label} [{r.status}] ===")
            print(body[:600])
        await b.close()
asyncio.run(main())
