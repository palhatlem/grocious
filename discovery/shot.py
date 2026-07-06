import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True)
        pg=await (await b.new_context(viewport={"width":1000,"height":1400})).new_page()
        await pg.goto("http://127.0.0.1:3012/", wait_until="networkidle", timeout=30000)
        await pg.wait_for_timeout(2500)
        await pg.screenshot(path="/out/grocious_ui.png", full_page=True)
        await b.close()
asyncio.run(main())
