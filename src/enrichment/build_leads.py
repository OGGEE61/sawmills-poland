"""Join every source into one ranked sales list -> data/processed/leads.csv

One row per firm, with who to call, how to reach them, which machine to offer, why they rank there, and what to say.
We sell wood chippers and briquette machines of 0.5-2 t/h, a Weima sub-brand for the smallest clients, so the buyer
is a small or mid-sized firm with wood waste to get rid of or burn.

Scores are hand-set rules, not a model trained on sales. Each one is 0-100 and kept separate on purpose:
  fit       does it produce wood waste, and how much is its core business?
  capacity  is it the right size? Big plants score low on purpose
  timing    is there a sign it is dealing with waste, biomass or investing now?
  reach     can we contact someone today? (not part of priority: a great firm with no phone is a research job)
priority = 0.45 fit + 0.30 capacity + 0.25 timing
"""
import json
import re
from datetime import date

import pandas as pd

from crawl_websites import PARKED_RE, PLACEHOLDER_MAIL_RE
from contacts import PROCESSED, clean_email, clean_phone, email_domain, mask_fits, missing, pair_fits, plain, read_ceidg, registry_contacts

TODAY = date.today()
WEIGHTS = {"fit": 0.45, "capacity": 0.30, "timing": 0.25}
TIERS = [("A", 75), ("B", 65), ("C", 50), ("D", 0)]
BIG_CAPITAL = 5_000_000
BIG_EU_VALUE = 5_000_000
SHARED_CONTACT_LIMIT = 3  # the same phone or email on this many unrelated sites is a web agency, not the firm

# Which machine suits which firm, by main PKD: (points, chipper, briquetter, typical waste).
# These are assumptions from general wood-industry knowledge: correct them from real sales conversations.
WASTE_RULES = [
    ("16.10", 70, True, True, "zrzyny, trociny"), ("16.11", 70, True, True, "zrzyny, trociny"), ("16.12", 60, True, True, "trociny, wióry"),
    ("16.24", 65, True, True, "odcinki, trociny"), ("16.23", 60, True, True, "ścinki, wióry"), ("16.25", 60, True, True, "ścinki, wióry"), ("16.22", 60, False, True, "wióry, pył"),
    ("16.21", 50, True, True, "ścinki, pył"), ("16.29", 50, False, True, "wióry, trociny"), ("16.", 50, False, True, "wióry, trociny"),
    ("31.0", 50, True, True, "ścinki, pył"),
    # assumed stationary machines: forestry and landscaping usually need mobile chippers, so these rank low
    ("02.20", 25, True, False, "gałęzie, drewno małowymiarowe"), ("02.40", 20, True, False, "gałęzie, drewno małowymiarowe"),
    ("81.30", 15, True, False, "gałęzie, wycinka"),
]
SAW_NAME_RE = re.compile(r"TARTAK|TARCIC|\bTRAK\b|SAWMILL|PRZERÓB DREWNA|PRZETARCIE", re.I)
WOOD_NAME_RE = re.compile(r"DREW|DRZEW|WOOD|TIMBER|\bLAS\b|LEŚN|LESN|PALET|STOLAR|CIESIEL|WIĘŹB|\bHOLZ", re.I)
WINDOW_NAME_RE = re.compile(r"\bOKN|OKIEN|WINDOW|FENSTER", re.I)
PKD_TAGS = {"16.21": "płyty", "16.22": "podłogi", "16.23": "więźba", "16.25": "okna", "16.24": "palety", "16.29": "wyroby z drewna",
            "02.20": "pozyskanie drewna", "02.40": "usługi leśne", "31.0": "meble", "46.73": "handel drewnem"}
ROLE_RANK = ["PREZES", "WŁAŚCICIEL", "WSPÓLNIK", "WICEPREZES", "DYREKTOR", "ZARZĄD", "CZŁONEK", "PROKURENT"]
KIND_LABEL = {"WASTE": "odpady/biomasa", "MACHINERY": "maszyny/technologia", "ENERGY": "energia", "EXPORT": "eksport", "LIQUIDITY": "płynność", "OTHER": "inne"}


