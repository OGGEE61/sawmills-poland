"""Read firms' own websites for phones, emails and what they actually do -> website_contacts.csv

Sites come from the registers, from email domains, and from web_search.jsonl when it exists. Sites found
by search count only if the page shows the firm's NIP or name, because search results are often unrelated.
Polite on purpose: honest user agent, robots.txt respected, one site per worker, at most 4 pages a site.
Resumable: delete website_contacts.csv to re-check everyone.

Usage: crawl_websites.py [limit]
"""
import csv
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import pandas as pd
import requests

from contacts import EMAIL_RE, NOT_OWN_SITE, PROCESSED, clean_phone, clean_site, pair_fits, registry_contacts

OUTPUT = PROCESSED / "website_contacts.csv"
SEARCH_FILE = PROCESSED / "web_search.jsonl"
USER_AGENT = "sawmills-poland-research/1.0 (B2B firm directory; public contact pages only)"
HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "pl,en;q=0.5"}
FIELDS = ["nip", "site", "site_source", "ok", "final_url", "verified", "nip_on_site", "name_on_site", "emails", "phones",
          "contact_url", "tags", "page_title", "site_names", "checked_on"]
WORKERS = 8
MAX_BYTES = 800_000
CONTACT_LINK_RE = re.compile(r"kontakt|contact|o-nas|o_nas|about|firma", re.I)
HREF_RE = re.compile(r"""href\s*=\s*["']([^"'#]+)["']""", re.I)
TEL_LINK_RE = re.compile(r"""href\s*=\s*["']tel:([^"']+)["']""", re.I)
PHONE_TEXT_RE = re.compile(r"(fax|tel|telefon|kom|mob|gsm|phone)[.:\s/]*((?:\+?48[\s-]?)?\(?\d{2,3}\)?[\s-]?\d{2,3}[\s-]?\d{2,3}[\s-]?\d{0,3})", re.I)
WOOD_RE = re.compile(r"tartak|tarcic|drewn|drzewn|więźb|palet", re.I)
WOOD_HITS_NEEDED = 4  # one stray word is not evidence: wygoda.pl passed on that
PARKED_RE = re.compile(r"aftermarket\.pl|domena (jest )?na sprzedaż|ta domena|this domain is for sale|domain is parked|parked free|"
                       r"strona w budowie|under construction|coming soon|namebright", re.I)
PLACEHOLDER_MAIL_RE = re.compile(r"@(email|domain|example|domena|twojadomena|mail|firma)\.|^(j|jan\.kowalski|imie\.nazwisko|user|name)@", re.I)
PERSON_RE = re.compile(r"\b([A-ZŁŚŻŹĆŃÓĄĘ][a-ząćęłńóśźż]{2,}|[A-ZŁŚŻŹĆŃÓĄĘ]{3,})\s+([A-ZŁŚŻŹĆŃÓĄĘ][a-ząćęłńóśźż]{2,}(?:-[A-ZŁŚŻŹĆŃÓĄĘ][a-ząćęłńóśźż]+)?|[A-ZŁŚŻŹĆŃÓĄĘ]{3,})\b")
TAG_PATTERNS = {
    "tartak": r"tartak|tarcic|przetarci|przetarcia|\btrak",
    "więźba": r"więźb|kantówk|konstrukcj\w* drewnian",
    "palety": r"palet|opakowa\w* drewnian|skrzyni",
    "suszarnia": r"suszarn|suszeni\w* drewna|suszeni\w* tarcicy",
    "impregnacja": r"impregn",
    "strugarnia": r"strugan|profilowan|boazeri|podbitk|deski elewacyjn|deski tarasow",
    "odpady drzewne": r"trocin|wiór|zrzyn|zrębk|odpad\w* drzewn|odpad\w* drewn|odpad\w* produkcyjn",
    "sprzedaje odpady": r"sprzedaż\w* (trocin|zrębk|wiór|brykiet|pelet)|trociny na sprzedaż|sprzedam trociny",
    "kocioł/biomasa": r"kocio\w* na (biomas|drewno|zrębk|trocin)|kotłowni|ogrzewani\w* (biomas|zrębk)|biomas",
    "pelet": r"pelet|pellet",
    "ma brykieciarkę": r"brykieciark|brykietownic|produkcj\w* brykiet|brykiet\w* (drzewn|z trocin)|brykiet",
    "ma rębak": r"rębak|rębark|rozdrabniacz",
    "domy": r"domy drewnian|domki|domów drewnian|dom z drewna",
    "meble": r"mebl",
    "cnc": r"\bcnc\b",
    "eksport": r"export|eksport",
}
TAG_RES = {tag: re.compile(pattern, re.I) for tag, pattern in TAG_PATTERNS.items()}
TAG_RE = re.compile(r"<script.*?</script>|<style.*?</style>|<[^>]+>", re.S | re.I)


