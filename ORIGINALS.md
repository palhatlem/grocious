# Kvitteringsoriginaler — 2026-09-06

Privat arkiv: `/srv/docker/grocery/data/receipts/{coop,trumf,rema}`. SHA-256-navngitte originalfiler overskrives aldri; receipt.json og index.json skrives atomisk. Ukjente kildefelter bevares. Passord og autentiseringsheadere arkiveres ikke sammen med kvitteringene.

## Verifiserte kilder

- Coop: originale PDF-er, API-JSON og tekst. 238 tilgjengelige kjøp, 2023-09-08–2026-09-04. Eksisterende Coop-import er beholdt.
- Trumf: 165 oppføringer fra nettstedets siste 12 måneder, 2025-09-06–2026-08-27. 161 har egen kvittering; fire er eksplisitt merket uten kvittering av kilden. Komplette head-/purchaseDetails-felter er hentet fra React Server Component-svar. Bare kvitteringsobjektene lagres, ikke hele siden med øvrige profildata. Nettstedets egen nedlastingsknapp lager JPEG fra sine kvitteringsdata. Disse filene hentes uendret med Playwright og merkes som leverandørbilder, ikke originale kassabonger.
- Rema: 106 kjøp, 2023-10-21–2026-09-05. GET `/v1/bella/transaction/v2/heads` og `/v1/bella/transaction/v2/rows/{id}` gir komplette JSON-svar med varer, betaling, pant, rabatter og bonus. Ingen separat bildekilde er funnet i disse svarene. Prøvekall til `/v1/bellanaveo/receipt/{receiptId}/{customerId}` med kontoens egne ID-er ga 404. Dette beviser ikke at Rema aldri kan levere bilder; arkivet viser tydelig «rådata» inntil en fungerende bildekilde er funnet.

Supplerende undersøkelseskilde: [Helge Sverres dekompilerte Rema-API-beskrivelse](https://gist.github.com/HelgeSverre/80a7f34f874336324184a0c513c2e6a2). Beskrivelsen er uoffisiell; fungerende kall og svar er kontrollert lokalt. Trumfs bildemetode er verifisert i nettstedets JavaScript og ved faktisk nedlasting.

## Grocious

`/archive/trumf` og `/archive/rema` viser arkivet uavhengig av live innlogging. Hvert kjøp har full JSON, alle originalfiler som ZIP, og individuelle råfiler/bilder. `/api/archive/{source}` gir indeks og jobbstatus, inklusive Trumf-bildejobb når tilgjengelig. Gamle JSON/CSV/PDF-ruter er beholdt; den forenklede PDF-en kalles nå «laget PDF».

## Drift

`app/provider_archive.py {rema,trumf}` henter hele tilgjengelige listen, lagrer manglende detaljer og kan gjenopptas. `--incremental` oppdaterer de siste 60 dagene og kjøp der oversiktsdata har endret seg. `app/trumf_images.py` henter manglende leverandørbilder med to nettleserfaner, kontrollerer kvitteringsnummer i filnavnet og JPEG-format, og bevarer gamle versjoner. Endrede rådata markerer bildet for ny innhenting.

Trumfs direkte detaljside trenger `transactionType`, `timestamp` og `description` fra den virkelige oversiktslenken. Bare batch-ID ga «Kunne ikke finne transaksjonsdetaljer», selv om purchaseDetails lå i råsvaret. Nettleserens native nedlastingsknapp virker med de observerte parameterne. Ingen lokal tegning av en erstatningskvittering brukes.

Systemd-brukertimer `grocious-provider-archive.timer` kjører daglig ca. 07:15–07:30 Europe/Oslo, via `app/sync_provider_archives.sh`. Gjenbruker grocery-web/grocery-login og eksisterende innlogging, ingen nye lyttere. Feilstatus ligger per kilde i status.json og images_status.json; journalen viser jobbutfall. En kildefeil stopper ikke forsøk på den andre kilden. Ingen automatisk ekstern melding er lagt til.

Originalene er under eksisterende restic-dekning for `/srv/docker`. En ny ekstern backup/restore er ikke verifisert som del av denne oppgaven. Restore til separat mappe og kontroller SHA-256 mot receipt.json før bruk; indeks kan gjenoppbygges med receipt_archive.rebuild(source).

Marcus sine tidligere manuelle filer og eksisterende Trumf/Rema-liveflyt er beholdt. Tidligere endringer i login/rema_login.py er ikke berørt.