def years_since(text):
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})|(\d{2})\.(\d{2})\.(\d{4})", str(text))
    if not match:
        return None
    year = int(match.group(1) or match.group(6))
    return TODAY.year - year


def yes(value):
    return str(value) == "True"


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def nice_name(name):
    return " ".join(part.capitalize() if "-" not in part else "-".join(p.capitalize() for p in part.split("-"))
                    for part in str(name).split())


# ---------- people ----------
def role_rank(role):
    for rank, word in enumerate(ROLE_RANK):
        if word in role.upper():
            return rank
    return len(ROLE_RANK)


def initials(mask):
    parts = mask.split()
    return " ".join(p[0] + "." for p in parts[:1] + parts[-1:]) if parts else ""


def share_note(owner):
    if owner.get("all"):
        return "100% udziałów"
    found = re.match(r"\s*([\d .]+)\s+UDZIA", owner.get("shares", ""))
    return f"{found.group(1).strip()} udz." if found else ""


NOT_A_PERSON = {"SPOLKA", "JAWNA", "KOMANDYTOWA", "AKCYJNA", "PARTNERSKA", "ZAKLAD", "FIRMA", "TARTAK", "BIURO", "KONTAKT", "INFO"}


def pair_in_words(mask, words):
    """Two neighbouring words, in either order, that fit the mask's first name and surname."""
    words = [word for word in words if plain(word) not in NOT_A_PERSON]
    for left, right in zip(words, words[1:]):
        if pair_fits(mask, left, right):
            return f"{left} {right}"
        if pair_fits(mask, right, left):
            return f"{right} {left}"
    return None


def resolve_name(mask, full_names, firm_name, emails, site_names):
    """A KRS mask becomes a full name only when a public source of this same firm fits it. Returns (name, source)."""
    fit = next((n for n in full_names if mask_fits(mask, n)), None)
    if fit:
        return nice_name(fit), "Biała Lista"
    fit = pair_in_words(mask, re.findall(r"[^\W\d_]{3,}", firm_name))
    if fit:
        return nice_name(fit), "nazwa firmy"
    if site_names.get(mask):
        return nice_name(site_names[mask]), "strona firmy"
    for email in emails:
        fit = pair_in_words(mask, re.findall(r"[^\W\d_]{3,}", email.split("@")[0]))
        if fit:
            return nice_name(fit), "adres e-mail (bez polskich znaków)"
    return "", ""


def krs_people(signals, ver, firm_name="", emails=(), site_names=None):
    """People with roles, with a full name when a public source fits, else initials from the KRS mask."""
    site_names = site_names or {}
    full_names = []
    for field in ("representatives", "partners", "authorized_clerks"):
        if ver is not None and not missing(ver.get(field)):
            full_names += [n.strip() for n in str(ver[field]).split(";") if n.strip()]
    people = []
    for person in json.loads(signals.get("people") or "[]"):
        name, source = resolve_name(person["mask"], full_names, firm_name, emails, site_names)
        people.append({"role": person["role"], "name": name, "name_source": source, "initials": initials(person["mask"])})
    owners = json.loads(signals.get("owners") or "[]")
    for owner in owners:
        name, source = resolve_name(owner["mask"], full_names, firm_name, emails, site_names)
        note = share_note(owner)
        for person in people:
            if person["initials"] == initials(owner["mask"]):
                person["note"] = note
                person["name"] = person["name"] or name
                person["name_source"] = person["name_source"] or source
                break
        else:
            people.append({"role": "WSPÓLNIK", "name": name, "name_source": source, "initials": initials(owner["mask"]), "note": note})
    if not people:
        people = [{"role": "", "name": nice_name(n), "initials": ""} for n in full_names]
    people.sort(key=lambda p: (role_rank(p["role"]), 0 if p["name"] else 1))
    return people


# ---------- scores ----------
def waste_rule(main):
    for code in main.split("; "):
        for rule in WASTE_RULES:
            if code.startswith(rule[0]):
                return rule
    return None


