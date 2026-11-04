"""Phones, emails, websites and local units from the GUS REGON register (BIR 1.1 API) -> gus.csv

Needs a free key from GUS: https://api.stat.gov.pl/Home/RegonApi (the "BIR1" API, version 1.1).

Usage: GUS_API_KEY=... gus_regon.py [limit]    real register, highest-priority firms first; resumable
       gus_regon.py --test NIP [NIP ...]       GUS's public test server and test key; prints, writes nothing
"""
import csv
import html
import os
import re
import sys
import time
from pathlib import Path
from xml.etree import ElementTree

import pandas as pd
import requests

PROCESSED = Path(__file__).resolve().parents[2] / "data" / "processed"
OUTPUT = PROCESSED / "gus.csv"
LIVE_URL = "https://wyszukiwarkaregon.stat.gov.pl/wsBIR/UslugaBIRzewnPubl.svc"
TEST_URL = "https://wyszukiwarkaregontest.stat.gov.pl/wsBIR/UslugaBIRzewnPubl.svc"
TEST_KEY = "abcde12345abcde12345"  # published by GUS for the test server, not a secret
DELAY = 0.5
SESSION_SECONDS = 50 * 60  # GUS sessions expire after an hour
FIELDS = ["nip", "found", "regon", "phone", "email", "website", "local_units", "checked_on"]
ACTION = "http://CIS/BIR/PUBL/2014/07/IUslugaBIRzewnPubl/"
NAMESPACES = ('xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:ns="http://CIS/BIR/PUBL/2014/07" '
              'xmlns:dat="http://CIS/BIR/PUBL/2014/07/DataContract" xmlns:g="http://CIS/BIR/2014/07"')
GET_ACTION = "http://CIS/BIR/2014/07/IUslugaBIR/"  # GetValue lives in a different contract from the rest
NOT_FOUND = "4"  # KomunikatKod: no record for these search terms


class GusError(requests.RequestException):
    pass


class Client:
    def __init__(self, url, key):
        self.url, self.key = url, key
        self.session = requests.Session()
        self.logged_at = 0
        self.login()

    def call(self, operation, body, action=ACTION, prefix="ns"):
        envelope = (f'<soap:Envelope {NAMESPACES}><soap:Header xmlns:wsa="http://www.w3.org/2005/08/addressing">'
                    f"<wsa:To>{self.url}</wsa:To><wsa:Action>{action}{operation}</wsa:Action></soap:Header>"
                    f"<soap:Body><{prefix}:{operation}>{body}</{prefix}:{operation}></soap:Body></soap:Envelope>")
        response = self.session.post(self.url, data=envelope.encode("utf-8"), timeout=40,
                                     headers={"Content-Type": "application/soap+xml; charset=utf-8"})
        response.raise_for_status()
        # the reply is MTOM multipart; the result is the one element named after the operation
        response.encoding = "utf-8"
        found = re.search(rf"<{operation}Result>(.*?)</{operation}Result>", response.text, re.S)
        return html.unescape(found.group(1)) if found else ""

    def login(self):
        sid = self.call("Zaloguj", f"<ns:pKluczUzytkownika>{self.key}</ns:pKluczUzytkownika>")
        if not sid:
            sys.exit("GUS login failed: check the key.")
        self.session.headers["sid"] = sid
        self.logged_at = time.time()

    def fetch(self, operation, body):
        """Rows of a reply. Empty means GUS has no such record; an empty reply for any other reason must not be saved as one."""
        for _ in range(2):
            found = rows(self.call(operation, body))
            if found:
                return found
            code = self.call("GetValue", "<g:pNazwaParametru>KomunikatKod</g:pNazwaParametru>", GET_ACTION, "g")
            if code == NOT_FOUND:
                return []
            self.login()  # the session dropped or GUS refused: try once more on a new one
        raise GusError(f"{operation} gave no data, GUS code {code!r}")

    def lookup(self, nip):
        if time.time() - self.logged_at > SESSION_SECONDS:
            self.login()
        found = self.fetch("DaneSzukajPodmioty", f"<ns:pParametryWyszukiwania><dat:Nip>{nip}</dat:Nip></ns:pParametryWyszukiwania>")
        if not found:
            return {"found": False}
        # a closed entry can sit next to the live one
        subject = next((r for r in found if not r.get("DataZakonczeniaDzialalnosci")), found[0])
        regon, kind = subject.get("Regon", ""), subject.get("Typ", "")
        report = "BIR11OsPrawna" if kind == "P" else "BIR11OsFizycznaDzialalnoscCeidg"
        prefix = "praw_" if kind == "P" else "fiz_"
        data = self.report(regon, report)
        if not data:
            print(f"{nip}: no {report} report (type {kind}, silo {subject.get('SilosID', '')})", flush=True)
        # sole traders keep the local units count in a separate report
        units = data if kind == "P" else self.report(regon, "BIR11OsFizycznaDaneOgolne")
        return {"found": True, "regon": regon, "phone": data.get(f"{prefix}numerTelefonu", ""), "email": data.get(f"{prefix}adresEmail", ""),
                "website": data.get(f"{prefix}adresStronyinternetowej", ""), "local_units": units.get(f"{prefix}liczbaJednLokalnych", "")}

    def report(self, regon, name):
        data = self.fetch("DanePobierzPelnyRaport", f"<ns:pRegon>{regon}</ns:pRegon><ns:pNazwaRaportu>{name}</ns:pNazwaRaportu>")
        return data[0] if data else {}


def rows(text):
    if "<dane>" not in text:
        return []
    root = ElementTree.fromstring(f"<root>{text[text.index('<dane>'):text.rindex('</dane>') + 7]}</root>")
    return [{child.tag: (child.text or "").strip() for child in item} for item in root.findall("dane")
            if item.find("ErrorCode") is None]


def main():
    if sys.argv[1:2] == ["--test"]:
        client = Client(TEST_URL, TEST_KEY)
        for nip in sys.argv[2:]:
            print(nip, client.lookup(nip))
            time.sleep(DELAY)
        return
    key = os.environ.get("GUS_API_KEY")
    if not key:
        sys.exit("Set GUS_API_KEY, or use --test NIP.")
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    leads = pd.read_csv(PROCESSED / "leads.csv", dtype=str).fillna("")
    firms = leads[leads["tier"] != "X"]["nip"]
    write_header = not OUTPUT.exists()
    if OUTPUT.exists():
        firms = firms[~firms.isin(pd.read_csv(OUTPUT, dtype=str)["nip"])]
    if limit:
        firms = firms.head(limit)
    print(f"{len(firms)} firms to look up")
    client = Client(LIVE_URL, key)
    with open(OUTPUT, "a", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, FIELDS)
        if write_header:
            writer.writeheader()
        for i, nip in enumerate(firms, 1):
            try:
                record = client.lookup(nip)
            except requests.RequestException as error:
                print(f"Stopping on API error: {error}")
                return
            writer.writerow({"nip": nip, "checked_on": time.strftime("%Y-%m-%d"), **record})
            out.flush()
            if i % 100 == 0:
                print(f"{i}/{len(firms)}", flush=True)
            time.sleep(DELAY)


if __name__ == "__main__":
    main()
