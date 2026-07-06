import asyncio, secrets, hashlib, base64, urllib.parse
from playwright.async_api import async_playwright
def pkce():
    v=base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=').decode()
    return v, base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b'=').decode()
async def main():
    v,c=pkce()
    q=urllib.parse.urlencode({"response_type":"code","client_id":"7WrQEdeXwUudArpQVjmZEvrTgVs1WkRr",
      "redirect_uri":"https://login.coop.no/android/no.coop.members/callback","audience":"https://api.coop.no",
      "scope":"openid profile offline_access","code_challenge":c,"code_challenge_method":"S256","state":secrets.token_hex(8)})
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True); ctx=await b.new_context(locale="nb-NO")
        pg=await ctx.new_page()
        r=await pg.goto("https://login.coop.no/authorize?"+q, wait_until="domcontentloaded", timeout=45000)
        await pg.wait_for_timeout(4000)
        print("STATUS", r.status if r else "?"); print("URL", pg.url[:80])
        u=await pg.query_selector('#username, input[name="username"]')
        print("LOGIN FORM PRESENT:", bool(u))
        print("BODY:", (await pg.inner_text("body"))[:150].replace(chr(10)," "))
        await b.close()
asyncio.run(main())
