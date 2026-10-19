"""Merge KRS and CEIDG into one list keyed on NIP -> data/processed/master.csv"""
from pathlib import Path

import pandas as pd

PROCESSED = Path(__file__).resolve().parents[2] / "data" / "processed"


def clean_nip(value):
    if pd.isna(value):
        return None
    digits = "".join(ch for ch in str(value).split(".")[0] if ch.isdigit())
    return digits.zfill(10) if len(digits) in range(1, 11) else None


def main():
    krs = pd.read_csv(PROCESSED / "tartaki_full.csv", dtype=str)
    ceidg = pd.read_csv(PROCESSED / "tartaki_ceidg.csv", sep=";", encoding="utf-8-sig", dtype=str)

    krs_m = pd.DataFrame({
        "source": "KRS",
        "source_id": krs["krs"],
        "name": krs["name"],
        "nip": krs["nip"].map(clean_nip),
        "regon": krs["regon"].str.split(".").str[0],
        "city": krs["city"],
        "postal_code": krs["postal_code"],
        "voivodeship": krs["voivodeship"],
    })
    ceidg_m = pd.DataFrame({
        "source": "CEIDG",
        "source_id": ceidg["CEIDG_ID"],
        "name": ceidg["NAZWA"],
        "nip": ceidg["detail.wlasciciel.nip"].map(clean_nip),
        "regon": ceidg["detail.wlasciciel.regon"],
        "city": ceidg["detail.adresDzialalnosci.miasto"],
        "postal_code": ceidg["detail.adresDzialalnosci.kod"],
        "voivodeship": ceidg["detail.adresDzialalnosci.wojewodztwo"],
    })

    master = pd.concat([krs_m, ceidg_m], ignore_index=True)
    master.to_csv(PROCESSED / "master.csv", index=False, encoding="utf-8")
    dup = master["nip"].dropna().duplicated().sum()
    print(f"{len(master)} rows, {master['nip'].notna().sum()} with NIP, "
          f"{master['nip'].nunique()} unique NIPs, {dup} duplicate NIPs, "
          f"{master['nip'].isna().sum()} without NIP")


if __name__ == "__main__":
    main()
