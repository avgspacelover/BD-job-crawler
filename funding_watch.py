"""Funding watcher v3: scans startup-news RSS feeds for SaaS funding rounds, emails new
ones with one-click job links, and adds each funded company to discovered_names.txt so
the weekly find-slugs run starts watching its job board automatically.

Reuses send_email() from job_alerts.py, so it needs the same three secrets.
Local test:  python funding_watch.py   (prints instead of emailing; changes no files)
"""
import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus

import requests

from job_alerts import send_email

ROOT = Path(__file__).parent
SEEN_FILE = ROOT / "seen_news.json"
NAMES_FILE = ROOT / "company_names.txt"
DISCOVERED_FILE = ROOT / "discovered_names.txt"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; funding-watch/3.0)"}

# Standard WordPress-style feed URLs. Open each in a browser to check; add more freely.
FEEDS = {
    "Inc42": "https://inc42.com/feed/",
    "Entrackr": "https://entrackr.com/feed",
    "YourStory": "https://yourstory.com/feed",
}

# ---- EDIT THESE FILTERS ----------------------------------------------------
FUNDING = re.compile(
    r"\b(raises?|raised|bags?|secures?|lands?|series [a-e]|seed|pre-series|funding)\b", re.I)
SAAS = re.compile(
    r"\b(saas|b2b|enterprise|software|crm|martech|sales|devtools|cloud|api|ai)\b", re.I)
# ----------------------------------------------------------------------------

NAME_RE = re.compile(r"^(.+?)\s+(?:raises?|bags?|secures?|lands?|gets|closes|picks up|mops up|nets)\b", re.I)
PREFIX_RE = re.compile(r"\b(?:startup|platform|firm|company|unicorn|major|player|provider)\s+", re.I)
BASED_RE = re.compile(r"^\S+-based\s+", re.I)
STAGE_RE = re.compile(r"\b(pre-?seed|seed|pre-?series [a-f]|series [a-f])\b", re.I)


def clean(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def company_from_title(title):
    m = NAME_RE.match(title)
    if not m:
        return None
    name = PREFIX_RE.split(m.group(1))[-1].strip()
    name = BASED_RE.sub("", name).strip()
    return name or None


def plausible_name(name):
    return (bool(name) and 2 < len(name) <= 40 and len(name.split()) <= 4
            and name[0].isupper() and not re.search(r"[\d$%]", name))


def known_names():
    known = set()
    for f in (NAMES_FILE, DISCOVERED_FILE):
        if f.exists():
            for line in f.read_text().splitlines():
                line = line.split("#")[0].strip()
                if line:
                    known.add(line.split(",")[0].strip().lower())
    return known


def record_discoveries(new):
    known = known_names()
    lines = []
    for _, title, _, _, company in new:
        if not plausible_name(company) or company.lower() in known:
            continue
        known.add(company.lower())
        stage = STAGE_RE.search(title)
        lines.append(f"{company}, C  # {stage.group(1).lower() if stage else 'funded'}, {date.today().isoformat()}")
    if lines:
        with DISCOVERED_FILE.open("a") as f:
            f.write("\n".join(lines) + "\n")
    return len(lines)


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    return [
        (clean(i.findtext("title")), (i.findtext("link") or "").strip(), clean(i.findtext("description")))
        for i in root.iter("item")
    ]


def render(new, broken):
    text, cards = [], []
    e = lambda s: html.escape(s or "", quote=True)
    for source, title, summary, link, company in new:
        q = company or title
        careers = "https://www.google.com/search?q=" + quote_plus(f"{q} careers sales jobs")
        jobs = "https://www.linkedin.com/jobs/search/?keywords=" + quote_plus(f"{q} sales")
        text.append(f"[{source}] {title}\n    {summary}\n    Story: {link}\n    "
                    f"Careers: {careers}\n    LinkedIn jobs: {jobs}")
        cards.append(
            '<div style="margin:0 0 14px;padding:12px;border:1px solid #ddd;border-radius:8px">'
            f'<div style="font-size:15px;font-weight:600"><a href="{e(link)}">{e(title)}</a></div>'
            f'<div style="color:#555;font-size:13px;margin:4px 0 8px">{e(source)} · {e(summary)}</div>'
            f'<div style="font-size:13px"><a href="{e(careers)}">Find careers page</a> · '
            f'<a href="{e(jobs)}">LinkedIn jobs</a></div></div>')
    tip = ("Funded companies hire sales fast. Check their jobs the same day you read this. "
           "These companies are also added to the bot's watch list automatically.")
    body_text = "\n\n".join(text) + "\n\n" + tip
    body_html = ('<div style="font-family:Arial,sans-serif;max-width:640px">' + "".join(cards)
                 + f'<p style="color:#555;font-size:13px">{e(tip)}</p>')
    if broken:
        note = "Feeds that failed: " + ", ".join(broken)
        body_text += "\n" + note
        body_html += f'<p style="color:#a33;font-size:12px">{e(note)}</p>'
    return body_text, body_html + "</div>"


def main():
    seen_list = json.loads(SEEN_FILE.read_text()) if SEEN_FILE.exists() else []
    seen = set(seen_list)
    new, broken = [], []

    for source, url in FEEDS.items():
        try:
            items = fetch(url)
        except Exception:
            broken.append(source)
            continue
        for title, link, summary in items:
            if not link or link in seen:
                continue
            if not FUNDING.search(title) or not SAAS.search(f"{title} {summary}"):
                continue
            seen.add(link)  # same story in two feeds is listed once
            new.append((source, title, summary[:200], link, company_from_title(title)))

    DISCOVERED_FILE.touch()  # make sure it exists so the workflow can always commit it
    if new:
        text, html_body = render(new, broken)
        if send_email(f"{len(new)} new SaaS funding stories", text, html_body):
            seen_list.extend(n[3] for n in new)
            added = record_discoveries(new)
            print(f"Added {added} new companies to discovered_names.txt")
    else:
        print("No new funding stories.")
    if broken:
        print("Broken feeds:", broken)

    SEEN_FILE.write_text(json.dumps(seen_list[-2000:]))


if __name__ == "__main__":
    main()
