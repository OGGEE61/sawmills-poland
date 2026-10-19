# Project status — 2026-10-19 (end of day)

See also `docs/WORKFLOW.md` for how data flows from fetch to dashboard.

## TL;DR
- **Data:** 4,541 CEIDG sole proprietors + 2,479 KRS companies (~7,013 unique NIPs).
- **KRS re-check:** nothing new. Discovery returned 9,364 candidates (we had 9,365); the 3,594 "errors" are deregistered companies, not failures.
- **VAT verification (done):** all NIPs checked in the Ministry of Finance Biała Lista (free, no key). 4,476 active, 148 exempt, 8 not registered, **486 removed from VAT (possibly closed — 450 of them KRS)**, 1,895 not found (weak signal; many sole proprietors simply aren't listed).
- **Dashboard:** new "Weryfikacja VAT" filter, VAT column and a verification section in the company popup. Header 🪵 emoji removed.
- **CEIDG token:** hardcoded token removed from `fetch_data.py` (now `CEIDG_TOKEN` env var only). It is still in git history (commit 4da45b4) — revoke it. A new key was requested at dane.gov.
- **Contact details (phone/email/www): still the main gap** (~15% of CEIDG, 0% of KRS have a phone).

## Scripts (`src/enrichment/`)
Run in this order from the repo root with `venv/bin/python`:
1. `build_master.py` → `data/processed/master.csv` (KRS + CEIDG keyed on NIP; CEIDG uses the owner's NIP)
2. `bialalista.py` → `enrichment_bialalista.csv` (batches of 30 NIPs, resumable)
3. `merge_verification.py` → `verification.csv` (CZYNNY / ZWOLNIONY / NIEZAREJESTROWANY / WYKRESLONY / BRAK), read by the dashboard
4. `web_search.py` — Selenium search harness for contact details (see below)

The three generated CSVs are **not committed** (untracked in `data/processed/`). `verification.csv` is needed for the dashboard's VAT features and contains names of board members/partners — decide before committing to a public repo.

## What did not work
- **Selenium on free search engines:** DuckDuckGo shows a bot challenge on the first query; Bing returns blank results after a few queries. Google would block faster. No evasion workarounds were built. `web_search.py` currently targets Bing and is not usable at scale.

## CEIDG update
- `fetch_data.py --update` was stopped at page ~68 of ~800 (1610Z) after repeated timeouts from dane.biznes.gov.pl; no new firms found in the pages checked. State is saved — re-run when the new key arrives:
  `cd data/raw && CEIDG_TOKEN=... ../../venv/bin/python ../../src/ceidg_scraper/fetch_data.py --update`
  (run from `data/raw`; the script writes its files to the current directory, and the resulting CSV must be copied to `data/processed/`).

## Cloudflare Pages
- Project `sawmills-poland` (https://sawmills-poland.pages.dev) is linked to `OGGEE61/sawmills-poland`, branch `main`. Build command copies `src/dashboard` + `data/processed/*.csv` into `public/`.
- **Auto-deploy on push is NOT firing** (no build for pushes after Oct 5). A manual build via the Pages API worked (2026-10-19, commit f5cb9c1), so Cloudflare can read the repo; GitHub just isn't notifying it.
- Fix: GitHub -> Settings -> Applications -> Cloudflare Pages -> Configure -> allow `sawmills-poland`; if that fails, reconnect the Git source in the Cloudflare project. Test by pushing any commit to `main`.
- Manual deploy meanwhile: `POST /accounts/<id>/pages/projects/sawmills-poland/deployments` with `branch=main` (wrangler login works via `npx wrangler@4.151.1`; wrangler is not installed globally).
- `verification.csv` is untracked, so the live VAT column/filter is empty.

## What we need to proceed
**Keys / accounts**
1. **New CEIDG token** (requested at dane.biznes.gov.pl) -> re-run `fetch_data.py --update`. Old token must be **revoked** (it is in the public repo history).
2. **GUS REGON key — the "BIR1" API, version 1.1** (SOAP). Request at api.stat.gov.pl ("Zamów klucz do API") or regon_bir@stat.gov.pl. Not the BDL or TERYT APIs. Gives address + TERC (fills county/municipality), PKD, and phone/email/www where filled.
3. **Search API key** (Serper.dev preferred, or SerpAPI; ~$1 per 1,000 searches, ~$5-7 for ~4,600 active firms) -> contact details via `src/enrichment/web_search.py` (swap `search()`; test on ~50 firms first). Free Selenium scraping of DuckDuckGo/Bing gets blocked.

**Decisions**
- `verification.csv` / `master.csv` / `enrichment_bialalista.csv` are uncommitted: they contain board-member names and the repo is public. Commit as is, strip the names, or keep local.
- What the dashboard does with the 486 "possibly closed" (WYKRESLONY) firms: hide by default or separate tab.

**Can be done without waiting**
- Build the GUS REGON client against GUS's public test environment.
- Clean up ~600 KRS rows with no main PKD (incl. firms listing every PKD code).
- Fix GitHub -> Cloudflare auto-deploy (see above).

**Suggested order:** request GUS key + sign up for Serper -> GUS test-env code + PKD cleanup -> when keys arrive: CEIDG update, contact search, GUS enrichment.
