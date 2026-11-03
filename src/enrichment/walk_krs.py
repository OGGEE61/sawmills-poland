"""Find companies registered after sprawdz-firme.pl's coverage ends by reading KRS numbers one by one -> expansion_walk_firms.csv

The official KRS API cannot search by PKD, but numbers are sequential, so a range can be read directly.
Keeps active firms by the same rules as the two discovery routes: main activity in TARGET_MAIN, or any sawmill code.
A random sample measures hit rate and speed before committing to a full range.

From one IP, no proxies. Workers share one rate limit. On HTTP 429 everything pauses and the rate halves; the third 429 stops the run.
Resumable: stop and re-run any time. --new continues past the highest real firm read so far, for the monthly refresh;
empty numbers above it are read again, because they fill up as new companies register.

Usage: walk_krs.py START END [--sample N] [--workers N] [--rate REQUESTS_PER_SECOND]
       walk_krs.py --new [--workers N] [--rate REQUESTS_PER_SECOND]
"""
import argparse
import csv
import json
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests

from expand_market import FIELDS, KRS_URL, PROCESSED, ROOT, TARGET_MAIN, firm_row, main_pkd

RAW = ROOT / "data" / "raw" / "krs_walk"
CHECKED = PROCESSED / "expansion_walk_checked.csv"
OUTPUT = PROCESSED / "expansion_walk_firms.csv"
SAWMILL_CODES = {"16.10.Z", "16.11.Z", "16.12.Z"}
SAMPLE_SEED = 20261103
MAX_FAILURES = 10
MAX_BLOCKS = 3
BLOCK_PAUSE = 60
NEW_SPAN = 20000  # about three months of new numbers


class Blocked(Exception):
    pass


class Limiter:
    """One rate limit across all workers."""

    def __init__(self, rate):
        self.interval = 1 / rate
        self.next_slot = time.monotonic()
        self.paused_until = 0
        self.blocks = 0
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            if self.blocks >= MAX_BLOCKS:
                raise Blocked()
            now = time.monotonic()
            slot = max(now, self.next_slot)
            self.next_slot = slot + self.interval
        time.sleep(max(slot - now, 0))

    def blocked(self):
        with self.lock:
            now = time.monotonic()
            # requests in flight when a block starts answer 429 too: count them as one
            if now < self.paused_until:
                return
            self.blocks += 1
            self.interval *= 2
            self.paused_until = self.next_slot = now + BLOCK_PAUSE
            print(f"HTTP 429 ({self.blocks}/{MAX_BLOCKS}): pausing {BLOCK_PAUSE}s, now {1 / self.interval:.1f}/s", flush=True)


def other_pkd(odpis):
    activity = (odpis["dane"].get("dzial3") or {}).get("przedmiotDzialalnosci") or {}
    items = activity.get("przedmiotPozostalejDzialalnosci") or []
    return [f"{p.get('kodDzial', '')}.{p.get('kodKlasa', '')}.{p.get('kodPodklasa', '')}" for p in items]


def classify(odpis):
    mains = main_pkd(odpis)
    target = any(code.startswith(TARGET_MAIN) for code in mains)
    sawmill = SAWMILL_CODES & set(mains + other_pkd(odpis))
    if not target and not sawmill:
        return "other"
    d6 = odpis["dane"].get("dzial6") or {}
    if d6.get("likwidacja") or d6.get("rozwiazanieUniewaznienie"):
        return "closing"
    return "kept_main" if target else "kept_sawmill_other"


def numbers(start, end, sample):
    all_numbers = range(start, end + 1)
    if sample:
        return random.Random(SAMPLE_SEED).sample(all_numbers, sample)
    return all_numbers


def read_number(krs, limiter, local):
    if not hasattr(local, "session"):
        local.session = requests.Session()
    while True:
        limiter.wait()
        try:
            response = local.session.get(KRS_URL.format(krs), timeout=30)
            if response.status_code == 429:
                limiter.blocked()
                continue
            if response.status_code >= 500:
                return krs, "error", "", None
            if response.status_code != 200:
                return krs, "none", "", None
            odpis = response.json()["odpis"]
            registered = (odpis.get("naglowekA") or {}).get("dataRejestracjiWKRS", "")
            return krs, classify(odpis), registered, odpis
        except (requests.RequestException, ValueError, KeyError):
            return krs, "error", "", None


def last_real_number():
    checked = pd.read_csv(CHECKED, dtype=str)
    return checked[~checked["result"].isin(["none", "error"])]["krs"].astype(int).max()


def walk(start, end, sample, workers, rate, reread=False):
    done = set(pd.read_csv(CHECKED, dtype=str).query("result != 'error'")["krs"]) if CHECKED.exists() and not reread else set()
    todo = [krs for krs in (str(n).zfill(10) for n in numbers(start, end, sample)) if krs not in done]
    print(f"{len(todo)} numbers to read, {len(done)} already read, {workers} workers, at most {rate}/s", flush=True)
    RAW.mkdir(parents=True, exist_ok=True)
    new_checked, new_output = not CHECKED.exists(), not OUTPUT.exists()
    limiter, local = Limiter(rate), threading.local()
    counts, failures, started, i = {}, 0, time.time(), 0
    executor = ThreadPoolExecutor(workers)
    futures = [executor.submit(read_number, krs, limiter, local) for krs in todo]
    with open(CHECKED, "a", newline="", encoding="utf-8") as check_file, open(OUTPUT, "a", newline="", encoding="utf-8") as out_file:
        check_writer, out_writer = csv.writer(check_file), csv.DictWriter(out_file, FIELDS)
        if new_checked:
            check_writer.writerow(["krs", "result", "registration_date"])
        if new_output:
            out_writer.writeheader()
        try:
            for future in as_completed(futures):
                krs, result, registered, odpis = future.result()
                i += 1
                if result.startswith("kept"):
                    (RAW / f"{krs}.json").write_text(json.dumps({"odpis": odpis}, ensure_ascii=False), encoding="utf-8")
                    mains = main_pkd(odpis)
                    out_writer.writerow(firm_row(krs, "", odpis, mains[0] if mains else ""))
                    out_file.flush()
                failures = failures + 1 if result == "error" else 0
                counts[result] = counts.get(result, 0) + 1
                check_writer.writerow([krs, result, registered])
                check_file.flush()
                if failures >= MAX_FAILURES:
                    print(f"Stopping after {MAX_FAILURES} failures in a row; re-run later")
                    break
                if i % 200 == 0:
                    print(f"{i}/{len(todo)} read, {i / (time.time() - started):.1f}/s, {counts}", flush=True)
        except Blocked:
            print(f"Stopping after {MAX_BLOCKS} HTTP 429 answers; re-run later")
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
    print(f"finished: {counts}, {time.time() - started:.0f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("start", type=int, nargs="?")
    parser.add_argument("end", type=int, nargs="?")
    parser.add_argument("--new", action="store_true")
    parser.add_argument("--sample", type=int, default=0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--rate", type=float, default=15)
    args = parser.parse_args()
    if args.new:
        top = last_real_number()
        walk(top + 1, top + NEW_SPAN, 0, args.workers, args.rate, reread=True)
    elif args.start is None or args.end is None:
        parser.error("give START and END, or --new")
    else:
        walk(args.start, args.end, args.sample, args.workers, args.rate)
