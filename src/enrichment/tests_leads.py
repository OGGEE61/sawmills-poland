"""Run from the repo root: venv/bin/python src/enrichment/tests_leads.py"""
import unittest

import pandas as pd

from build_leads import blockers, pair_in_words, product_for, resolve_name, role_rank, size_band
from contacts import clean_email, clean_phone, clean_site, email_domain, mask_fits
from fetch_eu_projects import classify, core_of, normalize
from crawl_websites import name_in_domain
from web_search import extract, select_firms


class Contacts(unittest.TestCase):
    def test_phone(self):
        self.assertEqual(clean_phone("+48 501-234-567"), "501 234 567")
        self.assertEqual(clean_phone("0048501234567"), "501 234 567")
        self.assertEqual(clean_phone("(22) 123 45 67"), "221 234 567")
        for bad in ("123", "nan", "", "111111111", None):
            self.assertEqual(clean_phone(bad), "")

    def test_site_rejects_junk(self):
        self.assertEqual(clean_site("www.Foo.PL/x"), "foo.pl")
        for bad in ("Liliowa", "a@b.pl", "nan", "facebook.com/tartak"):
            self.assertEqual(clean_site(bad), "")

    def test_email(self):
        self.assertEqual(clean_email("JACEK@X.PL"), "jacek@x.pl")
        self.assertEqual(email_domain("biuro@tartak.pl"), "tartak.pl")
        self.assertEqual(email_domain("a@gmail.com"), "")


class People(unittest.TestCase):
    def test_mask(self):
        self.assertTrue(mask_fits("J*** K******", "JANA KOWALSK"))
        self.assertFalse(mask_fits("J*** K******", "ANNA KOWALSK"))
        self.assertFalse(mask_fits("J*** K******", "JAN KOWALSKI"))
        self.assertFalse(mask_fits("J*** E** K******", "JANA KOWALSK"))

    def test_names_only_from_this_firms_own_sources(self):
        mask = "M****** E**** N****"
        self.assertEqual(resolve_name(mask, [], "TARTAK ZĘBOWO MATEUSZ NOWAK SPÓŁKA KOMANDYTOWA", [], {})[0], "Mateusz Nowak")
        self.assertEqual(resolve_name("J**** J******", [], "ABC", ["jacek.janicki@abc.pl"], {})[0], "Jacek Janicki")
        self.assertEqual(resolve_name("J**** J******", [], "ABC", ["biuro@abc.pl"], {}), ("", ""))
        self.assertIsNone(pair_in_words("J*** K******", ["ANNA", "KOWALSK"]))
        self.assertIsNone(pair_in_words("S***** P********", ["SPÓŁKA", "PIEKARSKI"]))

    def test_president_outranks_proxy(self):
        self.assertLess(role_rank("PREZES ZARZĄDU"), role_rank("PROKURENT"))
        self.assertLess(role_rank("PREZES ZARZĄDU"), role_rank("WICEPREZES ZARZĄDU") + 1)


class Matching(unittest.TestCase):
    def test_legal_forms_collapse(self):
        self.assertEqual(normalize('"ABC" Sp. z o.o.'), normalize("ABC SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ"))
        self.assertNotEqual(normalize("ABC SP. Z O.O."), normalize("ABC S.A."))
        self.assertEqual(core_of(normalize("ABC S.A.")), "ABC")
        self.assertEqual(normalize("ŁADA W LIKWIDACJI SP. Z O.O."), normalize("LADA SP Z O O"))

    def test_project_kind(self):
        self.assertEqual(classify("Zakup nowoczesnych urządzeń w tartaku", ""), "MACHINERY")
        self.assertEqual(classify("Zakup i montaż instalacji fotowoltaicznej", "zakup maszyn"), "ENERGY")
        self.assertEqual(classify("Dotacja na kapitał obrotowy", ""), "LIQUIDITY")
        self.assertEqual(classify("Biznes Plan dla tartaku", "maszyny"), "OTHER")
        self.assertEqual(classify("Model biznesowy GOZ w tartaku", ""), "WASTE")
        self.assertEqual(classify("Nowa linia produkcyjna", "zagospodarowanie trocin"), "WASTE")
        self.assertEqual(classify("Instalacja fotowoltaiczna", "brak odpadów"), "ENERGY")
        self.assertEqual(classify("Nowy produkt", "mniej odpadów"), "OTHER")


