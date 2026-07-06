import asyncio, json, secrets, hashlib, base64, urllib.parse
from playwright.async_api import async_playwright
def pkce():
    v=base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=').decode()
    c=base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b'=').decode()
    return v,c
async def main():
    v,c=pkce()
    q=urllib.parse.urlencode({"response_type":"code","client_id":"android-251010","scope":"all",
        "redirect_uri":"https://ae-appen.appspot.com/redirect/redirect.html",
        "code_challenge":c,"code_challenge_method":"S256","state":secrets.token_hex(8)})
    url="https://id.rema.no/authorization?"+q
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True)
        ctx=await b.new_context(locale="nb-NO", user_agent="Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/124.0 Mobile Safari/537.36")
        pg=await ctx.new_page()
        r=await pg.goto(url, wait_until="domcontentloaded", timeout=45000)
        await pg.wait_for_timeout(5000)
        print("STATUS:", r.status if r else "?"); print("URL_NOW:", pg.url)
        inputs=[]
        for el in await pg.query_selector_all("input"):
            inputs.append({k: await el.get_attribute(k) for k in ("type","name","id","placeholder","autocomplete")})
        print("INPUTS:", json.dumps(inputs, ensure_ascii=False))
        btns=[]
        for el in await pg.query_selector_all("button, a[role=button], input[type=submit]"):
            t=((await el.inner_text()) or (await el.get_attribute("value")) or "").strip()
            if t: btns.append(t[:30])
        print("BUTTONS:", json.dumps(btns[:12], ensure_ascii=False))
        body=(await pg.inner_text("body"))[:400]
        print("BODY_TEXT:", body.replace("\n"," ")[:400])
        await pg.screenshot(path="/work/discovery/rema_login.png", full_page=True)
        await b.close()
asyncio.run(main())
