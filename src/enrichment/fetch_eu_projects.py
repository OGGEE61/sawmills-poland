"""Find our firms among EU-funded projects -> data/processed/eu_projects.csv

Source: the Ministry's monthly project lists on dane.gov.pl (2014-2020 and 2021-2027). They have no
NIP, so firms are matched by name. match_type says how sure the match is:
  exact    same name and legal form
  reorder  same words in a different order (sole traders), at least three words
  core     same name without the legal form, unique in our list, project in the firm's voivodeship,
           and the project text mentions wood (short names like PROFIL hit unrelated firms otherwise)
"""
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import openpyxl
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
EXTERNAL = ROOT / "data" / "raw" / "external"
DATASETS = {"2014-2020": 1176, "2021-2027": 13939}
API = "https://api.dane.gov.pl/1.4/datasets/{}/resources"

MACHINERY_RE = re.compile(r"maszyn|urządzeń|urządzenia|lini[ią]\w* (technolog|produkc)|\btrak|suszarn|obrabiar|\bcnc\b|"
                          r"strugar|automatyzac|robotyzac|zdolności produkcyjn|technologi\w* produkcji|zakład\w* produkcyjn", re.I)
ENERGY_RE = re.compile(r"fotowolt|odnawialn|\boze\b|termomoderniz|efektywnoś\w* energ|kolektor|solar", re.I)
LIQUIDITY_RE = re.compile(r"kapitał\w* obrotow|płynnoś|covid|pandemi|utrzymanie przedsiębiorstwa|dotacj\w* na kapitał", re.I)
ADVISORY_RE = re.compile(r"doradcz|biznes\s*plan|szkoleni|cyfrow|informatyczn|\berp\b|oprogramowan|e-usług|\bb2b\b|strategi|model\w* biznesow|koncepcj", re.I)
EXPORT_RE = re.compile(r"eksport|targ\w*\b|zagraniczn|międzynarodow|internacjonaliz|promocj", re.I)
# chippers and briquette machines: a project about waste, biomass or circular economy is the strongest signal we have
WASTE_RE = re.compile(r"\bgoz\b|gospodark\w* o obiegu|obieg\w* zamknię|odpad|biomas|brykiet|pelet|pellet|zrębk|trocin|\bwiór|kocioł|kotł", re.I)
# summaries of nearly all projects promise "less waste", so a summary only counts when it names the material
WASTE_SUMMARY_RE = re.compile(r"\bgoz\b|obieg\w* zamknię|biomas|brykiet|pelet|pellet|zrębk|trocin|kocioł na|kotł\w* na", re.I)
WOOD_RE = re.compile(r"drewn|drzewn|tartak|tarcic|\btrak|palet|więźb|deski|desek|wood|timber", re.I)


def classify(title, summary):
    """Title decides first: summaries of energy or export projects often mention machines too."""
    if LIQUIDITY_RE.search(title):
        return "LIQUIDITY"
    if WASTE_RE.search(title):
        return "WASTE"
    if ADVISORY_RE.search(title):
        return "OTHER"
    for kind, pattern in (("ENERGY", ENERGY_RE), ("EXPORT", EXPORT_RE)):
        if pattern.search(title):
            return kind
    if WASTE_SUMMARY_RE.search(summary):
        return "WASTE"
    if MACHINERY_RE.search(title) or MACHINERY_RE.search(summary):
        return "MACHINERY"
    return "OTHER"


LEGAL_FORMS = [
    (r"\bSPOLKA Z OGRANICZONA ODPOWIEDZIALNOSCIA\b|\bSP\s*Z\s*O\s*O\b|\bSP\s*ZOO\b", "SPZOO"),
    (r"\bSPOLKA KOMANDYTOWO AKCYJNA\b|\bS\s*K\s*A\b", "SKA"),
    (r"\bSPOLKA KOMANDYTOWA\b|\bSP\s*K\b", "SPK"),
    (r"\bSPOLKA JAWNA\b|\bSP\s*J\b", "SPJ"),
    (r"\bSPOLKA AKCYJNA\b|\bS\s*A\b", "SA"),
    (r"\bSPOLKA CYWILNA\b|\bS\s*C\b", "SC"),
]
FORM_TOKENS = {"SPZOO", "SKA", "SPK", "SPJ", "SA", "SC"}


def normalize(name):
    text = unicodedata.normalize("NFKD", str(name).replace("Ł", "L").replace("ł", "l"))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).upper()
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    text = re.sub(r"\bW LIKWIDACJI\b", " ", text)
    for pattern, short in LEGAL_FORMS:
        text = re.sub(pattern, short, text)
    return " ".join(text.split())


