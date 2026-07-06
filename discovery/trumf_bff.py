import asyncio, json
from playwright.async_api import async_playwright
HITS=[]
INT=("trumf.no/api","api.trumf.no","ngdata.no","husstand","medlem","bonus","kvittering","tilbud","kupong","offer","transaks")
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True)
        ctx=await b.new_context(storage_state="/work/data/trumf_state.json", locale="nb-NO",
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
        pg=await ctx.new_page()
        async def on_resp(r):
            u=r.url
            if any(k in u.lower() for k in INT) and "_next" not in u and "auth/session" not in u:
                HITS.append((r.request.method, r.status, u.split("?")[0]))
        pg.on("response", on_resp)
        # confirm logged in
        await pg.goto("https://www.trumf.no/", wait_until="networkidle", timeout=45000)
        sess=await pg.evaluate("async()=>{try{return await(await fetch('/api/auth/session')).text()}catch(e){return 'ERR'}}")
        print("LOGGED_IN_AS:", sess[:200])
        for path in ["/kvitteringer","/bruk-bonus","/bonus","/fordeler","/tilbud","/mine-tilbud","/kuponger","/profil","/innsikt"]:
            try:
                r=await pg.goto("https://www.trumf.no"+path, wait_until="networkidle", timeout=25000)
                print(f"PAGE {path} -> {r.status if r else '?'}")
                await pg.wait_for_timeout(2500)
            except Exception as e:
                print(f"PAGE {path} ERR {str(e)[:50]}")
        uniq=sorted(set(HITS))
        print("\n=== API ENDPOINTS HIT (method status url) ===")
        for m,s,u in uniq: print(f"  {m} {s} {u}")
        await b.close()
asyncio.run(main())
