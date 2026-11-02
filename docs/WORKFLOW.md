# Workflow: from the registers to the dashboard

All commands run from the repo root with `venv/bin/python` (except the CEIDG fetch, see below).

## The big picture

```
 STEP 1: FETCH (two separate sources)

   CEIDG API (sole proprietors)               KRS (companies)
   dane.biznes.gov.pl, needs token            2 stages: find candidates, then verify
            |                                          |
            v                                          v
   data/raw/tartaki_ceidg.jsonl               data/processed/all_candidates.csv  (9,365 KRS numbers)
   data/raw/ceidg_state.json (resume)                  |   verify each one in the official KRS API
            |                                          v
            v                                 data/raw/raw_krs/*.json   (one raw file per company)
   data/processed/tartaki_ceidg.csv                    |
   (4,541 firms)  <-- dashboard reads this             v
                                              data/processed/tartaki_full_unfiltered.csv
                                                       |   fills missing voivodeship from postal code
                                                       v
                                              data/processed/tartaki_full.csv
                                              (2,479 firms)  <-- dashboard reads this

 STEP 2: VERIFY (new, free, by NIP)

   tartaki_ceidg.csv + tartaki_full.csv
            |  build_master.py
            v
   data/processed/master.csv              one list, 7,020 rows, key = NIP
            |  bialalista.py              asks the Ministry of Finance VAT register
            v
   data/processed/enrichment_bialalista.csv   raw answers (found? VAT status? board members?)
            |  merge_verification.py      turns answers into ONE category per firm
            v
   data/processed/verification.csv        <-- dashboard reads this

 STEP 3: SHOW

   python run_dashboard.py  ->  http://localhost:8000/src/dashboard/index.html
   The dashboard loads the 3 CSVs marked above and joins them by NIP in the browser.
```

## Step 1a: CEIDG (sole proprietors)

| | |
|---|---|
| Script | `src/ceidg_scraper/fetch_data.py` |
| Needs | `export CEIDG_TOKEN="..."` (a new key is requested; the old one must be revoked) |
| Run | `cd data/raw && ../../venv/bin/python ../../src/ceidg_scraper/fetch_data.py --update` |
| Why `cd data/raw` | the script writes its files into the current folder, and its resume file `ceidg_state.json` lives there |
| Output | `data/raw/tartaki_ceidg.csv` (also `.jsonl`) |
| Then | **copy** `tartaki_ceidg.csv` to `data/processed/` by hand |
| Speed | 1 request per ~3.7 s, about 1 hour for a full pass. Safe to stop and resume. |

`--update` re-walks all pages and only adds firms that are new.

## Step 1b: KRS (companies)

| Stage | Script | Reads | Writes |
|---|---|---|---|
| Find candidates | `src/krs_scraper/proxy_discover_all.py` (the proxies are not needed, your own IP works) | sprawdz-firme.pl search by PKD 16.10.Z / 16.11.Z / 16.12.Z | `data/processed/all_candidates.csv` |
| Verify each | `src/krs_scraper/krs_tartaki.py verify --input ... --save-raw-dir data/raw/raw_krs --resume` | official KRS API, one call per company | `data/raw/raw_krs/*.json`, `errors_full.csv` |
| Rebuild CSV | `rebuild_krs.py` | `data/raw/raw_krs/*.json` | `data/processed/tartaki_full_unfiltered.csv` |
| Fill regions | `data/enrich_krs.py` | `tartaki_full_unfiltered.csv` + CEIDG postal codes | `data/processed/tartaki_full.csv` |

Notes:
- `errors_full.csv` (3,594 rows) are companies no longer in KRS (deregistered), not failures.
- The last re-check found **no new KRS companies**.

## Step 2: VAT verification (free, no key)

Run in this order:

```
venv/bin/python src/enrichment/build_master.py          # -> master.csv
venv/bin/python src/enrichment/bialalista.py            # -> enrichment_bialalista.csv  (~4 min, resumable)
venv/bin/python src/enrichment/merge_verification.py    # -> verification.csv
```

- `build_master.py` joins KRS and CEIDG on NIP. For CEIDG it uses the **owner's** NIP (`detail.wlasciciel.nip`), because the plain NIP column is empty.
- `bialalista.py` sends 30 NIPs per request to the Ministry of Finance. To re-check everyone, delete `enrichment_bialalista.csv` first; otherwise it skips NIPs already done.
- `merge_verification.py` gives every NIP one label:

| Label | Meaning | Count |
|---|---|---|
| CZYNNY | active VAT taxpayer | 4,476 |
| ZWOLNIONY | VAT-exempt (normal for small firms) | 148 |
| NIEZAREJESTROWANY | in the register, not registered for VAT | 8 |
| WYKRESLONY | removed from VAT, **possibly closed** | 486 |
| BRAK | not in the register (weak signal only) | 1,895 |

## Step 3: Dashboard

