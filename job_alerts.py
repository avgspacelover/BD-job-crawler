"""Daily job alerts: polls company career feeds, filters, dedupes, emails new roles.

Run locally to test:  python job_alerts.py   (prints instead of emailing)
"""
import json
import os
import re
import smtplib
from email.message import EmailMessage
from pathlib import Path

import requests

ROOT = Path(__file__).parent
SEEN_FILE = ROOT / "seen.json"
COMPANIES = json.loads((ROOT / "companies.json").read_text())

# ---- EDIT THESE FILTERS ----------------------------------------------------
TITLE_INCLUDE = re.compile(
    r"\b(sdr|bdr|sales development|business development|inside sales|"
    r"account executive|account manager|customer success|sales)\b", re.I)
TITLE_EXCLUDE = re.compile(
    r"\b(senior|sr\.?|head|director|vp|vice president|principal|staff|lead)\b", re.I)
LOCATION_OK = re.compile(
    r"(delhi|noida|gurgaon|gurugram|ncr|mumbai|bangalore|bengaluru|pune|"
    r"hyderabad|remote|india)", re.I)
# ----------------------------------------------------------------------------


def fetch_greenhouse(slug):
    r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", timeout=20)
    r.raise_for_status()
    return [(j["id"], j["title"], (j.get("location") or {}).get("name", ""), j["absolute_url"])
            for j in r.json()["jobs"]]


def fetch_lever(slug):
    r = requests.get(f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"}, timeout=20)
    r.raise_for_status()
    return [(j["id"], j["text"], (j.get("categories") or {}).get("location") or "", j["hostedUrl"])
            for j in r.json()]


def fetch_ashby(slug):
    r = requests.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", timeout=20)
    r.raise_for_status()
    return [(j["id"], j["title"], j.get("location") or "", j["jobUrl"]) for j in r.json()["jobs"]]


FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever, "ashby": fetch_ashby}


def send_email(subject, body):
    user = os.getenv("GMAIL_USER")
    password = os.getenv("GMAIL_APP_PASSWORD")
    to = os.getenv("TO_EMAIL")
    if not (user and password and to):
        print(subject, "\n", body)  # local test mode
        return
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, password)
        s.send_message(msg)


def main():
    seen = set(json.loads(SEEN_FILE.read_text())) if SEEN_FILE.exists() else set()
    new, broken = [], []

    for c in COMPANIES:
        try:
            jobs = FETCHERS[c["ats"]](c["slug"])
        except Exception:
            broken.append(f'{c["name"]} ({c["ats"]}/{c["slug"]})')
            continue
        for jid, title, loc, url in jobs:
            key = f'{c["ats"]}:{c["slug"]}:{jid}'
            if key in seen:
                continue
            if not TITLE_INCLUDE.search(title) or TITLE_EXCLUDE.search(title):
                continue
            if loc and not LOCATION_OK.search(loc):
                continue
            seen.add(key)
            new.append((c.get("tier", "B"), c["name"], title, loc, url))

    if new:
        new.sort()
        lines = [f"[{t}] {name} | {title} | {loc or 'n/a'}\n    {url}" for t, name, title, loc, url in new]
        body = "\n\n".join(lines)
        if broken:
            body += "\n\nCould not fetch (check slug/ATS): " + ", ".join(broken)
        send_email(f"{len(new)} new sales roles", body)
    else:
        print("No new roles.")
    if broken:
        print("Broken feeds:", broken)

    SEEN_FILE.write_text(json.dumps(sorted(seen), indent=0))


if __name__ == "__main__":
    main()