def product_for(row):
    rule = waste_rule(row["main_pkd"])
    tags = row["tags"]
    chipper, briquetter = (rule[2], rule[3]) if rule else (False, False)
    if "tartak" in tags or "palety" in tags:
        chipper = briquetter = True
    if "strugarnia" in tags or "meble" in tags:
        briquetter = True
    if "kocioł/biomasa" in tags or "suszarnia" in tags:
        chipper = True
    if not (chipper or briquetter) and row["fit"] >= 30:
        chipper = briquetter = True
    return {(True, True): "Rębak + brykieciarka", (True, False): "Rębak", (False, True): "Brykieciarka"}.get((chipper, briquetter), "")


def fit_score(row, reasons):
    name = row["name"]
    main, count = row["main_pkd"], row["pkd_count"]
    rule = waste_rule(main)
    if rule:
        score = rule[1]
        reasons.append(f"Odpad: {rule[4]}")
    elif count > 50:
        score = 0
        reasons.append(f"PKD wpisane hurtowo ({count} kodów)")
    elif count > 15:
        score = 10
    else:
        score = 20
    if SAW_NAME_RE.search(name):
        score += 30
        reasons.append("„tartak” w nazwie")
    elif WOOD_NAME_RE.search(name):
        score += 15
    tags = row["tags"]
    if "tartak" in tags:
        score += 20
        reasons.append("Strona potwierdza tartak")
    if "odpady drzewne" in tags:
        score += 15
        reasons.append("Strona: wspomina odpady")
    if "suszarnia" in tags or "kocioł/biomasa" in tags:
        score += 10
        reasons.append("Potrzebuje ciepła (suszarnia/kocioł)")
    if "sprzedaje odpady" in tags:
        reasons.append("Już sprzedaje odpady")
    if "ma brykieciarkę" in tags:
        reasons.append("Wspomina brykiet: wymiana lub większa wydajność")
    if "ma rębak" in tags:
        reasons.append("Wspomina rębak: wymiana lub drugi")
    if row["eu_wood"]:
        score += 5
    return min(score, 100)


def size_band(row):
    """The machines do 0.5-2 t/h: big plants belong with the main Weima line, micro firms cannot justify the machine."""
    if (row["legal_form"] == "SPÓŁKA AKCYJNA" or row["has_group_accounts"] or row["has_supervisory_board"]
            or row["share_capital"] >= BIG_CAPITAL or row["eu_value"] >= BIG_EU_VALUE):
        return "duża"
    # below the VAT threshold there is little turnover, so probably too little waste and money
    if row["verification"] in ("ZWOLNIONY", "NIEZAREJESTROWANY"):
        return "mała"
    # no size data for sole traders, so these stand in for scale: own website, EU project, more than one site
    if row["legal_form"] == "JDG" and not (row["website"] or row["eu_value"] or row["extra_sites"] or row["local_units"]):
        return "mała"
    return "pasuje"


def capacity_score(row, reasons):
    """Is the firm the right size for these machines? Not "the bigger the better"."""
    row["size_band"] = size_band(row)
    if row["size_band"] == "duża":
        reasons.append("Duża firma: raczej główna linia Weima")
        return 15
    score = 40
    if row["verification"] == "CZYNNY":
        score += 20
    age = row["age"]
    if age is not None and age >= 5:
        score += 15
    elif age is not None and age >= 2:
        score += 8
    if row["extra_sites"] or row["branches"] or row["local_units"]:
        score += 15
        reasons.append("Więcej niż jeden zakład")
    if row["latest_filing_year"] >= TODAY.year - 2:
        score += 10
    capital = row["share_capital"]
    if capital >= 50_000:
        score += 10
    if capital >= 200_000:
        reasons.append(f"Kapitał {capital / 1_000_000:.1f} mln zł".replace(".", ",") if capital >= 1_000_000 else f"Kapitał {capital / 1000:.0f} tys. zł")
    value = row["eu_value"]
    if value >= 50_000:
        score += 20
        reasons.append(f"Projekty UE za {value / 1_000_000:.1f} mln zł".replace(".", ",") if value >= 1_000_000 else f"Projekty UE za {value / 1000:.0f} tys. zł")
    if row["size_band"] == "mała":
        reasons.append("Mała skala: zwolniona z VAT lub bez VAT" if row["verification"] in ("ZWOLNIONY", "NIEZAREJESTROWANY")
                       else "Mała skala: JDG bez własnej strony, projektu UE i drugiego zakładu")
        return min(score, 30)
    return min(score, 100)