`venv/bin/python run_dashboard.py`, then open http://localhost:8000/src/dashboard/index.html.
It loads `tartaki_ceidg.csv`, `tartaki_full.csv` and `verification.csv`, and matches rows by NIP.
Without `verification.csv` it still works; the VAT column and filter are just empty.

## Step 4: Sales list (wood chippers and briquette machines)

The machines do 0.5-2 t/h and are a Weima sub-brand for the smallest clients, so the buyer is a small or mid-sized firm with wood waste. Big plants score low and are listed separately for the main line. Run everything from the repo root:

```
venv/bin/python -m pip install -r src/enrichment/requirements.txt
sh src/enrichment/refresh.sh                     # rebuild everything; run monthly. Optional sources run if their key is set
venv/bin/python src/enrichment/tests_leads.py    # unit tests
```

Then open http://localhost:8000/src/dashboard/index.html. The "Lista sprzedażowa" tab holds the working lists, notes, next-step dates and CSV export.

Keys are read from the environment (`export GUS_API_KEY=...`); scripts do not load `.env`. `refresh.sh` caps Google Places at 1,000 and web search at 50 lookups per run (`SEARCH_LIMIT`). Called directly without a limit, those scripts process every eligible firm and can bill for all of them.

Web search takes the best tier first and, within a tier, firms with no contact at all first. It skips firms already searched. If both search keys are set, SearchApi is used, so set only one. To run a batch:

```
export SERPER_API_KEY=...                          # type it in the terminal; do not paste keys into chats or commit them
venv/bin/python src/enrichment/web_search.py 50    # the number caps billed lookups
venv/bin/python src/enrichment/crawl_websites.py   # verify found sites and read their contacts
venv/bin/python src/enrichment/build_leads.py
```

To widen the market beyond 16.10/16.11 (slow, resumable, stop any time):

```
venv/bin/python src/enrichment/expand_market.py discover   # list KRS companies with wood PKD codes
venv/bin/python src/enrichment/expand_market.py verify     # keep active firms whose MAIN activity fits; about 2 extracts/s at most
sh src/enrichment/refresh.sh                               # merge what was found
```

| Source | Script | Gives | Needs |
|---|---|---|---|
| Raw KRS extracts | `extract_krs_signals.py` | email, website, roles, shareholders, filings, arrears, bankruptcy | nothing |
| EU project lists | `fetch_eu_projects.py` | projects by type (waste/biomass first). Matched by name, no NIP | nothing |
| Firm websites | `crawl_websites.py` | phones, emails, waste/heat/machine keywords, names fitting KRS masks | nothing |
| Wider market | `expand_market.py` | pallets, joinery, flooring, furniture, forestry companies | nothing. Sole traders outside 16.10 need a new CEIDG run with a token |
| GUS REGON | `gus_regon.py` | phone, email, website, local units | `GUS_API_KEY` (free). Tested on GUS's test server |
| Google Maps | `google_places.py` | phone, website, Maps link | `GOOGLE_PLACES_KEY` (billed). Tested on a stub only |
| Web search | `web_search.py` | websites, contact snippets about the right firm | `SEARCHAPI_KEY` (tested live) or `SERPER_API_KEY` (tested on a stub only). Billed |

**Which machine:** `WASTE_RULES` in `build_leads.py` maps main PKD to chipper, briquetter and typical waste. These are assumptions: correct them from real conversations.

**Scoring** is hand-set rules, not trained on sales: `priority = 0.45 fit + 0.30 capacity + 0.25 timing`, where capacity means right size, not biggest. Firms sized `duża` or `mała` (`size_band`) cannot be tier A or B. `reach` is separate, so a strong firm with no phone becomes a research job. Tier X means closing or closed.

**Checked by hand on each firm's card, not automated:** BDO, financial statements (RDF), FSC, ARiMR. None offers a bulk route we found; RDF blocks scripts. Do not automate around that.

**CRM data** (stage, notes, next step) lives in the browser's localStorage. Use "Kopia CRM" to back it up or move it; several people cannot share it yet.

## What is committed to git
- Committed: all code, `docs/`, and the older CSVs in `data/processed/`.
- **Not committed yet:** `master.csv`, `enrichment_bialalista.csv`, `verification.csv`. They contain board-member names; decide before pushing to a public repo. The dashboard's VAT features need `verification.csv`. `.gitignore` allows `data/processed/*.csv`, so `git add .` **would** add these three.
- **Git-ignored on purpose:** `leads.csv`, `krs_signals.csv`, `eu_projects.csv`, `website_contacts.csv`, `expansion_*.csv`, `gus.csv`, `places.csv`, `data/raw/external/`. They hold names and contacts, and the Cloudflare build publishes every committed CSV, so the public site shows a "missing file" note on the sales list.
- Never committed (ignored): `data/raw/`, `*.json`, `*.jsonl`.
