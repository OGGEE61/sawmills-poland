# CEIDG & KRS Sawmills Data Sourcing & Dashboard

This project provides tools to fetch, process, and visualize data about active sawmills (tartaki) from both the Polish CEIDG (Osoby fizyczne) API v3 and the official KRS (Spółki) via custom scraper.

## Features

* **Data Sourcing CEIDG (`src/ceidg_scraper/fetch_data.py`)**: Queries the CEIDG API for businesses registered under target PKD codes.
* **Data Sourcing KRS (`src/krs_scraper/proxy_discover_all.py` & `krs_tartaki.py`)**: Uses proxies to find target companies and verifies them against the official KRS MS API.
* **Dashboard (`src/dashboard/index.html`)**: A web interface for visualizing both datasets, featuring a dynamic heat map of Poland.
* **Local Web Server (`run_dashboard.py`)**: A simple Python server to launch the dashboard.

## Directory Structure
```text
/Users/gustaw/Documents/Projects/sawmills-poland
├── data/                    # Heavy datasets and raw files
│   ├── raw/                 # Raw JSONL dumps from CEIDG, raw KRS JSONs
│   └── processed/           # Final CSVs ready for the dashboard (tartaki_ceidg.csv, tartaki_full.csv)
├── src/                     # Source Code
│   ├── dashboard/           # HTML/CSS/JS for the frontend
│   ├── ceidg_scraper/       # CEIDG Python scripts
│   └── krs_scraper/         # KRS Python scripts
├── venv/                    # Python virtual environment
├── run_dashboard.py         # Script to run the dashboard
└── requirements.txt         # Dependencies
```

## Setup & Running

**It is highly recommended to run all Python scripts from your virtual environment.**

1. **Activate your virtual environment (if not already active):**
   ```bash
   source venv/bin/activate
   ```
   *(Or just use `venv/bin/python` directly in your commands)*

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **View the Dashboard:**
   To launch the dashboard server, run:
   ```bash
   venv/bin/python run_dashboard.py
   ```
   Then navigate to: [http://localhost:8000/src/dashboard/index.html](http://localhost:8000/src/dashboard/index.html)

## Fetching New Data

### CEIDG (Osoby Fizyczne)
```bash
export CEIDG_TOKEN="YOUR_TOKEN"
cd src/ceidg_scraper
../../venv/bin/python fetch_data.py
```
*To update with newly registered companies, add the `--update` flag.*

### KRS (Spółki)
KRS fetching is a two-step process (Discovery + Verification).
```bash
cd src/krs_scraper
../../venv/bin/python proxy_discover_all.py
../../venv/bin/python krs_tartaki.py verify --input ../../data/processed/all_candidates.csv --output ../../data/processed/tartaki_full.csv --errors ../../data/processed/errors_full.csv --save-raw-dir ../../data/raw/raw_krs --resume
```