def core_of(key):
    return " ".join(token for token in key.split() if token not in FORM_TOKENS)


def latest_file(period, dataset_id):
    params = {"per_page": 1, "sort": "-data_date"}
    data = requests.get(API.format(dataset_id), params=params, timeout=60,
                        headers={"Accept": "application/vnd.api+json"}).json()["data"]
    url = data[0]["attributes"]["file_url"]
    path = EXTERNAL / url.rsplit("/", 1)[-1]
    if not path.exists():
        print(f"downloading {url}")
        EXTERNAL.mkdir(parents=True, exist_ok=True)
        with requests.get(url, stream=True, timeout=300) as response:
            response.raise_for_status()
            with open(path, "wb") as out:
                for chunk in response.iter_content(1 << 20):
                    out.write(chunk)
    return path


def read_projects(path):
    sheet = openpyxl.load_workbook(path, read_only=True).worksheets[0]
    columns = None
    for row in sheet.iter_rows(values_only=True):
        if columns is None:
            labels = [str(cell or "") for cell in row]
            if any(label.startswith("Nazwa beneficjenta") for label in labels):
                columns = labels
            continue
        yield dict(zip(columns, row))


def pick(project, prefix):
    for key, value in project.items():
        if key.startswith(prefix):
            return value
    return None


def to_day(value):
    return value.date().isoformat() if isinstance(value, datetime) else str(value or "")[:10]


def build_indexes(master):
    master = master.assign(key=master["name"].map(normalize))
    master["core"] = master["key"].map(core_of)
    master["sorted"] = master["key"].map(lambda k: " ".join(sorted(k.split())))
    exact = master.groupby("key")["nip"].apply(list).to_dict()
    reorder = master[master["key"].str.split().str.len() >= 3].groupby("sorted")["nip"].apply(list).to_dict()
    unique_core = master.groupby("core").filter(lambda g: g["nip"].nunique() == 1)
    unique_core = unique_core[unique_core["core"].str.len() >= 6]
    core = unique_core.drop_duplicates("core").set_index("core")[["nip", "voivodeship"]].to_dict("index")
    return exact, reorder, core


def match(beneficiary, place, indexes):
    exact, reorder, core = indexes
    hits = []
    for part in str(beneficiary).split("|"):
        key = normalize(part)
        if not key:
            continue
        if key in exact:
            hits += [(nip, "exact") for nip in exact[key]]
            continue
        sorted_key = " ".join(sorted(key.split()))
        if sorted_key in reorder:
            hits += [(nip, "reorder") for nip in reorder[sorted_key]]
            continue
        candidate = core.get(core_of(key))
        if candidate and str(candidate["voivodeship"]).upper() in str(place).upper():
            hits.append((candidate["nip"], "core"))
    return hits


def main():
    master = pd.read_csv(PROCESSED / "master.csv", dtype=str).dropna(subset=["nip"])
    indexes = build_indexes(master)
    rows = []
    for period, dataset_id in DATASETS.items():
        path = latest_file(period, dataset_id)
        total = 0
        for project in read_projects(path):
            total += 1
            beneficiary = pick(project, "Nazwa beneficjenta")
            if not beneficiary:
                continue
            place = pick(project, "Miejsce") or ""
            for nip, match_type in match(beneficiary, place, indexes):
                title = str(pick(project, "Tytuł projektu") or pick(project, "Nazwa projektu") or "")
                summary = str(pick(project, "Skrócony opis") or pick(project, "Opis projektu") or "")
                text = f"{title} {summary}"
                rows.append({
                    "nip": nip, "match_type": match_type, "period": period, "beneficiary": beneficiary,
                    "title": title, "summary": summary[:500], "measure": pick(project, "Działanie"),
                    "project_value_pln": pick(project, "Wartość projektu"),
                    "eu_funding_pln": pick(project, "Wartość unijnego") or pick(project, "Dofinansowanie z UE"),
                    "place": place, "start": to_day(pick(project, "Data rozpoczęcia")),
                    "end": to_day(pick(project, "Data zakończenia")),
                    "kind": classify(title, summary), "mentions_wood": bool(WOOD_RE.search(text)),
                    "source_file": path.name,
                })
        print(f"{period}: {total} projects read")
    out = pd.DataFrame(rows).drop_duplicates(["nip", "title", "start"])
    out = out[(out["match_type"] != "core") | out["mentions_wood"]]
    out.to_csv(PROCESSED / "eu_projects.csv", index=False, encoding="utf-8")
    print(f"{len(out)} projects for {out['nip'].nunique()} firms; " + str(out["match_type"].value_counts().to_dict()) + " " + str(out["kind"].value_counts().to_dict()))


if __name__ == "__main__":
    main()
