"""Pull sales signals out of the full KRS extracts -> data/processed/krs_signals.csv

The extracts in data/raw/raw_krs hold much more than tartaki_full.csv keeps: email, website,
board roles, shareholders, filing history, tax arrears, bankruptcy. PESEL and birth dates are
never copied. The KRS API masks names (J*** K******), so people are written as masks here and
matched to full names from Biała Lista in build_leads.py.
"""
import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "raw_krs"
PROCESSED = ROOT / "data" / "processed"


def parse_date(text):
    try:
        return datetime.strptime(str(text).strip()[:10], "%d.%m.%Y").date()
    except ValueError:
        return None


def pkd_code(item):
    return f"{item.get('kodDzial', '')}.{item.get('kodKlasa', '')}.{item.get('kodPodklasa', '')}"


def mask_of(person):
    names = person.get("imiona") or {}
    surname = person.get("nazwisko") or {}
    parts = [names.get("imie"), names.get("imieDrugie"), surname.get("nazwiskoICzlon"), surname.get("nazwiskoIICzlon")]
    return " ".join(p for p in parts if p)


def as_list(value):
    if not value:
        return []
    return value if isinstance(value, list) else [value]


def is_open(entry, end_key):
    return not entry.get(end_key)


def filing_years(mentions):
    years = []
    for item in as_list(mentions):
        period = str(item.get("zaOkresOdDo", ""))
        digits = [period[i:i + 4] for i in range(len(period) - 3) if period[i:i + 4].isdigit()]
        years += [int(y) for y in digits if 1990 <= int(y) <= date.today().year]
    return years


def extract(odpis):
    head = odpis.get("naglowekA") or odpis.get("naglowekP") or {}
    data = odpis["dane"]
    d1, d2, d3, d4, d6 = (data.get(f"dzial{n}") or {} for n in (1, 2, 3, 4, 6))
    address = d1.get("siedzibaIAdres") or {}
    activity = d3.get("przedmiotDzialalnosci") or {}
    main_pkd = [pkd_code(p) for p in as_list(activity.get("przedmiotPrzewazajacejDzialalnosci"))]
    other_pkd = [pkd_code(p) for p in as_list(activity.get("przedmiotPozostalejDzialalnosci"))]
    capital = ((d1.get("kapital") or {}).get("wysokoscKapitaluZakladowego") or {}).get("wartosc", "")

    board = (d2.get("reprezentacja") or {})
    people = [{"role": p.get("funkcjaWOrganie") or board.get("nazwaOrganu") or "", "mask": mask_of(p)}
              for p in as_list(board.get("sklad")) if not p.get("czyZawieszona")]
    people += [{"role": "PROKURENT", "mask": mask_of(p)} for p in as_list(d2.get("prokurenci"))]
    owners = [{"mask": mask_of(p), "shares": p.get("posiadaneUdzialy", ""), "all": bool(p.get("czyPosiadaCaloscUdzialow"))}
              for p in as_list(d1.get("wspolnicySpzoo")) + as_list(d1.get("wspolnicyPartnerzy")) if mask_of(p)]

    filings = (d3.get("wzmiankiOZlozonychDokumentach") or {}).get("wzmiankaOZlozeniuRocznegoSprawozdaniaFinansowego")
    years = filing_years(filings)
    suspensions = as_list(d6.get("zawieszenieWznowienie"))

    return {
        "krs": str(head.get("numerKRS", "")).zfill(10),
        "email": address.get("adresPocztyElektronicznej", ""),
        "website": address.get("adresStronyInternetowej", ""),
        "main_pkd": "; ".join(main_pkd),
        "pkd_count": len(main_pkd) + len(other_pkd),
        "all_pkd": "; ".join(main_pkd + other_pkd),
        "share_capital_pln": capital.replace(",", ".").replace(" ", "") if capital else "",
        "voivodeship_raw": (address.get("siedziba") or {}).get("wojewodztwo", ""),
        "county_raw": (address.get("siedziba") or {}).get("powiat", ""),
        "municipality_raw": (address.get("siedziba") or {}).get("gmina", ""),
        "people": json.dumps(people, ensure_ascii=False),
        "owners": json.dumps(owners, ensure_ascii=False),
        "latest_filing_year": max(years) if years else "",
        "filings_count": len(as_list(filings)),
        "has_group_accounts": bool(d3.get("sprawozdaniaGrupyKapitalowej")),
        "has_supervisory_board": bool(d2.get("organNadzoru")),
        "branches": len(as_list(d1.get("jednostkiTerenoweOddzialy"))),
        "open_arrears": sum(is_open(z, "zakonczenieEgzekucji") for z in as_list(d4.get("zaleglosci"))),
        "enforcement_discontinued": bool(d4.get("umorzenieEgzekucji")),
        "liquidation": bool(d6.get("likwidacja")),
        "bankruptcy": any(is_open(b, "opisZakonczeniaProcesuUpadlosci") for b in as_list(d6.get("postepowanieUpadlosciowe"))),
        "restructuring": bool(d6.get("postepowanieRestrukturyzacyjneNaprawczePrzymusowaRestrukturyzacjaUporzadkowanaLikwidacja")
                              or d6.get("postepowanieUkladowe")),
        "dissolved": bool(d6.get("rozwiazanieUniewaznienie")),
        "suspended": any(s.get("dataZawieszenia") and not s.get("dataWznowienia") for s in suspensions),
        "last_entry_date": str(parse_date(head.get("dataOstatniegoWpisu")) or ""),
    }


def main():
    rows = [extract(json.loads(path.read_text(encoding="utf-8"))["odpis"]) for path in sorted(RAW.glob("*.json"))]
    out = pd.DataFrame(rows).drop_duplicates("krs")
    out.to_csv(PROCESSED / "krs_signals.csv", index=False, encoding="utf-8")
    print(f"{len(out)} extracts: {(out['email'] != '').sum()} emails, {(out['website'] != '').sum()} websites, "
          f"{(out['main_pkd'] != '').sum()} with main PKD, {out['liquidation'].sum()} in liquidation, "
          f"{out['bankruptcy'].sum()} in bankruptcy, {(out['open_arrears'] > 0).sum()} with open arrears, "
          f"{out['suspended'].sum()} suspended")


if __name__ == "__main__":
    main()
