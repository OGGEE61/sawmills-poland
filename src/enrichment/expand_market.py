"""Find wood-waste producers beyond sawmills: pallets, joinery, flooring, furniture, forestry -> expansion_firms.csv

Chippers and briquette machines sell to anyone with wood waste, but the registers were only searched for 16.10/16.11.
  discover  lists companies by PKD from sprawdz-firme.pl, which matches any PKD in the extract, so most hits are noise
  verify    reads each official KRS extract and keeps active firms whose MAIN activity is in TARGET_MAIN

Deliberately slow, from one IP, no proxies. Resumable: stop and re-run any time.

Usage: expand_market.py discover [pkd ...] | verify [limit]
"""
import csv
import json
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw" / "raw_krs"
CANDIDATES = PROCESSED / "expansion_candidates.csv"
CHECKED = PROCESSED / "expansion_checked.csv"
OUTPUT = PROCESSED / "expansion_firms.csv"

SEARCH_URL = "https://sprawdz-firme.pl/api/v1/search"
KRS_URL = "https://api-krs.ms.gov.pl/api/krs/OdpisAktualny/{}?rejestr=P&format=json"
SEARCH_DELAY = 1.0
KRS_DELAY = 0.5
# highest waste volume first, so a partial run still gives the best firms
DISCOVERY_ORDER = ["16.24.Z", "16.23.Z", "16.22.Z", "16.21.Z", "16.29.Z", "02.20.Z", "02.40.Z", "31.09.Z", "31.02.Z", "31.01.Z", "81.30.Z"]
TARGET_MAIN = ("16.", "31.0", "02.20", "02.40", "81.30")
FIELDS = ["krs", "name", "nip", "regon", "legal_form", "status_from_discovery", "voivodeship", "city", "street", "building_no",
          "postal_code", "registration_date", "pkd_main"]


def discover(codes):
    known = set()
    for name in ("all_candidates.csv", "errors_full.csv"):
        path = PROCESSED / name
        if path.exists():
            known |= set(pd.read_csv(path, dtype=str, encoding="utf-8-sig")["krs"].str.zfill(10))
    done_codes, seen = set(), set()
    if CANDIDATES.exists():
        previous = pd.read_csv(CANDIDATES, dtype=str)
        seen = set(previous["krs"])
        done_codes = set(previous["pkd"])
    write_header = not CANDIDATES.exists()
    session = requests.Session()
    with open(CANDIDATES, "a", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        if write_header:
            writer.writerow(["krs", "name", "pkd", "status"])
        for code in codes:
            if code in done_codes:
                print(f"{code}: already listed")
                continue
            page, new = 1, 0
            while True:
                response = session.get(SEARCH_URL, params={"pkd": code, "per_page": 100, "page": page}, timeout=30)
                if response.status_code != 200:
                    print(f"Stopping on HTTP {response.status_code} at {code} page {page}; delete its rows to redo that code")
                    return
                data = response.json()
                for item in data.get("results") or []:
                    krs = str(item.get("krs") or "").zfill(10)
                    if krs.strip("0") and item.get("status") == "ACTIVE" and krs not in known and krs not in seen:
                        seen.add(krs)
                        new += 1
                        writer.writerow([krs, item.get("name", ""), code, item.get("status")])
                if not data.get("meta", {}).get("has_next"):
                    break
                page += 1
                time.sleep(SEARCH_DELAY)
            out.flush()
            print(f"{code}: {new} new candidates, {page} pages", flush=True)


def main_pkd(odpis):
    activity = (odpis["dane"].get("dzial3") or {}).get("przedmiotDzialalnosci") or {}
    items = activity.get("przedmiotPrzewazajacejDzialalnosci") or []
    return [f"{p.get('kodDzial', '')}.{p.get('kodKlasa', '')}.{p.get('kodPodklasa', '')}" for p in items]


def firm_row(krs, name, odpis, code):
    head = odpis.get("naglowekA") or {}
    d1 = odpis["dane"]["dzial1"]
    subject = d1.get("danePodmiotu") or {}
    ids = subject.get("identyfikatory") or {}
    place = d1.get("siedzibaIAdres") or {}
    seat, address = place.get("siedziba") or {}, place.get("adres") or {}
    return {"krs": krs, "name": subject.get("nazwa") or name, "nip": ids.get("nip", ""), "regon": ids.get("regon", ""),
            "legal_form": subject.get("formaPrawna", ""), "status_from_discovery": "ACTIVE", "voivodeship": seat.get("wojewodztwo", ""),
            "city": address.get("miejscowosc", ""), "street": address.get("ulica", ""), "building_no": address.get("nrDomu", ""),
            "postal_code": address.get("kodPocztowy", ""), "registration_date": head.get("dataRejestracjiWKRS", ""), "pkd_main": code}


def verify(limit):
    candidates = pd.read_csv(CANDIDATES, dtype=str).fillna("")
    checked = set(pd.read_csv(CHECKED, dtype=str)["krs"]) if CHECKED.exists() else set()
    todo = candidates[~candidates["krs"].isin(checked)]
    if limit:
        todo = todo.head(limit)
    print(f"{len(todo)} extracts to read, {len(checked)} already read", flush=True)
    new_checked, new_output = not CHECKED.exists(), not OUTPUT.exists()
    session = requests.Session()
    kept = 0
    with open(CHECKED, "a", newline="", encoding="utf-8") as check_file, open(OUTPUT, "a", newline="", encoding="utf-8") as out_file:
        check_writer, out_writer = csv.writer(check_file), csv.DictWriter(out_file, FIELDS)
        if new_checked:
            check_writer.writerow(["krs", "result"])
        if new_output:
            out_writer.writeheader()
        failures = 0
        for i, row in enumerate(todo.itertuples(), 1):
            try:
                response = session.get(KRS_URL.format(row.krs), timeout=30)
            except requests.RequestException:
                failures += 1
                if failures >= 10:
                    print("Stopping after 10 network failures in a row; re-run later")
                    return
                time.sleep(10)
                continue
            if response.status_code == 429 or response.status_code >= 500:
                print(f"Stopping on HTTP {response.status_code}; re-run later")
                return
            failures = 0
            result = "gone"
            if response.status_code == 200:
                odpis = response.json()["odpis"]
                mains = [code for code in main_pkd(odpis) if code.startswith(TARGET_MAIN)]
                result = "other"
                if mains:
                    d6 = odpis["dane"].get("dzial6") or {}
                    if d6.get("likwidacja") or d6.get("rozwiazanieUniewaznienie"):
                        result = "closing"
                    else:
                        result = "kept"
                        kept += 1
                        (RAW / f"{row.krs}.json").write_text(json.dumps({"odpis": odpis}, ensure_ascii=False), encoding="utf-8")
                        out_writer.writerow(firm_row(row.krs, row.name, odpis, mains[0]))
                        out_file.flush()
            check_writer.writerow([row.krs, result])
            check_file.flush()
            if i % 200 == 0:
                print(f"{i}/{len(todo)} read, {kept} kept", flush=True)
            time.sleep(KRS_DELAY)
    print(f"done: {kept} kept")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "discover":
        discover(sys.argv[2:] or DISCOVERY_ORDER)
    elif command == "verify":
        verify(int(sys.argv[2]) if len(sys.argv) > 2 else None)
    else:
        sys.exit(__doc__)