def timing_score(row, reasons):
    score = 0
    projects = row["eu_projects"]
    def is_live(project):
        return project["end"] >= TODAY.isoformat() or (years_since(project["start"]) or 99) <= 3

    waste = [p for p in projects if p["kind"] == "WASTE"]
    machinery = [p for p in projects if p["kind"] == "MACHINERY"]
    if any(is_live(p) for p in waste):
        score = 95
        reasons.append("Świeży projekt UE: odpady/biomasa")
    elif any(is_live(p) for p in machinery):
        score = 75
        reasons.append("Świeży projekt UE: maszyny, więcej odpadu")
    elif waste:
        score = 45
        reasons.append("Wcześniejszy projekt UE: odpady/biomasa")
    elif [p for p in projects if p["kind"] in ("OTHER", "EXPORT") and p["end"] >= TODAY.isoformat()]:
        score = 40
        reasons.append("Trwający projekt UE")
    elif machinery:
        score = 30
        reasons.append("Wcześniejszy projekt UE: maszyny")
    elif projects:
        score = 15
    age = row["age"]
    if age is not None and age <= 2:
        score = max(score, 25)
        reasons.append("Nowa firma, kompletuje wyposażenie")
    return score


def reach_score(row):
    score = 0
    if row["phone"]:
        score += 50
    if row["email"]:
        score += 30 if email_domain(row["email"]) else 25
    if row["website"]:
        score += 5
    if row["contact_person"]:
        score += 15
    return min(score, 100)


def blockers(row):
    """Hard stops: firm is closing or closed. Kept in the file but hidden by default."""
    out = []
    if row["status"] == "W LIKWIDACJI" or row["liquidation"]:
        out.append("W likwidacji")
    if row["bankruptcy"]:
        out.append("Upadłość")
    if row["dissolved"]:
        out.append("Rozwiązanie spółki")
    if row["suspended"]:
        out.append("Działalność zawieszona")
    if row["verification"] == "WYKRESLONY":
        out.append("Wykreślona z VAT")
    return out


def warnings(row):
    out = []
    if row["open_arrears"]:
        out.append(f"Zaległości w KRS: {row['open_arrears']}")
    if row["enforcement_discontinued"]:
        out.append("Umorzona egzekucja")
    if row["restructuring"]:
        out.append("Restrukturyzacja/układ")
    if row["source"] == "KRS" and row["filings_count"] and row["latest_filing_year"] and row["latest_filing_year"] < TODAY.year - 3:
        out.append(f"Ostatnie sprawozdanie za {row['latest_filing_year']}")
    return out


