import asyncio, os, json, secrets, hashlib, base64, urllib.parse
from playwright.async_api import async_playwright
PHONE=os.environ["REMA_PHONE"]; SMS="/data/rema_sms.txt"
caps={"code":None}
def pkce():
    v=base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=').decode()
    c=base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b'=').decode()
    return v,c
async def click_any(pg, texts):
    for t in texts:
        el=await pg.query_selector(f'button:has-text("{t}")') or await pg.query_selector(f'input[type=submit][value*="{t}" i]')
        if el and await el.is_enabled():
            try: await el.click(timeout=4000); return t
            except: pass
    return None
async def main():
    v,c=pkce(); REDIR="https://ae-appen.appspot.com/redirect/redirect.html"
    q=urllib.parse.urlencode({"response_type":"code","client_id":"android-251010","scope":"all",
        "redirect_uri":REDIR,"code_challenge":c,"code_challenge_method":"S256","state":secrets.token_hex(8)})
    url="https://id.rema.no/authorization?"+q
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True)
        ctx=await b.new_context(locale="nb-NO", user_agent="Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/124.0 Mobile Safari/537.36")
        pg=await ctx.new_page()
        def on_req(r):
            if "ae-appen.appspot.com" in r.url and "code=" in r.url:
                caps["code"]=urllib.parse.parse_qs(urllib.parse.urlparse(r.url).query).get("code",[None])[0]
        pg.on("request", on_req)
        await pg.goto(url, wait_until="domcontentloaded", timeout=45000); await pg.wait_for_timeout(4000)
        ph=await pg.query_selector('input[name="phoneNumber"]') or await pg.query_selector('input[type="tel"]')
        await ph.fill(PHONE)
        print("SUBMITTING_PHONE (triggers SMS)...", flush=True)
        await click_any(pg, ["Send meg engangskode","Send","Logg inn","Neste"])
        await pg.wait_for_timeout(5000); (await pg.screenshot(path="/work/discovery/rema_s2.png")) if False else None
        print("SMS_SENT — waiting for code file (up to 6 min)...", flush=True)
        code=None
        for _ in range(120):
            if os.path.exists(SMS):
                x=open(SMS).read().strip()
                if x: code=x; break
            await asyncio.sleep(3)
        if not code: print("NO_CODE_TIMEOUT"); await b.close(); return
        print("GOT_CODE, entering...", flush=True)
        boxes=await pg.query_selector_all('input[autocomplete="one-time-code"], input[inputmode="numeric"], input[type="tel"]:not([name="phoneNumber"]), input[name*="code" i], input[name*="otp" i]')
        if len(boxes)==1: await boxes[0].fill(code)
        elif len(boxes)>=len(code):
            for i,ch in enumerate(code): await boxes[i].fill(ch)
        elif boxes: await boxes[0].click(); await pg.keyboard.type(code)
        await click_any(pg, ["Logg inn","Bekreft","Send","Neste","Fortsett","Verifiser"])
        for _ in range(20):
            if caps["code"]: break
            await pg.wait_for_timeout(1000)
        if not caps["code"]:
            try:
                await pg.wait_for_url("**ae-appen.appspot.com/**", timeout=8000)
            except: pass
            import urllib.parse as _u
            if "code=" in pg.url:
                caps["code"]=_u.parse_qs(_u.urlparse(pg.url).query).get("code",[None])[0]
        print("AUTH_CODE_CAPTURED:", bool(caps["code"]))
        if not caps["code"]:
            print("URL_NOW:", pg.url); await b.close(); return
        # exchange code -> tokens
        tok=await ctx.request.post("https://id.rema.no/token", form={
            "grant_type":"authorization_code","code":caps["code"],"redirect_uri":REDIR,
            "client_id":"android-251010","code_verifier":v})
        tj=await tok.json()
        print("TOKEN_STATUS:", tok.status, "KEYS:", list(tj.keys()) if isinstance(tj,dict) else tj)
        if "access_token" in tj:
            open("/data/rema_tokens.json","w").write(json.dumps(tj))
            print("SUCCESS: rema tokens saved | has_refresh:", "refresh_token" in tj, "expires_in:", tj.get("expires_in"))
        await b.close()
asyncio.run(main())
