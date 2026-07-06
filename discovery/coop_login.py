import asyncio, os, json, secrets, hashlib, base64, urllib.parse
from playwright.async_api import async_playwright
USER=os.environ["COOP_USER"]; PW=os.environ["COOP_PASSWORD"]; SMS="/data/coop_sms.txt"
CID="7WrQEdeXwUudArpQVjmZEvrTgVs1WkRr"; REDIR="https://login.coop.no/android/no.coop.members/callback"
caps={"code":None}
def pkce():
    v=base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=').decode()
    return v, base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b'=').decode()
async def click_any(pg,texts):
    for t in texts:
        el=await pg.query_selector(f'button:has-text("{t}")') or await pg.query_selector('button[type=submit]')
        if el and await el.is_enabled():
            try: await el.click(timeout=4000); return t
            except: pass
async def main():
    v,c=pkce()
    q=urllib.parse.urlencode({"response_type":"code","client_id":CID,"redirect_uri":REDIR,"audience":"https://api.coop.no",
      "scope":"openid profile offline_access","code_challenge":c,"code_challenge_method":"S256","state":secrets.token_hex(8)})
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True)
        ctx=await b.new_context(locale="nb-NO", user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36")
        pg=await ctx.new_page()
        def on_req(r):
            if REDIR in r.url and "code=" in r.url:
                caps["code"]=urllib.parse.parse_qs(urllib.parse.urlparse(r.url).query).get("code",[None])[0]
        pg.on("request", on_req)
        await pg.goto("https://login.coop.no/authorize?"+q, wait_until="domcontentloaded", timeout=45000)
        await pg.wait_for_timeout(4000)
        for t in ["Godta","Aksepter","Tillat alle","Godta alle"]:
            el=await pg.query_selector(f'button:has-text("{t}")')
            if el:
                try: await el.click(timeout=2500); break
                except: pass
        u=await pg.query_selector('#username') or await pg.query_selector('input[name="username"]')
        await u.fill(USER); print("SUBMIT_IDENTIFIER...",flush=True)
        try: await u.press("Enter")
        except: pass
        await pg.wait_for_selector('input[name="password"]:visible', timeout=15000); await pg.wait_for_timeout(1200)
        pwf=await pg.query_selector('input[name="password"]'); await pwf.fill(PW)
        print("SUBMIT_PASSWORD...",flush=True)
        try: await pwf.press("Enter")
        except: pass
        await pg.wait_for_timeout(4000)
        if await pg.query_selector('input[name="password"]:visible'): await click_any(pg,["Logg inn","Fortsett"])
        await pg.wait_for_timeout(4000)
        if ("mfa" in pg.url.lower()) or ("challenge" in pg.url.lower()) or (await pg.query_selector('input[name="code"]')):
            print("MFA_SMS_SENT — waiting for code file /data/coop_sms.txt (6 min)...",flush=True)
            code=None
            for _ in range(120):
                if os.path.exists(SMS):
                    x=open(SMS).read().strip()
                    if x: code=x; break
                await asyncio.sleep(3)
            if code:
                print("GOT_CODE, entering...",flush=True)
                cb=await pg.query_selector('input[name="code"]') or await pg.query_selector('input[inputmode="numeric"]') or await pg.query_selector('input[type="text"]:visible')
                await cb.fill(code)
                try: await cb.press("Enter")
                except: pass
                await pg.wait_for_timeout(1500); await click_any(pg,["Fortsett","Bekreft","Logg inn","Verifiser"])
        # wait for the app-link callback with code
        for _ in range(30):
            if caps["code"]: break
            await pg.wait_for_timeout(1000)
        if not caps["code"] and "code=" in pg.url:
            caps["code"]=urllib.parse.parse_qs(urllib.parse.urlparse(pg.url).query).get("code",[None])[0]
        print("AUTH_CODE_CAPTURED:", bool(caps["code"]), "| url:", pg.url[:70])
        if caps["code"]:
            tok=await ctx.request.post("https://login.coop.no/oauth/token", form={
                "grant_type":"authorization_code","client_id":CID,"code":caps["code"],
                "redirect_uri":REDIR,"code_verifier":v})
            tj=await tok.json()
            print("TOKEN_STATUS:", tok.status, "KEYS:", list(tj.keys()) if isinstance(tj,dict) else tj)
            if "access_token" in tj:
                open("/data/coop_tokens.json","w").write(json.dumps(tj))
                print("SUCCESS: coop tokens saved | refresh:", "refresh_token" in tj, "expires_in:", tj.get("expires_in"))
        await b.close()
asyncio.run(main())