def opening_line(row):
    """A true, specific first sentence for the salesperson, from the strongest fact we hold."""
    def short_title(project):
        title = project["title"]
        return title if len(title) <= 110 else title[:110].rsplit(" ", 1)[0] + "…"

    projects = row["eu_projects"]
    waste = sorted((p for p in projects if p["kind"] == "WASTE"), key=lambda p: p["start"], reverse=True)
    machinery = sorted((p for p in projects if p["kind"] == "MACHINERY"), key=lambda p: p["start"], reverse=True)
    if waste:
        return f"Widzę Wasz projekt UE z {waste[0]['start'][:4]}: „{short_title(waste[0])}”. Jak w tym projekcie zagospodarowujecie odpad drzewny?"
    if machinery and (machinery[0]["end"] >= TODAY.isoformat() or (years_since(machinery[0]["start"]) or 99) <= 3):
        return f"Widzę Wasz projekt UE z {machinery[0]['start'][:4]}: „{short_title(machinery[0])}”. Czy przy większej produkcji nadążacie z odbiorem odpadu?"
    tags = row["tags"]
    if "ma brykieciarkę" in tags:
        return "Widzę, że wspominacie o brykiecie. Na czym go robicie i czy ta maszyna nadąża za ilością trocin?"
    if "sprzedaje odpady" in tags:
        return "Widzę, że sprzedajecie odpady drzewne. Liczyliście, ile więcej dałby z nich brykiet lub zrębka?"
    if "suszarnia" in tags or "kocioł/biomasa" in tags:
        return "Skoro macie suszarnię lub kocioł, potrzebujecie paliwa. Palicie własnym odpadem, czy go kupujecie?"
    if "palety" in tags or row["main_pkd"].startswith("16.24"):
        return "Przy paletach zostaje sporo odcinków i trocin. Co dziś z nimi robicie: sprzedajecie, palicie, czy płacicie za odbiór?"
    if row["main_pkd"].startswith(("02.20", "02.40", "81.30")):
        return "Co robicie z gałęziami i drewnem małowymiarowym po wycince: zostawiacie, wozicie, czy macie własny rębak?"
    if row["main_pkd"].startswith(("16.22", "16.23", "16.25", "16.29", "31.0")) or "strugarnia" in tags or "meble" in tags:
        return "Przy obróbce zostają wióry i pył. Jak dziś się ich pozbywacie i ile to kosztuje miesięcznie?"
    return "Co dziś robicie z trocinami i zrzynami: sprzedajecie, palicie, czy płacicie za odbiór?"


# ---------- assembling ----------
def load_eu():
    eu = pd.read_csv(PROCESSED / "eu_projects.csv", dtype=str).fillna("")
    grouped = {}
    for rec in eu.to_dict("records"):
        grouped.setdefault(rec["nip"], []).append({
            "title": rec["title"], "kind": rec["kind"], "kind_label": KIND_LABEL.get(rec["kind"], ""), "start": rec["start"],
            "end": rec["end"], "value": number(rec["project_value_pln"]), "funding": number(rec["eu_funding_pln"]),
            "place": rec["place"][:80], "match": rec["match_type"], "wood": rec["mentions_wood"] == "True"})
    for projects in grouped.values():
        projects.sort(key=lambda p: p["start"], reverse=True)
    return grouped


def load_sites():
    try:
        sites = pd.read_csv(PROCESSED / "website_contacts.csv", dtype=str).fillna("")
    except FileNotFoundError:
        return {}
    sites = sites[(sites["verified"] == "True") & ~sites["page_title"].str.contains(PARKED_RE)]
    sites["emails"] = sites["emails"].map(lambda text: "; ".join(e for e in text.split("; ") if not PLACEHOLDER_MAIL_RE.search(e)))
    owners = {}
    for rec in sites.to_dict("records"):
        for contact in rec["phones"].split("; ") + rec["emails"].split("; "):
            owners.setdefault(contact, set()).add(rec["site"])
    shared = {contact for contact, hosts in owners.items() if contact and len(hosts) >= SHARED_CONTACT_LIMIT}
    best = {}
    for rec in sites.to_dict("records"):
        rec["phones"] = "; ".join(p for p in rec["phones"].split("; ") if p not in shared)
        rec["emails"] = "; ".join(e for e in rec["emails"].split("; ") if e not in shared)
        if rec["nip"] not in best or rec["nip_on_site"] == "True":
            best[rec["nip"]] = rec
    return best


def load_optional(name):
    path = PROCESSED / name
    if not path.exists():
        return {}
    return pd.read_csv(path, dtype=str).fillna("").drop_duplicates("nip").set_index("nip").to_dict("index")


def change_notes(rows):
    """What changed since the last build, from facts only, so a scoring tweak does not flag every firm."""
    path = PROCESSED / "leads.csv"
    if not path.exists():
        return
    previous = pd.read_csv(path, dtype=str).fillna("").drop_duplicates("nip").set_index("nip").to_dict("index")
    for row in rows:
        before = previous.get(row["nip"])
        notes = []
        if before is None:
            notes.append("Nowa na liście")
        else:
            if len(row["eu_projects"]) > int(number(before.get("eu_count"))):
                notes.append("Nowy projekt UE")
            if row["phone"] and not before.get("phone"):
                notes.append("Nowy telefon")
            if row["email"] and not before.get("email"):
                notes.append("Nowy e-mail")
            if row["blockers"] and not before.get("blockers"):
                notes.append("Firma się zamyka")
            if row["warnings"] and not before.get("warnings"):
                notes.append("Nowe ostrzeżenie")
        row["changes"] = "; ".join(notes)


