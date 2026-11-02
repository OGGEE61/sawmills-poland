"""Find firms' websites and contact details by searching name + city + NIP through the Serper API.

Free search engines block automated browsers (DuckDuckGo at the first query, Bing after a few),
so this uses a paid API: about $1 per 1,000 searches. Needs SERPER_API_KEY from serper.dev.

Usage: SERPER_API_KEY=... web_search.py [limit]
Reads leads.csv, takes the highest-priority live firms without a website or phone, writes
data/processed/web_search.jsonl. Resumable (skips NIPs already in the output). Stops on API errors.
Then re-run crawl_websites.py and build_leads.py. Start with limit 50 and check the hit rate.
"""
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests

PROCESSED = Path(__file__).resolve().parents[2] / "data" / "processed"
OUTPUT = PROCESSED / "web_search.jsonl"
SERPER_URL = "https://google.serper.dev/search"

DELAY = 0.3
PHONE_RE = re.compile(r"(?<!\d)(?:\+48[\s-]?)?(?:\d{3}[\s-]\d{3}[\s-]\d{3}|\d{2}[\s-]\d{3}[\s-]\d{2}[\s-]\d{2}|\d{9})(?!\d)")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# registers / aggregators: useful as a source, but not the firm's own website
DIRECTORIES = ("aleo.com", "krs-online.com.pl", "rejestr.io", "panoramafirm.pl", "krs-pobierz.pl",
               "infoveriti.pl", "pkt.pl", "firmy.net", "owg.pl", "gowork.pl", "biznes.gov.pl",
               "ceidg.gov.pl", "empoweredsystems.com", "facebook.com", "linkedin.com", "wikipedia.org",
               "olx.pl", "allegro.pl", "oferteo.pl", "youtube.com", "instagram.com", "dnb.com", "gov.pl")


LEGAL_FORMS = re.compile(r"\s+(SPÓŁKA (Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ|AKCYJNA|JAWNA|KOMANDYTOWA|PARTNERSKA)|"
                         r"SP\.? ?Z ?O\.? ?O\.?|S\.A\.|SP\. ?J\.|SP\. ?K\.).*$", re.I)


def short_name(name):
    return LEGAL_FORMS.sub("", name.replace('"', "")).strip()


def search(session, api_key, query):
    response = session.post(SERPER_URL, headers={"X-API-KEY": api_key}, timeout=30,
                            json={"q": query, "gl": "pl", "hl": "pl", "num": 8})
    response.raise_for_status()
    results = []
    for item in response.json().get("organic", []):
        host = urlparse(item.get("link", "")).netloc
        results.append({"title": item.get("title", ""), "url": "https://" + host,
                        "text": f"{item.get('title', '')} {item.get('snippet', '')}"})
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
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        sys.exit("Set SERPER_API_KEY (serper.dev).")
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None

    leads = pd.read_csv(PROCESSED / "leads.csv", dtype=str).fillna("")
    firms = leads[(leads["tier"] != "X") & ((leads["website"] == "") | (leads["phone"] == ""))]

    done = set()
    if OUTPUT.exists():
        done = {json.loads(line)["nip"] for line in OUTPUT.open(encoding="utf-8")}
    firms = firms[~firms["nip"].isin(done)]
    if limit:
        firms = firms.head(limit)
    print(f"{len(firms)} firms to search")

    session = requests.Session()
    with open(OUTPUT, "a", encoding="utf-8") as out:
        for i, row in enumerate(firms.itertuples(), 1):
            query = f"{short_name(row.name)} {row.city} NIP {row.nip}"
            try:
                results = search(session, api_key, query)
            except requests.RequestException as error:
                print(f"Stopping on API error: {error}")
                return
            rec = {"nip": row.nip, "name": row.name, "source": row.source, "query": query,
                   "n_results": len(results), **extract(results)}
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            print(f"{i}/{len(firms)} {row.name[:40]!r}: {len(rec['phones'])} tel, "
                  f"{len(rec['emails'])} mail, sites={rec['sites'][:1]}", flush=True)
            time.sleep(DELAY)


if __name__ == "__main__":
    main()
