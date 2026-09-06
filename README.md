# grocious

Your groceries. Your receipts. Your overview.

Pull your loyalty **bonus balance, receipts and campaign offers** straight from the
grocery APIs — no phone app required. Built because the Trumf/Coop/Rema apps are a
pain (or impossible) on de-Googled Android (GrapheneOS). Runs as small containers.

Implements **Trumf / NorgesGruppen** (Kiwi, Meny, Spar, Joker) and **Rema 1000 (Æ)** —
tracking bonus, receipts and offers (coupons are **not** auto-activated — by choice). Coop is planned.

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
By default, Compose uses `.env` and `data/` in the project directory. Set
`GROCIOUS_HOME=/path/to/private/runtime` in the local `.env` to keep runtime files
elsewhere; that directory must contain its own `.env` and `data/`. Export the same
variable when running `app/sync_provider_archives.sh` outside Compose.

Session cookie is long-lived (~months, auto-refreshed server-side); re-run the login only when
`trumf_client` reports the cookie expired.

## Web GUI (`app/webgui.py` + `templates/`, `static/`, `themes/`)

Flask, no CDN, no JS framework. `webgui.py` keeps the data functions and every route; the
presentation lives in `app/templates/` (Jinja), `app/static/style.css` + `app.js`, helpers in `app/ui.py`
(NOK formatting `1 234,50 kr`, dates `dd.mm.yyyy`). Mobile first; receipts expand in place (line items are
fetched from the existing `/…/receipt/<id>.json` routes) and can be filtered per chain and month.

**Themes:** one JSON file per theme in `app/themes/` — `light`, `dark`, `gruvbox`, `catppuccin-mocha`, `ink`
ship. Add a theme by dropping in another file (`{"label": "…", "scheme": "light|dark", "colors": {...}}`,
keys in `themes.COLOR_KEYS`, missing keys fall back to the base scheme) and restarting; it appears in the
picker. The picker (header) remembers the choice in `localStorage`; «Auto» follows `prefers-color-scheme`.
`?theme=<id>` in the URL selects one (used for screenshots).

**Demo mode:** `GROCIOUS_DEMO=1` serves anonymised fixtures (`app/fixtures/`, regenerate with
`python scripts/gen_fixtures.py`) for Trumf, Rema and a small Coop archive — no tokens, no network:

```
python -m venv .venv && .venv/bin/pip install flask requests reportlab waitress pytest ruff
cd app && GROCIOUS_DEMO=1 PORT=3012 ../.venv/bin/python webgui.py
.venv/bin/pytest && .venv/bin/ruff check .
```

Receipt line items are cached on disk under `GROCERY_DATA/cache/<chain>-<id>.json` after the first fetch
(lines never change), so `/api/export/<ym>.json?lines=1` is fast the second time.

## Security
Your own loyalty account, personal use. Secrets (`.env`) and the session cookie (`data/`) are
`.gitignore`d and never committed. The grocery APIs are unofficial/reverse-engineered — they can
change without notice; monitor the fetch job.


## Roadmap
- [x] **Trumf** — bonus balance, receipts, offers
- [x] **Rema 1000 (Æ)** — offers + receipts (activation available but opt-in, not automatic)
- [ ] **Coop** — login works, but data API is edge/WAF-walled (see notes) — receipts not reachable
- [x] **Web GUI** at `grocious.example.com` — dashboard, offers browser (manual activate), receipt export (JSON/CSV/PDF)
- [ ] Scheduled fetch/activate + ntfy summary

## Credits
Reverse-engineering groundwork: [HelgeSverre](https://helgesver.re/articles/reverse-engineering-norwegian-grocery-apps)
and [HelgeSverre's gist](https://gist.github.com/HelgeSverre/80a7f34f874336324184a0c513c2e6a2);
Trumf transaction fields from [ttyridal/trumf-data-fetch](https://github.com/ttyridal/trumf-data-fetch).

## License

[AGPL-3.0](LICENSE) — you may use, self-host and modify this, but derivatives (including hosted services) must stay open under AGPL. No taking it private to monetize grocery data.

The wordmark uses locally hosted [Space Grotesk](https://github.com/floriankarsten/space-grotesk),
licensed under the SIL Open Font License (included in `app/static/fonts/`).