def load_search():
    path = PROCESSED / "web_search.jsonl"
    if not path.exists():
        return {}
    return {json.loads(line)["nip"]: json.loads(line) for line in path.open(encoding="utf-8")}


def build_rows():
    firms = registry_contacts()
    ver = pd.read_csv(PROCESSED / "verification.csv", dtype=str).drop_duplicates("nip").set_index("nip").to_dict("index")
    krs_full = pd.read_csv(PROCESSED / "tartaki_full.csv", dtype=str).fillna("")
    expansion_path = PROCESSED / "expansion_firms.csv"
    if expansion_path.exists():
        krs_full = pd.concat([krs_full, pd.read_csv(expansion_path, dtype=str).fillna("")], ignore_index=True).fillna("")
    krs_full["krs"] = krs_full["krs"].str.zfill(10)
    krs_full = krs_full.drop_duplicates("krs").set_index("krs").to_dict("index")
    signals = pd.read_csv(PROCESSED / "krs_signals.csv", dtype=str).fillna("").set_index("krs").to_dict("index")
    ceidg = read_ceidg().fillna("")
    ceidg = ceidg.drop_duplicates("CEIDG_ID").set_index("CEIDG_ID").to_dict("index")
    eu = load_eu()
    sites = load_sites()
    searched = load_search()
    gus = load_optional("gus.csv")
    places = load_optional("places.csv")

    rows = []
    for firm in firms.to_dict("records"):
        nip, key, source = firm["nip"], firm["key"], firm["source"]
        verification = ver.get(nip)
        sig = signals.get(key, {}) if source == "KRS" else {}
        projects = eu.get(nip, [])
        site = sites.get(nip, {})
        search_hit = searched.get(nip, {})
        gus_hit = gus.get(nip, {})
        place = places.get(nip, {}) if places.get(nip, {}).get("matched") == "True" else {}
        row = {
            "nip": nip, "source": source, "source_id": key, "name": firm["name"],
            "verification": (verification or {}).get("verification", ""),
            "eu_projects": projects,
            "eu_value": sum(p["value"] for p in projects),
            "eu_wood": any(p["wood"] for p in projects),
            "tags": site.get("tags", ""), "site_verified": bool(site), "local_units": number(gus_hit.get("local_units")) > 0,
            "maps_url": place.get("maps_url", ""),
        }
        if source == "KRS":
            base = krs_full.get(key, {})
            row.update(
                legal_form=base.get("legal_form", ""), status={"ACTIVE": "AKTYWNY", "LIQUIDATION": "W LIKWIDACJI"}.get(base.get("status_from_discovery"), "AKTYWNY"),
                voivodeship=base.get("voivodeship") or sig.get("voivodeship_raw", ""), county=sig.get("county_raw", ""),
                municipality=sig.get("municipality_raw", ""), city=base.get("city", ""),
                street=" ".join(x for x in (base.get("street", ""), base.get("building_no", "")) if x),
                postal_code=base.get("postal_code", ""), post_office=base.get("post_office", ""), started=base.get("registration_date", ""),
                main_pkd=sig.get("main_pkd", "") or base.get("pkd_main", ""), pkd_count=int(number(sig.get("pkd_count"))),
                all_pkd=sig.get("all_pkd", ""), share_capital=number(sig.get("share_capital_pln")),
                latest_filing_year=int(number(sig.get("latest_filing_year"))), filings_count=int(number(sig.get("filings_count"))),
                branches=int(number(sig.get("branches"))), open_arrears=int(number(sig.get("open_arrears"))), extra_sites=False,
                has_group_accounts=yes(sig.get("has_group_accounts")), has_supervisory_board=yes(sig.get("has_supervisory_board")),
                enforcement_discontinued=yes(sig.get("enforcement_discontinued")), liquidation=yes(sig.get("liquidation")),
                bankruptcy=yes(sig.get("bankruptcy")), restructuring=yes(sig.get("restructuring")),
                dissolved=yes(sig.get("dissolved")), suspended=yes(sig.get("suspended")))
            people = []
            if sig:
                mails = [e for e in [firm["email"]] + site.get("emails", "").split("; ") if e]
                people = krs_people(sig, verification, firm["name"], mails, json.loads(site.get("site_names") or "{}"))
        else:
            base = ceidg.get(key, {})
            pkd_codes = re.findall(r'"kod": "(\d{4}[A-Z])"', base.get("detail.pkd", ""))
            pkd_dotted = [f"{c[:2]}.{c[2:4]}.{c[4]}" for c in pkd_codes]
            main = base.get("detail.pkdGlowny.kod", "")
            building = " ".join(x for x in (base.get("detail.adresDzialalnosci.ulica", ""), base.get("detail.adresDzialalnosci.budynek", "")) if not missing(x))
            row.update(
                legal_form="JDG", status=base.get("STATUS", "AKTYWNY"), voivodeship=base.get("detail.adresDzialalnosci.wojewodztwo", ""),
                county=base.get("detail.adresDzialalnosci.powiat", ""), municipality=base.get("detail.adresDzialalnosci.gmina", ""),
                city=base.get("detail.adresDzialalnosci.miasto", ""), street=building, postal_code=base.get("detail.adresDzialalnosci.kod", ""), post_office="",
                started=base.get("detail.dataRozpoczecia", ""), main_pkd=f"{main[:2]}.{main[2:4]}.{main[4:]}" if main else "",
                pkd_count=len(pkd_dotted), all_pkd="; ".join(pkd_dotted), share_capital=0.0, latest_filing_year=0, filings_count=0,
                branches=0, open_arrears=0, extra_sites=not missing(base.get("detail.adresyDzialalnosciDodatkowe")),
                has_group_accounts=False, has_supervisory_board=False, enforcement_discontinued=False, liquidation=False,
                bankruptcy=not missing(base.get("detail.upadlosci")), restructuring=False, dissolved=False, suspended=False)
            owner = " ".join(x for x in (base.get("detail.wlasciciel.imie", ""), base.get("detail.wlasciciel.nazwisko", "")) if not missing(x))
            people = [{"role": "WŁAŚCICIEL", "name": nice_name(owner), "initials": ""}] if owner else []
        row["age"] = years_since(row["started"])

        # contact details: register first, then the firm's own site, then search snippets (least trusted)
        site_phones = [p for p in site.get("phones", "").split("; ") if p]
        site_emails = [e for e in site.get("emails", "").split("; ") if e]
        search_phones = [clean_phone(p) for p in search_hit.get("phones", [])]
        search_emails = [clean_email(e) for e in search_hit.get("emails", [])]
        phone, phone_source = next(((p, s) for p, s in [(firm["phone"], "rejestr"), (clean_phone(gus_hit.get("phone")), "GUS")]
                                    + [(p, "strona firmy") for p in site_phones] + [(place.get("phone", ""), "Mapy Google")]
                                    + [(p, "wyszukiwarka") for p in search_phones if p] if p), ("", ""))
        email, email_source = next(((e, s) for e, s in [(firm["email"], "rejestr"), (clean_email(gus_hit.get("email")), "GUS")]
                                    + [(e, "strona firmy") for e in site_emails]
                                    + [(e, "wyszukiwarka") for e in search_emails if e] if e), ("", ""))
        website = site.get("final_url", "") or (f"https://{firm['site']}" if firm["site_source"] == "rejestr" else "")
        lead = next((p for p in people if p["name"]), people[0] if people else None)
        row.update(
            phone=phone, phone_source=phone_source, email=email, email_source=email_source,
            other_phones="; ".join(p for p in site_phones if p != phone), other_emails="; ".join(e for e in site_emails if e != email),
            website=website, contact_url=site.get("contact_url", ""),
            contact_person=(lead["name"] if lead else ""), contact_role=(nice_name(lead["role"]) if lead else ""),
            contact_initials=(lead["initials"] if lead and not lead["name"] else ""),
            contact_person_source=(lead.get("name_source", "rejestr") if lead else ""), people=people,
        )
        pkd_tags = [tag for prefix, tag in PKD_TAGS.items() if prefix in row["all_pkd"] and row["pkd_count"] <= 50]
        # plastic and aluminium window makers leave no wood waste, so the name counts only with a wood main activity
        if WINDOW_NAME_RE.search(row["name"]) and row["main_pkd"].startswith("16."):
            pkd_tags.append("okna")
        row["all_tags"] = "; ".join(dict.fromkeys([t for t in row["tags"].split("; ") if t] + pkd_tags))
        rows.append(row)
    return rows


