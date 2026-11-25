"""Find which job board each company uses, and merge the hits into companies.json.

Reads company_names.txt (your list) and discovered_names.txt (added automatically from
funding news). Format per line:  Name, tier   (anything after # is a comment).

Names with no live job board are remembered in slug_misses.json and retried after
30 days, so repeat runs stay fast.

Run on GitHub (Actions tab -> find-slugs) or locally:  python find_slugs.py
Each hit prints a sample job title: if it looks like the wrong company, delete that
entry from companies.json.
"""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from job_alerts import FETCHERS

ROOT = Path(__file__).parent
NAME_FILES = [ROOT / "company_names.txt", ROOT / "discovered_names.txt"]
OUT_FILE = ROOT / "companies.json"
MISSES_FILE = ROOT / "slug_misses.json"
RETRY_MISS_DAYS = 30
SUFFIXES = {"technologies", "technology", "software", "labs", "inc", "corp", "pvt", "ltd", "limited"}


def variants(name):
    words = re.sub(r"[^a-z0-9 ]", "", name.lower()).split()
    core = [w for w in words if w not in SUFFIXES] or words
    out = []
    for ws in (words, core):
        for v in ("".join(ws), "-".join(ws)):
            if v and v not in out:
                out.append(v)
    return out


def discover(name):
    for slug in variants(name):
        for ats, fetch in FETCHERS.items():
            try:
                rows = fetch(slug)
            except Exception:
                rows = None
            time.sleep(0.05)
            if rows:
                return ats, slug, rows
    return None


def read_names():
    seen, names = set(), []
    for f in NAME_FILES:
        if not f.exists():
            continue
        for line in f.read_text().splitlines():
            line = line.split("#")[0].strip()
            if not line:
                continue
            name, _, tier = [p.strip() for p in line.partition(",")]
            if name and name.lower() not in seen:
                seen.add(name.lower())
                names.append((name, tier or "B"))
    return names


def main():
    existing = json.loads(OUT_FILE.read_text()) if OUT_FILE.exists() else []
    have = {c["name"].lower() for c in existing}
    misses = json.loads(MISSES_FILE.read_text()) if MISSES_FILE.exists() else {}
    today = date.today()

    todo, skipped = [], 0
    for name, tier in read_names():
        if name.lower() in have:
            continue
        missed_on = misses.get(name.lower())
        if missed_on and (today - date.fromisoformat(missed_on)).days < RETRY_MISS_DAYS:
            skipped += 1
            continue
        todo.append((name, tier))
    print(f"{len(todo)} names to check ({len(existing)} already tracked, {skipped} skipped as recent misses)\n")

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda nt: discover(nt[0]), todo))

    added, missed = [], []
    for (name, tier), found in zip(todo, results):
        if not found:
            print(f"x {name}: not found")
            missed.append(name)
            misses[name.lower()] = today.isoformat()
            continue
        ats, slug, rows = found
        print(f'+ {name}: {ats}/{slug} ({len(rows)} jobs, e.g. "{rows[0][1]}")')
        added.append({"name": name, "ats": ats, "slug": slug, "tier": tier})
        misses.pop(name.lower(), None)

    merged = sorted(existing + added, key=lambda c: (c.get("tier", "B"), c["name"].lower()))
    OUT_FILE.write_text(json.dumps(merged, indent=2) + "\n")
    MISSES_FILE.write_text(json.dumps(misses, indent=1, sort_keys=True) + "\n")
    print(f"\nAdded {len(added)}, missed {len(missed)}. companies.json now has {len(merged)} companies.")
    if missed:
        print("Not on a supported job board (check by hand if you care):", ", ".join(missed))


if __name__ == "__main__":
    main()
