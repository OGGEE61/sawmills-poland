# Project status — 2026-10-19

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

## Next steps
1. **Contact details:** use a search API (Serper.dev / SerpAPI, ~$1 per 1,000 searches, ~$5–7 for ~4,600 active firms) by swapping the `search()` function in `web_search.py`; test on ~50 firms first. Alternative: Google Places API (only firms with a listing).
2. **GUS REGON (BIR1.1) API:** request a key at api.stat.gov.pl (or regon_bir@stat.gov.pl). Gives official address + TERC codes (fixes empty county/municipality), PKD, and phone/email/www where filled. Can be built against the GUS test environment meanwhile.
3. Re-run CEIDG `--update` with the new token.
4. Clean up ~600 KRS rows with no main PKD (incl. firms listing every PKD code).
5. Decide what to do with the 486 "possibly closed" firms (hide by default? separate tab?).
