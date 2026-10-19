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

## What is committed to git
- Committed: all code, `docs/`, and the older CSVs in `data/processed/`.
- **Not committed yet:** `master.csv`, `enrichment_bialalista.csv`, `verification.csv`. They contain board-member names; decide before pushing to a public repo. The dashboard's VAT features need `verification.csv`.
- Never committed (ignored): `data/raw/`, `*.json`, `*.jsonl`.

## Still missing: contact details (phone / email / website)
Only ~15% of CEIDG firms and 0% of KRS firms have a phone. Plan: a search API (Serper/SerpAPI) driven by `src/enrichment/web_search.py`, and the GUS REGON key. See `docs/STATUS.md`.
