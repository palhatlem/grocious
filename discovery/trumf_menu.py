import asyncio, json
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True)
        ctx=await b.new_context(locale="nb-NO", user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
        pg=await ctx.new_page()
        await pg.goto("https://www.trumf.no/", wait_until="domcontentloaded", timeout=45000); await pg.wait_for_timeout(4000)
        for t in ["Godta alle","Godta"]:
            el=await pg.query_selector(f'button:has-text("{t}")')
            if el:
                try: await el.click(timeout=3000); break
                except: pass
        await pg.wait_for_timeout(1500)
        el=await pg.query_selector('button:has-text("Logg inn")') or await pg.query_selector('a:has-text("Logg inn")')
        await el.click(timeout=8000); await pg.wait_for_timeout(3500)
        print("URL:", pg.url)
        links=[]
        for el in await pg.query_selector_all('a,button'):
            t=(await el.inner_text() or "").strip(); h=await el.get_attribute("href")
            if t and (h and ("login" in (h or "") or "signin" in (h or "")) or any(w in t.lower() for w in ["privat","person","logg","bedrift"])):
                links.append({"t":t[:30],"href":h})
        print("LOGIN LINKS:", json.dumps(links[:12], ensure_ascii=False))
        await pg.screenshot(path="/work/discovery/menu.png", full_page=True)
        await b.close()
asyncio.run(main())
