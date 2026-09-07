# Receipt inbox

Upload at `/inbox`, share into the installed PWA, or enable the optional IMAP IDLE worker.
PDF text, plain text, HTML, EML attachments and JPEG/PNG/WebP/HEIC are supported. Photos and scanned
PDFs retain a display/vision derivative; deterministic rules cannot read image pixels. OCR is not
implemented yet. `GROCIOUS_OCR=none` documents that current limitation.

## Run

Use the normal web image build. It now includes Poppler, Pillow/HEIF, html2text, provider SDKs,
jsonschema and IMAPClient. Keep the existing authentication reverse proxy.
Set `client_max_body_size 321m` on `/inbox` to allow ten 32 MiB files plus multipart overhead;
a 32m proxy limit restricts the entire batch. The application also rejects more than 20 PDF pages.

Install from HTTPS in Chrome/Vanadium, then share a PDF/photo to grocious. The service worker uses
network-only fetching; it stores no authenticated receipt pages offline. PWA icons wrap the approved
wordmark, pending a dedicated icon design. A share requires a valid proxy login cookie; phone acceptance
must be checked after deployment with the actual authentication proxy.

## Interpretation

Default `GROCIOUS_LLM_DEFAULT=none`, `GROCIOUS_LLM_AUTO=0`. Buttons are disabled unless the provider is
configured. Set keys in the private runtime `.env`, never the repository. Only this receipt's text,
derived images, and limited intake hints are sent. Gateway is text-only; its EU routing is an operator
configuration, not a guarantee made by this application. SDK retries are disabled. Manual runs are
synchronous (up to 120 seconds): allow an appropriate reverse-proxy read timeout on the interpret route.

Provider defaults are configurable: `claude-opus-5` and `gpt-6-astra`. Usage token counts are shown;
monetary cost is not estimated. See the official [OpenAI structured output contract](https://developers.openai.com/api/docs/guides/structured-outputs),
[OpenAI image input contract](https://developers.openai.com/api/docs/guides/images-vision), and
[Claude structured output contract](https://platform.claude.com/docs/en/build-with-claude/structured-outputs).
These adapters use the official SDKs and a shared, locally validated JSON schema.

Every successful run appends `interpretation-N.json`; `active.json` chooses the current run.
Unlike the initial proposed design, the immutable baseline `receipt.json` is never rewritten to switch
providers. `read_receipt()` merges active interpretation, user corrections, and review state.
Corrections take precedence even when selecting another run. Provider failures preserve existing data.
Wrong totals absent from extracted text are flagged. Image-only receipts have no independent text
baseline; inspect the original before confirming. Confirmation requires store, date, amount and currency.

## Mail

Configure `IMAP_*` variables from `.env.example`, then `docker compose --profile mail up -d inbox-mail`.
The optional service shares only the same application data volume and runs `python -m inbox.mailworker`.
The Bridge host must be reachable from this container: configure networking in a local Compose override
if the Bridge listens on host loopback. Do not expose Bridge externally. Configure TLS verification for
the actual Bridge certificate; verification defaults on. IMAP IDLE requires server MOVE support.

Create a mail filter routing receipts into `Grocious/Inbox`. Successful messages move to `Grocious/Done`
only after ingestion of all attachments. Invalid messages remain in `Grocious/Failed`; originals are not
deleted. `mail_status.json` supplies connection and last-ingestion status. Reconnect uses backoff;
IDLE is renewed at most every 25 minutes. No timer or cron is installed.
[IMAPClient's IDLE API](https://imapclient.readthedocs.io/en/3.0.1/api.html#imapclient.IMAPClient.idle)
is the worker's connection contract.

## Storage and exports

`receipts/inbox/<content-id>/` lives in the existing receipt archive. Original files are immutable and
SHA-256 checked. Review and corrections are separate overlays. Duplicate uploads reuse the same ID.
Shared URLs are stored as inert text and never fetched by the server. HTML and email render as plain text.

Linking copies the original into the provider receipt as `user-upload`. The target's independent
`user-uploads.json` is merged on read so a subsequent provider sync cannot erase the attachment/reference.
No provider amounts or receipt lines are changed. Linked receipts cannot be edited or reconfirmed into a
second export. There is currently no unlink UI.

`/api/export/<ym>.json` and CSV include pending/confirmed inbox records, with review state, confidence,
category, currency and archive ID; discarded and linked inbox records are excluded. CSV appends these
metadata columns after its legacy columns. The combined JSON total is explicitly NOK-only; individual
non-NOK receipts retain their own currency and amount. The inbox card groups totals by currency.
EML and its attachments each remain separate intake records; review possible duplication of body/attachment.

## Verification

`pytest` is offline and uses synthetic documents/mocked providers, including extraction, idempotency,
overlays, mail attachments, provider history, links surviving provider refresh, and thumbnail checks.
Demo mode seeds five synthetic inbox receipts on the first inbox visit. Run demo with an isolated writable
`GROCERY_DATA`; never point demo at a production archive.

Release acceptance still requires the deployed proxy/PWA on a phone, live Bridge delivery, and one real
photo run with each configured vision provider. Those are separate from local tests. Optional OCR and
a dedicated icon design are deferred.

## Bookkeeping contract additions

`payment` is a nullable object with `method`, `card_last4`, `terminal`, `auth_code`, also indexed and
exported. Unknown references remain null; no bank account is inferred. Only explicitly printed masked
card suffixes are extracted by rules. Structured payment is included in prompt `interpret-v2`; v1 is
retained for reproducibility. Category remains a UI hint, and never filters an export or selects an account.

All four sources export integer `amount_minor`; line exports also include integer `amount_minor`
(`line_amount_minor` in CSV) and available `kind`. Old numeric `amount` columns remain for compatibility.
Archived integer amounts take precedence; without one, legacy chain amounts are converted with Decimal,
so this cannot recover precision already lost upstream. `total_minor` is an integer NOK total.
An endpoint regression test excludes linked/discarded rows in both JSON and CSV, including when the
index is stale but the current review overlay has changed. `/api/archive/inbox` keeps the shared archive
response shape with document checksums and roles.