def fetch(session, url):
    with session.get(url, timeout=12, stream=True, allow_redirects=True) as response:
        if response.status_code != 200 or "html" not in response.headers.get("content-type", "html"):
            return None, url
        body = b""
        for chunk in response.iter_content(65536):
            body += chunk
            if len(body) >= MAX_BYTES:
                break
        for encoding in ("utf-8", "iso-8859-2"):  # older Polish sites
            try:
                return body.decode(encoding), response.url
            except UnicodeDecodeError:
                continue
        return body.decode("utf-8", errors="replace"), response.url


def robots_for(session, base):
    robots = RobotFileParser()
    try:
        response = session.get(urljoin(base, "/robots.txt"), timeout=8)
        robots.parse(response.text.splitlines() if response.status_code == 200 else [])
    except requests.RequestException:
        robots.parse([])
    return robots


def contact_links(html, base_url):
    host = urlparse(base_url).netloc
    links = []
    for href in HREF_RE.findall(html):
        url = urljoin(base_url, href)
        if urlparse(url).netloc == host and CONTACT_LINK_RE.search(href) and url not in links:
            links.append(url)
    links.sort(key=lambda u: 0 if re.search("kontakt|contact", u, re.I) else 1)
    return links[:3]


def phones_from(html, text):
    phones = [clean_phone(p) for p in TEL_LINK_RE.findall(html)]
    phones += [clean_phone(num) for label, num in PHONE_TEXT_RE.findall(text) if label.lower() != "fax"]
    return [p for p in dict.fromkeys(phones) if p]


def emails_from(html, text, host):
    found = [m.group(0).lower() for m in EMAIL_RE.finditer(html + " " + text)]
    found = [e for e in dict.fromkeys(found)
             if not re.search(r"\.(png|jpe?g|gif|svg|webp|css|js)$|sentry|example\.|wixpress|@2x", e) and not PLACEHOLDER_MAIL_RE.search(e)]
    # own-domain addresses first: others may belong to the web agency
    return sorted(found, key=lambda e: 0 if e.split("@")[-1].endswith(host) else 1)[:5]


def names_on_page(masks, text):
    """People the firm itself names: full names on its site that fit a KRS mask of this firm."""
    found = {}
    if isinstance(masks, list):  # sole traders have none
        for first, last in set(PERSON_RE.findall(text)):
            for mask in masks:
                if mask not in found and pair_fits(mask, first, last):
                    found[mask] = f"{first} {last}"
    return found


def krs_masks():
    signals = pd.read_csv(PROCESSED / "krs_signals.csv", dtype=str).fillna("")
    masks = {}
    for krs, people, owners in zip(signals["krs"], signals["people"], signals["owners"]):
        masks[krs] = list({p["mask"] for p in json.loads(people or "[]") + json.loads(owners or "[]") if p.get("mask")})
    return masks


def name_tokens(name):
    words = re.findall(r"[^\W\d_]{4,}", name.upper())
    generic = {"SPÓŁKA", "OGRANICZONĄ", "ODPOWIEDZIALNOŚCIĄ", "JAWNA", "KOMANDYTOWA", "AKCYJNA", "FIRMA", "TARTAK", "ZAKŁAD",
               "PRZEDSIĘBIORSTWO", "PRODUKCYJNO", "HANDLOWO", "USŁUGOWE", "HANDEL", "USŁUGI", "PRODUKCJA", "DREWNA"}
    return [w for w in words if w not in generic]


