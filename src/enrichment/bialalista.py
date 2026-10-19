"""Check NIPs in the Ministry of Finance VAT "Biała Lista" (no key needed).

Reads data/processed/master.csv, writes data/processed/enrichment_bialalista.csv.
Resumable: NIPs already in the output are skipped. Stops cleanly on rate limit.
"""
import csv
import sys
import time
from datetime import date
from pathlib import Path

import requests

PROCESSED = Path(__file__).resolve().parents[2] / "data" / "processed"
INPUT = PROCESSED / "master.csv"
OUTPUT = PROCESSED / "enrichment_bialalista.csv"

URL = "https://wl-api.mf.gov.pl/api/search/nips/{nips}"
BATCH = 30
DELAY = 1.0

FIELDS = [
    "nip", "found", "wl_name", "vat_status", "regon", "krs", "residence_address",
    "working_address", "registration_date", "registration_denial_date",
    "restoration_date", "removal_date", "removal_basis", "representatives",
    "partners", "authorized_clerks", "account_count", "checked_on",
]


def people(items):
    names = []
    for p in items or []:
        name = p.get("companyName") or " ".join(
            x for x in (p.get("firstName"), p.get("lastName")) if x)
        if name:
            names.append(name)
    return "; ".join(names)


def to_row(nip, subject, today):
    if not subject:
        return {"nip": nip, "found": False, "checked_on": today}
    return {
        "nip": nip,
        "found": True,
        "wl_name": subject.get("name"),
        "vat_status": subject.get("statusVat"),
        "regon": subject.get("regon"),
        "krs": subject.get("krs"),
        "residence_address": subject.get("residenceAddress"),
        "working_address": subject.get("workingAddress"),
        "registration_date": subject.get("registrationLegalDate"),
        "registration_denial_date": subject.get("registrationDenialDate"),
        "restoration_date": subject.get("restorationDate"),
        "removal_date": subject.get("removalDate"),
        "removal_basis": subject.get("removalBasis"),
        "representatives": people(subject.get("representatives")),
        "partners": people(subject.get("partners")),
        "authorized_clerks": people(subject.get("authorizedClerks")),
        "account_count": len(subject.get("accountNumbers") or []),
        "checked_on": today,
    }


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None

    with open(INPUT, encoding="utf-8") as f:
        nips = list(dict.fromkeys(r["nip"] for r in csv.DictReader(f) if r["nip"]))

    done = set()
    if OUTPUT.exists():
        with open(OUTPUT, encoding="utf-8") as f:
            done = {r["nip"] for r in csv.DictReader(f)}

    todo = [n for n in nips if n not in done]
    if limit:
        todo = todo[:limit]
    print(f"{len(nips)} NIPs, {len(done)} done, {len(todo)} to check")

    today = date.today().isoformat()
    new_file = not OUTPUT.exists()
    with open(OUTPUT, "a", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()

        for i in range(0, len(todo), BATCH):
            batch = todo[i:i + BATCH]
            resp = requests.get(URL.format(nips=",".join(batch)), params={"date": today}, timeout=30)
            if resp.status_code == 429:
                print("Rate limit hit - stopping. Re-run later to resume.")
                return
            if resp.status_code != 200:
                print(f"HTTP {resp.status_code}: {resp.text[:300]} - stopping.")
                return

            by_nip = {}
            for entry in resp.json()["result"]["entries"]:
                subjects = entry.get("subjects") or []
                by_nip[entry["identifier"]] = subjects[0] if subjects else None
            for nip in batch:
                writer.writerow(to_row(nip, by_nip.get(nip), today))
            out.flush()
            print(f"{min(i + BATCH, len(todo))}/{len(todo)}", flush=True)
            time.sleep(DELAY)


if __name__ == "__main__":
    main()
