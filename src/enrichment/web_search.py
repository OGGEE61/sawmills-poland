"""Find contact details by searching name + city + NIP in Bing with headless Chrome.

(DuckDuckGo shows a bot challenge on the first query, so it is not usable.)

Usage: web_search.py [limit] [--seed N]
Reads master.csv + verification.csv, picks active firms, writes data/processed/web_search.jsonl.
Resumable (skips NIPs already in the output). Throttled; stops at the first CAPTCHA/block.
"""
import json
import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By

PROCESSED = Path(__file__).resolve().parents[2] / "data" / "processed"
OUTPUT = PROCESSED / "web_search.jsonl"

DELAY = (4.0, 7.0)
PHONE_RE = re.compile(r"(?<!\d)(?:\+48[\s-]?)?(?:\d{3}[\s-]\d{3}[\s-]\d{3}|\d{2}[\s-]\d{3}[\s-]\d{2}[\s-]\d{2}|\d{9})(?!\d)")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# registers / aggregators: useful as a source, but not the firm's own website
DIRECTORIES = ("aleo.com", "krs-online.com.pl", "rejestr.io", "panoramafirm.pl", "krs-pobierz.pl",
               "infoveriti.pl", "pkt.pl", "firmy.net", "owg.pl", "gowork.pl", "biznes.gov.pl",
               "ceidg.gov.pl", "empoweredsystems.com", "facebook.com", "linkedin.com", "wikipedia.org")


LEGAL_FORMS = re.compile(r"\s+(SPÓŁKA (Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ|AKCYJNA|JAWNA|KOMANDYTOWA|PARTNERSKA)|"
                         r"SP\.? ?Z ?O\.? ?O\.?|S\.A\.|SP\. ?J\.|SP\. ?K\.).*$", re.I)


def short_name(name):
    return LEGAL_FORMS.sub("", name.replace('"', "")).strip()


def make_driver():
    opts = webdriver.ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--lang=pl-PL")
    opts.add_argument("--window-size=1280,1600")
    return webdriver.Chrome(options=opts)


def search(driver, query):
    driver.get(f"https://www.bing.com/search?q={quote_plus(query)}&setlang=pl&cc=pl")
    time.sleep(2.5)
    page = driver.page_source.lower()
    if "captcha" in page or "unusual traffic" in page or "g-recaptcha" in page:
        return None
    results = []
    for item in driver.find_elements(By.CSS_SELECTOR, "li.b_algo")[:8]:
        try:
            title = item.find_element(By.CSS_SELECTOR, "h2").text
            cite = item.find_element(By.CSS_SELECTOR, "cite").text
        except Exception:
            continue
        host = re.sub(r"^https?://", "", cite.split(" ")[0].split("\u203a")[0]).split("/")[0]
        results.append({"title": title, "url": "https://" + host, "text": item.text})
    return results


def extract(results):
    phones, emails, sites, sources = set(), set(), [], []
    for r in results:
        host = urlparse(r["url"]).netloc.lower().removeprefix("www.")
        is_dir = any(host.endswith(d) for d in DIRECTORIES)
        found_phones = {re.sub(r"\s|-", "", p) for p in PHONE_RE.findall(r["text"])}
        found_emails = set(EMAIL_RE.findall(r["text"]))
        phones |= found_phones
        emails |= found_emails
        if not is_dir and host and host not in sites:
            sites.append(host)
        if found_phones or found_emails:
            sources.append(host)
    return {"phones": sorted(phones), "emails": sorted(emails), "sites": sites[:3], "sources": sources[:3]}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    limit = int(args[0]) if args else None
    seed = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else 1

    master = pd.read_csv(PROCESSED / "master.csv", dtype=str).drop_duplicates("nip")
    ver = pd.read_csv(PROCESSED / "verification.csv", dtype=str)[["nip", "verification"]]
    firms = master.merge(ver, on="nip")
    firms = firms[firms["verification"].isin(["CZYNNY", "ZWOLNIONY"])]

    done = set()
    if OUTPUT.exists():
        done = {json.loads(line)["nip"] for line in OUTPUT.open(encoding="utf-8")}
    firms = firms[~firms["nip"].isin(done)]
    firms = firms.sample(frac=1, random_state=seed)
    if limit:
        firms = firms.head(limit)
    print(f"{len(firms)} firms to search")

    driver = make_driver()
    try:
        with open(OUTPUT, "a", encoding="utf-8") as out:
            for i, row in enumerate(firms.itertuples(), 1):
                query = f"{short_name(row.name)} {row.city or ''} NIP {row.nip}"
                results = search(driver, query)
                if results is None:
                    print("Blocked / CAPTCHA detected - stopping. Try again later.")
                    return
                rec = {"nip": row.nip, "name": row.name, "source": row.source, "query": query,
                       "n_results": len(results), **extract(results)}
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                out.flush()
                print(f"{i}/{len(firms)} {row.name[:40]!r}: {len(rec['phones'])} tel, "
                      f"{len(rec['emails'])} mail, sites={rec['sites'][:1]}", flush=True)
                time.sleep(random.uniform(*DELAY))
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
