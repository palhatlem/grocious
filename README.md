# grocery — self-hosted Norwegian grocery bonus tooling

Pull your loyalty **bonus balance, receipts and campaign offers** straight from the
grocery APIs — no phone app required. Built because the Trumf/Coop/Rema apps are a
pain (or impossible) on de-Googled Android (GrapheneOS). Runs as small containers.

Implements **Trumf / NorgesGruppen** (Kiwi, Meny, Spar, Joker) and **Rema 1000 (Æ)** —
including **auto-activation of all available personalized offers** for Rema. Coop is planned.

## How it works
- `login/` — one-time (or ~yearly) **Playwright** re-auth: drives trumf.no's NextAuth →
  `id.trumf.no` IdentityServer (OAuth2 + PKCE, `offline_access`), including the **SMS OTP**
  step, and saves the session cookie to `data/trumf_state.json`.
- `app/trumf_client.py` — **browser-free** runtime: reads the session cookie, gets a Bearer
  from `/api/auth/session`, and calls `platform-rest-prod.ngdata.no` for `saldo` (balance),
  `transaksjoner` (receipts) and `kampanjeavtale/beskrivelser` (offers). Writes `data/status.json`
  and (optionally) pushes an [ntfy](https://ntfy.sh) summary.

## Usage
```bash
cp .env.example .env      # add TRUMF_PHONE + TRUMF_PASSWORD (kept out of git)
docker compose --profile login run --rm trumf-login   # first login; paste SMS code when prompted
docker compose run --rm trumf-fetch                    # pull data; schedule weekly (systemd timer / cron)
```
Session cookie is long-lived (~months, auto-refreshed server-side); re-run the login only when
`trumf_client` reports the cookie expired.

## Security
Your own loyalty account, personal use. Secrets (`.env`) and the session cookie (`data/`) are
`.gitignore`d and never committed. The grocery APIs are unofficial/reverse-engineered — they can
change without notice; monitor the fetch job.

## Credits
Reverse-engineering groundwork: [HelgeSverre](https://helgesver.re/articles/reverse-engineering-norwegian-grocery-apps)
and [HelgeSverre's gist](https://gist.github.com/HelgeSverre/80a7f34f874336324184a0c513c2e6a2);
Trumf transaction fields from [ttyridal/trumf-data-fetch](https://github.com/ttyridal/trumf-data-fetch).

## License
MIT
