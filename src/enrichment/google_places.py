"""Phones and websites from Google Maps listings (Places API, Text Search) -> places.csv

Rural firms often have a Maps listing and no site. Needs a key with the Places API enabled; this is billed per
request, so check Google's current price and start small. A listing counts only if its name shares a distinctive
word with the firm and its address names the firm's city, because the top search hit is often a different firm.

Usage: GOOGLE_PLACES_KEY=... google_places.py [limit]
Takes the highest-priority live firms still missing a phone. Resumable.
"""
import csv
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

from contacts import clean_phone, plain

PROCESSED = Path(__file__).resolve().parents[2] / "data" / "processed"
OUTPUT = PROCESSED / "places.csv"
URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = "places.displayName,places.formattedAddress,places.nationalPhoneNumber,places.websiteUri,places.googleMapsUri,places.rating,places.userRatingCount"
FIELDS = ["nip", "matched", "place_name", "address", "phone", "website", "maps_url", "rating", "reviews", "checked_on"]
GENERIC = {"SPOLKA", "OGRANICZONA", "ODPOWIEDZIALNOSCIA", "JAWNA", "KOMANDYTOWA", "AKCYJNA", "FIRMA", "ZAKLAD", "PRZEDSIEBIORSTWO",
           "PRODUKCYJNO", "HANDLOWO", "USLUGOWE", "HANDLOWE", "USLUGI", "HANDEL", "PRODUKCJA", "DREWNA", "TARTAK", "WYROBY"}
DELAY = 0.2


def words(text):
    return {w for w in re.findall(r"[A-Z0-9]{3,}", plain(text)) if w not in GENERIC}


def is_same_firm(name, city, place):
    place_name = (place.get("displayName") or {}).get("text", "")
    return bool(words(name) & words(place_name)) and plain(city) in plain(place.get("formattedAddress", ""))


def lookup(session, key, name, city):
    response = session.post(URL, timeout=30, json={"textQuery": f"{name} {city}", "languageCode": "pl", "regionCode": "PL", "pageSize": 3},
                            headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELD_MASK})
    response.raise_for_status()
    for place in response.json().get("places", []):
        if is_same_firm(name, city, place):
            return {"matched": True, "place_name": (place.get("displayName") or {}).get("text", ""), "address": place.get("formattedAddress", ""),
                    "phone": clean_phone(place.get("nationalPhoneNumber")), "website": place.get("websiteUri", ""),
                    "maps_url": place.get("googleMapsUri", ""), "rating": place.get("rating", ""), "reviews": place.get("userRatingCount", "")}
    return {"matched": False}


def main():
    key = os.environ.get("GOOGLE_PLACES_KEY")
    if not key:
        sys.exit("Set GOOGLE_PLACES_KEY.")
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    leads = pd.read_csv(PROCESSED / "leads.csv", dtype=str).fillna("")
    firms = leads[(leads["tier"] != "X") & (leads["phone"] == "")]
    write_header = not OUTPUT.exists()
    if OUTPUT.exists():
        firms = firms[~firms["nip"].isin(pd.read_csv(OUTPUT, dtype=str)["nip"])]
    if limit:
        firms = firms.head(limit)
    print(f"{len(firms)} firms to look up")
    session = requests.Session()
    with open(OUTPUT, "a", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, FIELDS)
        if write_header:
            writer.writeheader()
        for i, row in enumerate(firms.itertuples(), 1):
            try:
                record = lookup(session, key, row.name, row.city)
            except requests.RequestException as error:
                print(f"Stopping on API error: {error}")
                return
            writer.writerow({"nip": row.nip, "checked_on": time.strftime("%Y-%m-%d"), **record})
            out.flush()
            print(f"{i}/{len(firms)} {row.name[:40]!r}: {record.get('phone') or '-'}", flush=True)
            time.sleep(DELAY)


if __name__ == "__main__":
    main()
