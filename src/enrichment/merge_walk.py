"""Add the in-scope firms from walk_krs.py to expansion_firms.csv, so the normal pipeline picks them up.

Scope: wood (16.x), forestry (02.20, 02.40), or any sawmill code. Furniture and landscaping stay out for now.
Safe to re-run: firms already in tartaki_full.csv or expansion_firms.csv are skipped.

Usage: merge_walk.py
"""
import shutil

import pandas as pd

from expand_market import FIELDS, OUTPUT as EXPANSION, PROCESSED, RAW as PIPELINE_RAW
from walk_krs import CHECKED, OUTPUT as WALK_FIRMS, RAW as WALK_RAW

SCOPE_MAIN = ("16.", "02.20", "02.40")


def main():
    firms = pd.read_csv(WALK_FIRMS, dtype=str).fillna("")
    firms["krs"] = firms["krs"].str.zfill(10)
    results = pd.read_csv(CHECKED, dtype=str).drop_duplicates("krs", keep="last").set_index("krs")["result"]
    in_scope = firms["pkd_main"].str.startswith(SCOPE_MAIN) | (firms["krs"].map(results) == "kept_sawmill_other")
    known = set()
    for path in (PROCESSED / "tartaki_full.csv", EXPANSION):
        known |= set(pd.read_csv(path, dtype=str)["krs"].str.zfill(10))
    new = firms[in_scope & ~firms["krs"].isin(known)].drop_duplicates("krs")
    new[FIELDS].to_csv(EXPANSION, mode="a", header=False, index=False, encoding="utf-8")
    for krs in new["krs"]:
        shutil.copy(WALK_RAW / f"{krs}.json", PIPELINE_RAW / f"{krs}.json")
    print(f"{in_scope.sum()} in scope, {len(new)} added to {EXPANSION.name}")


if __name__ == "__main__":
    main()
