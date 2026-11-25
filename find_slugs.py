"""Find which job board each company uses, and write/merge companies.json.

1. Put one company per line in company_names.txt:   Name, tier   (tier A or B)
2. Run:  python find_slugs.py
3. Read the output. Each hit prints a sample job title: if it looks like the wrong
   company, delete that entry from companies.json. Misses need a manual look at the
   company's careers page (it probably uses Workday or its own site).

Run it on your own computer; it makes a few hundred small requests.
"""
import json
import re
import time
from pathlib import Path

from job_alerts import FETCHERS

ROOT = Path(__file__).parent
NAMES_FILE = ROOT / "company_names.txt"
OUT_FILE = ROOT / "companies.json"
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
                continue
            finally:
                time.sleep(0.15)
            if rows:
                return ats, slug, rows
    return None


def main():
    existing = json.loads(OUT_FILE.read_text()) if OUT_FILE.exists() else []
    have = {c["name"].lower() for c in existing}
    added, missed = [], []

    for line in NAMES_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, tier = [p.strip() for p in line.partition(",")]
        tier = tier or "B"
        if name.lower() in have:
            print(f"= {name}: already in companies.json")
            continue
        found = discover(name)
        if not found:
            print(f"x {name}: not found")
            missed.append(name)
            continue
        ats, slug, rows = found
        print(f"+ {name}: {ats}/{slug} ({len(rows)} jobs, e.g. \"{rows[0][1]}\")")
        added.append({"name": name, "ats": ats, "slug": slug, "tier": tier})

    merged = sorted(existing + added, key=lambda c: (c.get("tier", "B"), c["name"].lower()))
    OUT_FILE.write_text(json.dumps(merged, indent=2) + "\n")
    print(f"\nAdded {len(added)}, missed {len(missed)}. companies.json now has {len(merged)} companies.")
    if missed:
        print("Missed (check their careers page by hand):", ", ".join(missed))


if __name__ == "__main__":
    main()
