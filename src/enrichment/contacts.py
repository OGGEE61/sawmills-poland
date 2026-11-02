"""Clean registry contact fields (they hold typos, emails in the website field, street names...)."""
import re
import unicodedata
from pathlib import Path

import pandas as pd

PROCESSED = Path(__file__).resolve().parents[2] / "data" / "processed"

EMAIL_RE = re.compile(r"[a-z0-9._%+-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}", re.I)
SITE_RE = re.compile(r"^(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})(/\S*)?$", re.I)
FREE_MAIL = {"gmail.com", "wp.pl", "o2.pl", "02.pl", "onet.pl", "onet.eu", "op.pl", "interia.pl", "interia.eu", "poczta.fm",
             "vp.pl", "tlen.pl", "go2.pl", "buziaczek.pl", "autograf.pl", "gazeta.pl", "yahoo.com", "yahoo.pl",
             "hotmail.com", "outlook.com", "icloud.com", "post.com", "mail.com", "email.com", "protonmail.com", "live.com", "wp.eu", "poczta.onet.pl", "neostrada.pl", "spoko.pl"}
# social and directory pages say nothing about the firm's own domain
NOT_OWN_SITE = ("facebook.com", "instagram.com", "linkedin.com", "olx.pl", "allegro.pl", "aleo.com", "panoramafirm.pl",
                "pkt.pl", "krs-online.com.pl", "rejestr.io", "biznes.gov.pl", "ceidg.gov.pl", "gowork.pl", "owg.pl",
                "firmy.net", "infoveriti.pl", "krs-pobierz.pl", "wikipedia.org", "youtube.com", "google.com", "oferteo.pl")


def missing(value):
    return value is None or pd.isna(value) or str(value).strip().lower() in ("", "nan", "none", "-")


def clean_email(value):
    if missing(value):
        return ""
    found = EMAIL_RE.search(str(value))
    return found.group(0).lower() if found else ""


def clean_phone(value):
    """Polish numbers as 'NNN NNN NNN'; anything that is not 9 digits is dropped."""
    if missing(value):
        return ""
    digits = re.sub(r"\D", "", str(value).split(",")[0].split(";")[0])
    if digits.startswith("0048"):
        digits = digits[4:]
    elif digits.startswith("48") and len(digits) == 11:
        digits = digits[2:]
    digits = digits.lstrip("0") if len(digits) == 10 else digits
    if len(digits) != 9 or digits[0] == "0" or len(set(digits)) == 1:
        return ""
    return f"{digits[:3]} {digits[3:6]} {digits[6:]}"


def clean_site(value):
    if missing(value) or "@" in str(value):
        return ""
    found = SITE_RE.match(str(value).strip().rstrip("/").lower())
    if not found:
        return ""
    host = found.group(1).removeprefix("www.")
    return "" if host.endswith(NOT_OWN_SITE) else host


def email_domain(email):
    domain = email.split("@")[-1].lower() if email else ""
    return "" if domain in FREE_MAIL or domain.endswith(NOT_OWN_SITE) else domain


def plain(text):
    text = str(text).replace("Ł", "L").replace("ł", "l")
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)).upper()


def word_fits(mask_word, word):
    return bool(mask_word) and len(mask_word) == len(word) and plain(mask_word[0]) == plain(word[0])


def mask_fits(mask, full):
    """Does a KRS mask (J*** K******) fit a full name? Same words, first letters and lengths."""
    mask_parts, full_parts = mask.split(), full.split()
    return len(mask_parts) == len(full_parts) and all(word_fits(m, f) for m, f in zip(mask_parts, full_parts))


def pair_fits(mask, first, last):
    """Fit first name + surname only: firms publish names without the second given name."""
    parts = mask.split()
    return len(parts) >= 2 and word_fits(parts[0], first) and word_fits(parts[-1], last)


def read_ceidg():
    """Sawmill sole traders, plus other wood trades once fetch_data.py --wood has been run."""
    frames = [pd.read_csv(PROCESSED / name, sep=";", encoding="utf-8-sig", dtype=str)
              for name in ("tartaki_ceidg.csv", "tartaki_ceidg_wood.csv") if (PROCESSED / name).exists()]
    return pd.concat(frames, ignore_index=True)


def registry_contacts():
    """One row per firm with what the registers themselves say: nip, phone, email, site, site_source."""
    master = pd.read_csv(PROCESSED / "master.csv", dtype=str).dropna(subset=["nip"]).drop_duplicates("nip")
    master["key"] = master["source_id"].where(master["source"] == "CEIDG", master["source_id"].str.zfill(10))

    ceidg = read_ceidg()
    ceidg = pd.DataFrame({"key": ceidg["CEIDG_ID"], "raw_phone": ceidg["detail.telefon"], "raw_email": ceidg["detail.email"],
                          "raw_site": ceidg["detail.www"]})
    krs = pd.read_csv(PROCESSED / "krs_signals.csv", dtype=str)
    krs = pd.DataFrame({"key": krs["krs"], "raw_phone": None, "raw_email": krs["email"], "raw_site": krs["website"]})
    merged = master.merge(pd.concat([ceidg, krs]).drop_duplicates("key"), on="key", how="left")

    # the website field regularly holds the email and vice versa
    merged["phone"] = merged["raw_phone"].map(clean_phone)
    merged["email"] = [clean_email(e) or clean_email(s) for e, s in zip(merged["raw_email"], merged["raw_site"])]
    merged["site"] = merged["raw_site"].map(clean_site)
    merged["site_source"] = merged["site"].map(lambda s: "rejestr" if s else "")
    from_mail = (merged["site"] == "") & merged["email"].map(email_domain).ne("")
    merged.loc[from_mail, "site"] = merged.loc[from_mail, "email"].map(email_domain)
    merged.loc[from_mail, "site_source"] = "domena e-mail"
    return merged[["nip", "name", "city", "source", "key", "phone", "email", "site", "site_source"]]
