# Project status — 2026-11-02

**Goal:** sell wood chippers and briquette machines to Polish firms with wood waste. Run and refresh: `docs/WORKFLOW.md`, Step 4. Nothing below the line has been re-checked since 2026-10-19.

| Live firms (6,370) | Phone | Email | Website | Full contact name | Role only |
|---|---|---|---|---|---|
| KRS (1,873) | 90 | 290 | 152 | 117 | ~1,700 |
| CEIDG (4,497) | 752 | 792 | 103 | 4,497 | - |

- Target: 0.5-2 t/h machines, Weima sub-brand for the smallest clients. 160 big firms and 149 very small ones are kept out of tiers A and B.
- Tiers: A 59, B 854, C 3466, D 1991, X 664 (closing or closed). Of A+B: 214 have a phone, 88 email only, 611 need research.
- Search API: 99 firms searched with SearchApi.io (A first, then B firms with no contact). Tier A top 50 went from 2 to 18 phones; the 49 B firms from 0 to 13. 20 phones come from search snippets, so check them on the first call. SearchApi credits are used up; 552 tier B firms with no contact have not been searched.
- EU projects, right-sized firms: 25 have a recent waste/biomass/GOZ project, 11 a recent machinery project.
- Wider market: verification in progress, 9,200 of 15,317 candidates read and 1,202 kept (13%), not yet in the list. `expand_market.py verify` is resumable.

**Known limits**
- Scoring, size limits and the machine offered (`WASTE_RULES`) are assumptions with no sales data behind them. Stationary machines are assumed, so forestry and landscaping rank low. Almost all A+B firms get "Rębak + brykieciarka", so the offer does not yet discriminate for sawmills.
- Project type is keyword-based; EU matches are by name (no NIP in the lists).
- Waste volume is not known for any firm: PKD and website words are stand-ins.
- KRS API masks names. For most companies we know the role and initials only.
- Financial statements (RDF) return 403 from bot protection to scripts. Not worked around; no revenue or headcount.
- By hand on each firm's card, not automated: BDO, RDF, FSC, ARiMR. Skipped: job ads, the e-drewno buyer list (unverified that it exists), PEFC, dane.gov.pl farm-beneficiary list (dead 2017 link).
- Sole traders outside 16.10/16.11 are missing until CEIDG is re-run with a token.
- GUS: tested on its test server only, which anonymises sole traders. Places: tested on a stub only. SearchApi.io and Serper: tested live.

**Needs you:** revoke the old CEIDG token (in git history); new CEIDG token (CEIDG support is checking bulk access); GUS key (requested 2026-11-02); fix GitHub to Cloudflare auto-deploy; decide on `master.csv`, `verification.csv`, `enrichment_bialalista.csv`.

**Next**
1. Calls are on hold for now. When they start, begin with the "Zmiany" list and note which firms have wood waste and buy: scoring has no sales data yet.
2. Finish the Serper search of the 552 tier B firms with no contact: see `docs/WORKFLOW.md`.
3. When `expand_market.py verify` finishes, run `refresh.sh` to add those firms to the list.
4. Use Google Places (billed) only if search leaves too many strong firms without a phone.
5. When GUS and CEIDG keys arrive, run them. Both are free and cover firms that search misses.

---

# Earlier status — 2026-10-19 (end of day)

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
