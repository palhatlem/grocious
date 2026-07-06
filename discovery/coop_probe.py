import asyncio, json
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True)
        ctx=await b.new_context(locale="nb-NO", user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36")
        pg=await ctx.new_page()
        await pg.goto("https://minside.coop.no/api/auth/login/", wait_until="domcontentloaded", timeout=45000)
        await pg.wait_for_timeout(5000)
        print("URL:", pg.url)
        inputs=[]
        for el in await pg.query_selector_all("input"):
            inputs.append({k: await el.get_attribute(k) for k in ("type","name","id","placeholder","autocomplete")})
        print("INPUTS:", json.dumps(inputs, ensure_ascii=False))
        btns=[]
        for el in await pg.query_selector_all("button, a[role=button], input[type=submit], [class*=social], [class*=idp]"):
            t=((await el.inner_text()) or (await el.get_attribute("value")) or "").strip()
            if t: btns.append(t[:35])
        print("BUTTONS:", json.dumps(btns[:15], ensure_ascii=False))
        print("BODY:", (await pg.inner_text("body"))[:300].replace("\n"," "))
        await b.close()
asyncio.run(main())