def score(row):
    reasons = []
    row["fit"] = fit_score(row, reasons)
    row["capacity"] = capacity_score(row, reasons)
    row["timing"] = timing_score(row, reasons)
    row["reach"] = reach_score(row)
    row["priority"] = round(sum(row[name] * weight for name, weight in WEIGHTS.items()))
    row["product"] = product_for(row)
    row["blockers"] = "; ".join(blockers(row))
    row["warnings"] = "; ".join(warnings(row))
    tier = next(label for label, floor in TIERS if row["priority"] >= floor)
    # weak evidence of being a sawmill caps the tier however big the firm looks
    if row["fit"] < 40 and tier in ("A", "B"):
        tier = "C"
    if row["warnings"] and tier == "A":
        tier = "B"
    # wrong size for these machines however good the other signals are
    if row["size_band"] != "pasuje" and tier in ("A", "B"):
        tier = "C"
    row["tier"] = "X" if row["blockers"] else tier
    row["action"] = "Zadzwoń" if row["phone"] else ("Napisz" if row["email"] else "Znajdź kontakt")
    row["reasons"] = "; ".join(reasons)
    row["opening"] = opening_line(row)
    return row


COLUMNS = ["tier", "priority", "fit", "capacity", "timing", "reach", "action", "product", "size_band", "changes", "name", "nip", "source", "source_id", "legal_form", "status",
           "verification", "voivodeship", "county", "municipality", "city", "street", "postal_code", "post_office", "contact_person", "contact_role",
           "contact_person_source", "contact_initials", "phone", "phone_source", "email", "email_source", "other_phones", "other_emails", "website", "contact_url",
           "all_tags", "reasons", "warnings", "blockers", "opening", "started", "main_pkd", "pkd_count", "share_capital", "latest_filing_year",
           "eu_count", "eu_value", "maps_url", "people_json", "eu_json"]