class Product(unittest.TestCase):
    def test_machine_follows_waste(self):
        offer = lambda main, tags="", fit=60: product_for(dict(main_pkd=main, tags=tags, fit=fit))
        self.assertEqual(offer("16.10.Z"), "Rębak + brykieciarka")
        self.assertEqual(offer("16.22.Z"), "Brykieciarka")
        self.assertEqual(offer("02.20.Z"), "Rębak")
        self.assertEqual(offer("16.22.Z", "suszarnia"), "Rębak + brykieciarka")
        self.assertEqual(offer("41.20.Z", "", 10), "")


class SearchResults(unittest.TestCase):
    def test_contacts_only_from_results_about_this_firm(self):
        other = {"url": "https://www.gowork.pl/x", "text": "Tartak Rawicz tel. 501 234 567 biuro@rawicz.pl"}
        mine = {"url": "https://www.krs-online.com.pl/y", "text": "Powidzka Sp. NIP 7551004144 tel. 602 111 222"}
        found = extract([other, mine], "POWIDZKA SPÓŁKA JAWNA", "7551004144")
        self.assertEqual(found["phones"], ["602111222"])
        self.assertEqual(found["emails"], [])

    def test_directory_is_not_the_firms_site(self):
        self.assertFalse(name_in_domain("TARTAK BYDGOSZCZ SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ", "aplikuj.pl"))
        self.assertTrue(name_in_domain("GAMBEX GOŁĄBEK SPÓŁKA KOMANDYTOWA", "gambex.pl"))

    def test_regon_is_not_a_phone(self):
        found = extract([{"url": "https://a.pl", "text": "NIP 7551004144. REGON: 530831216."}], "X", "7551004144")
        self.assertEqual(found["phones"], [])


class SearchSelection(unittest.TestCase):
    def test_no_contact_first_within_tier(self):
        leads = pd.DataFrame([
            dict(nip="1", tier="A", size_band="pasuje", phone="", email="a@a.pl", website=""),
            dict(nip="2", tier="B", size_band="pasuje", phone="600", email="", website=""),
            dict(nip="3", tier="B", size_band="pasuje", phone="", email="", website=""),
            dict(nip="4", tier="B", size_band="pasuje", phone="", email="", website=""),
            dict(nip="5", tier="B", size_band="duża", phone="", email="", website=""),
            dict(nip="6", tier="X", size_band="pasuje", phone="", email="", website=""),
            dict(nip="7", tier="B", size_band="pasuje", phone="600", email="", website="https://a.pl"),
        ])
        self.assertEqual(list(select_firms(leads, {"4"})["nip"]), ["1", "3", "2"])


class Size(unittest.TestCase):
    def test_small_clients_are_the_target(self):
        base = dict(legal_form="JDG", has_group_accounts=False, has_supervisory_board=False, share_capital=0, eu_value=0, verification="CZYNNY")
        self.assertEqual(size_band(base), "pasuje")
        self.assertEqual(size_band({**base, "legal_form": "SPÓŁKA AKCYJNA"}), "duża")
        self.assertEqual(size_band({**base, "share_capital": 8_000_000}), "duża")
        self.assertEqual(size_band({**base, "verification": "ZWOLNIONY"}), "mała")


class Blockers(unittest.TestCase):
    def test_closed_firm_blocked(self):
        row = dict(status="AKTYWNY", liquidation=False, bankruptcy=True, dissolved=False, suspended=False, verification="CZYNNY")
        self.assertEqual(blockers(row), ["Upadłość"])


if __name__ == "__main__":
    unittest.main()
