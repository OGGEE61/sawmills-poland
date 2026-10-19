"""Turn enrichment_bialalista.csv into data/processed/verification.csv for the dashboard.

verification:
  CZYNNY             active VAT taxpayer
  ZWOLNIONY          VAT-exempt (normal for small firms, not a warning)
  NIEZAREJESTROWANY  found, but not registered for VAT
  WYKRESLONY         removed from the VAT register -> possibly closed
  BRAK               not in the register (weak signal only)
"""
from pathlib import Path

import pandas as pd

PROCESSED = Path(__file__).resolve().parents[2] / "data" / "processed"


def classify(row):
    if row["found"] != "True":
        return "BRAK"
    removed = pd.notna(row["removal_date"]) and (
        pd.isna(row["restoration_date"]) or row["restoration_date"] < row["removal_date"])
    if removed:
        return "WYKRESLONY"
    return {"Czynny": "CZYNNY", "Zwolniony": "ZWOLNIONY"}.get(row["vat_status"], "NIEZAREJESTROWANY")


def main():
    wl = pd.read_csv(PROCESSED / "enrichment_bialalista.csv", dtype=str)
    wl["verification"] = wl.apply(classify, axis=1)
    wl["possibly_closed"] = (wl["verification"] == "WYKRESLONY").map({True: "1", False: ""})
    wl.to_csv(PROCESSED / "verification.csv", index=False, encoding="utf-8")
    print(wl["verification"].value_counts().to_string())


if __name__ == "__main__":
    main()