def crawl(firm):
    record = {"nip": firm["nip"], "site": firm["site"], "site_source": firm["site_source"], "ok": False, "final_url": "",
              "verified": False, "nip_on_site": False, "name_on_site": False, "emails": "", "phones": "", "contact_url": "",
              "tags": "", "page_title": "", "site_names": "", "checked_on": time.strftime("%Y-%m-%d")}
    session = requests.Session()
    session.headers.update(HEADERS)
    html, final = None, None
    for base in (f"https://{firm['site']}/", f"https://www.{firm['site']}/", f"http://{firm['site']}/"):
        try:
            html, final = fetch(session, base)
            if html:
                break
        except (requests.RequestException, UnicodeError, LookupError):
            continue
    if not html or urlparse(final).netloc.lower().removeprefix("www.").endswith(NOT_OWN_SITE):
        return record
    if PARKED_RE.search(html):
        record["site_source"] += " (parked)"
        return record
    robots = robots_for(session, final)
    if not robots.can_fetch(USER_AGENT, final):
        record["site_source"] += " (robots.txt)"
        return record

    pages = [(final, html)]
    links = contact_links(html, final)
    for url in links:
        if not robots.can_fetch(USER_AGENT, url):
            continue
        try:
            time.sleep(1)
            page, resolved = fetch(session, url)
        except (requests.RequestException, UnicodeError, LookupError):
            continue
        if page:
            pages.append((resolved, page))

    host = urlparse(final).netloc.lower().removeprefix("www.")
    emails, phones, all_text = [], [], ""
    for _, page in pages:
        text = re.sub(r"\s+", " ", TAG_RE.sub(" ", page)).replace("&nbsp;", " ")
        all_text += " " + text
        phones += phones_from(page, text)
        emails += emails_from(page, text, host)
    digits = re.sub(r"\D", "", all_text)
    tokens = name_tokens(firm["name"])
    upper = all_text.upper()
    title = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)

    record.update(
        ok=True, final_url=final,
        nip_on_site=firm["nip"] in digits,
        name_on_site=bool(tokens) and all(t in upper for t in tokens[:2]),
        emails="; ".join(dict.fromkeys(emails)), phones="; ".join(list(dict.fromkeys(phones))[:4]),
        contact_url=links[0] if links else "",
        tags="; ".join(tag for tag, pattern in TAG_RES.items() if pattern.search(all_text)),
        page_title=re.sub(r"\s+", " ", title.group(1)).strip()[:120] if title else "",
        site_names=json.dumps(names_on_page(firm.get("masks"), all_text), ensure_ascii=False),
    )
    # a registry or email-domain site belongs to the firm unless it is parked; search hits must prove it
    if firm["site_source"] == "wyszukiwarka":
        record["verified"] = record["nip_on_site"] or record["name_on_site"]
    else:
        record["verified"] = record["nip_on_site"] or record["name_on_site"] or len(WOOD_RE.findall(all_text)) >= WOOD_HITS_NEEDED
    if not record["verified"]:
        record.update(emails="", phones="", tags="", site_names="")
    return record


def search_sites():
    """Sites from sources that can name the wrong firm: search, Google Maps, GUS."""
    rows = []
    if SEARCH_FILE.exists():
        for line in SEARCH_FILE.open(encoding="utf-8"):
            rec = json.loads(line)
            rows += [{"nip": rec["nip"], "site": site} for site in rec.get("sites", [])[:2]]
    for name, column in (("places.csv", "website"), ("gus.csv", "website")):
        path = PROCESSED / name
        if path.exists():
            found = pd.read_csv(path, dtype=str).fillna("")
            rows += [{"nip": nip, "site": clean_site(site)} for nip, site in zip(found["nip"], found[column]) if clean_site(site)]
    return pd.DataFrame(rows, columns=["nip", "site"])


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    firms = registry_contacts()
    firms["masks"] = firms["key"].map(krs_masks())
    known = firms[firms["site"] != ""][["nip", "name", "site", "site_source", "masks"]]
    found = search_sites().merge(firms[["nip", "name", "masks"]], on="nip")
    found["site_source"] = "wyszukiwarka"
    queue = pd.concat([known, found]).drop_duplicates(["nip", "site"])

    done = set()
    write_header = not OUTPUT.exists()
    if OUTPUT.exists():
        previous = pd.read_csv(OUTPUT, dtype=str)
        done = set(zip(previous["nip"], previous["site"]))
    queue = queue[[(n, s) not in done for n, s in zip(queue["nip"], queue["site"])]]
    if limit:
        queue = queue.head(limit)
    print(f"{len(queue)} sites to read")

    with open(OUTPUT, "a", newline="", encoding="utf-8") as out, ThreadPoolExecutor(WORKERS) as pool:
        writer = csv.DictWriter(out, FIELDS)
        if write_header:
            writer.writeheader()
        jobs = {pool.submit(crawl, row): row for row in queue.to_dict("records")}
        stats = {"ok": 0, "verified": 0, "phones": 0, "emails": 0}
        for i, job in enumerate(as_completed(jobs), 1):
            try:
                record = job.result()
            except Exception as error:  # one broken site must not end the run; it is retried next time
                print(f"skipped {jobs[job]['site']}: {error}", flush=True)
                continue
            writer.writerow(record)
            out.flush()
            stats["ok"] += record["ok"]
            stats["verified"] += record["verified"]
            stats["phones"] += bool(record["phones"])
            stats["emails"] += bool(record["emails"])
            if i % 50 == 0:
                print(f"{i}/{len(jobs)} {stats}", flush=True)
    print(f"done: {stats}")


if __name__ == "__main__":
    main()
