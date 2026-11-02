#!/bin/sh
# Rebuild the sales list from the current sources. Run monthly from the repo root: sh src/enrichment/refresh.sh
# build_leads.py compares with the previous leads.csv, so changes appear in the dashboard's "Zmiany" list.
# Optional sources run first when their key is set in the environment. To re-read every website: delete website_contacts.csv.
set -e
PY="venv/bin/python -W ignore"
E=src/enrichment

$PY $E/build_master.py
$PY $E/bialalista.py
$PY $E/merge_verification.py
$PY $E/extract_krs_signals.py
$PY $E/fetch_eu_projects.py
# optional sources read leads.csv, but only a first run may build it here: a second build would wipe the change flags
if [ ! -f data/processed/leads.csv ]; then $PY $E/build_leads.py; fi

if [ -n "${GUS_API_KEY:-}" ]; then $PY $E/gus_regon.py; fi
# billed per request, so capped per run (set SEARCH_LIMIT to change). Both take top-priority firms first and skip those already done
if [ -n "${GOOGLE_PLACES_KEY:-}" ]; then $PY $E/google_places.py 1000; fi
if [ -n "${SERPER_API_KEY:-}${SEARCHAPI_KEY:-}" ]; then $PY $E/web_search.py "${SEARCH_LIMIT:-50}"; fi

$PY $E/crawl_websites.py
$PY $E/build_leads.py