def main():
    rows = [score(row) for row in build_rows()]
    change_notes(rows)
    for row in rows:
        row["eu_count"] = len(row["eu_projects"])
        row.setdefault("changes", "")
        row["people_json"] = json.dumps(row["people"], ensure_ascii=False)
        row["eu_json"] = json.dumps(row["eu_projects"][:8], ensure_ascii=False)
    leads = pd.DataFrame(rows)[COLUMNS].sort_values(["priority", "reach"], ascending=False)
    leads.to_csv(PROCESSED / "leads.csv", index=False, encoding="utf-8")

    live = leads[leads["tier"] != "X"]
    print(f"{len(leads)} firms, {len(live)} live, {len(leads) - len(live)} blocked")
    print("tiers:", leads["tier"].value_counts().sort_index().to_dict())
    print("product (live):", live["product"].value_counts().to_dict())
    print("size (live):", live["size_band"].value_counts().to_dict())
    print("changes:", leads["changes"].value_counts().head(6).to_dict())
    print("action:", live["action"].value_counts().to_dict())
    print("with phone:", (live["phone"] != "").sum(), "email:", (live["email"] != "").sum(), "site:", (live["website"] != "").sum(),
          "named person:", (live["contact_person"] != "").sum(), "EU project:", (live["eu_count"] > 0).sum())
    print("source of phone:", live["phone_source"].value_counts().to_dict(), "email:", live["email_source"].value_counts().to_dict())


if __name__ == "__main__":
    main()
