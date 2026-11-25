"""Job alerts v2: polls company job boards (+ optional Adzuna), filters, ranks,
dedupes, and emails new roles as a clickable HTML email.

Local test:  python job_alerts.py   (prints instead of emailing; saves nothing as "seen")
"""
import html
import json
import os
import re
import smtplib
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import quote_plus

import requests

ROOT = Path(__file__).parent
SEEN_FILE = ROOT / "seen.json"
COMPANIES_FILE = ROOT / "companies.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; job-alerts/2.0)"}

# ---- EDIT THESE ------------------------------------------------------------
MAX_AGE_DAYS = 30        # skip postings older than this (when the board gives a date)
MAX_JOBS_PER_EMAIL = 60  # best-ranked first; the rest arrive in the next emails

# Titles you WANT. Wide net on purpose; the exclude list trims the noise.
TITLE_INCLUDE = re.compile(
    r"\b(sdr|bdr|sales development|business development|inside sales|outbound|"
    r"account executive|account manager|account development|key account|"
    r"sales|customer success|client success|relationship manager|"
    r"pre-?sales|solutions? consultant|growth associate|lead generation)\b", re.I)
TITLE_EXCLUDE = re.compile(
    r"\b(senior|sr\.?|head|director|vp|vice president|principal|staff|chief|avp|"
    r"general manager|team lead|lead(?!\s*gen)|"
    r"engineer|developer|designer|analyst|recruiter|talent|"
    r"operations|ops|marketing)\b", re.I)

# Ranking boosts (higher score = higher in the email)
CORE_ROLE = re.compile(r"\b(sdr|bdr|sales development|business development|inside sales)\b", re.I)
ENTRY_LEVEL = re.compile(
    r"\b(associate|executive|trainee|fresher|junior|jr\.?|entry|graduate|intern)\b", re.I)
PREFERRED_CITIES = re.compile(r"(delhi|noida|gurgaon|gurugram|ncr)", re.I)  # +1 boost

# Locations
INDIA = re.compile(
    r"(delhi|noida|gurgaon|gurugram|ncr|mumbai|bangalore|bengaluru|pune|"
    r"hyderabad|chennai|kolkata|ahmedabad|india)", re.I)

# Optional Adzuna aggregator (needs ADZUNA_APP_ID / ADZUNA_APP_KEY secrets)
ADZUNA_QUERIES = [
    "saas sales development", "saas business development executive",
    "saas account executive", "saas customer success executive",
]
ADZUNA_CITIES = ["Delhi", "Gurgaon", "Noida", "Mumbai", "Bangalore", "Pune", "Hyderabad"]
SAAS_HINT = re.compile(r"\b(saas|software|b2b|platform|cloud|crm|enterprise)\b", re.I)
# ----------------------------------------------------------------------------


def parse_dt(v):
    if not v:
        return None
    try:
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(v / 1000, tz=timezone.utc)
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _get(url, **kw):
    r = requests.get(url, headers=HEADERS, timeout=20, **kw)
    r.raise_for_status()
    return r.json()


# Each fetcher returns [(id, title, location, url, posted_datetime_or_None), ...]
def fetch_greenhouse(slug):
    data = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    return [(j["id"], j["title"], (j.get("location") or {}).get("name", ""), j["absolute_url"],
             parse_dt(j.get("first_published") or j.get("updated_at"))) for j in data["jobs"]]


def fetch_lever(slug):
    data = _get(f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"})
    return [(j["id"], j["text"], (j.get("categories") or {}).get("location") or "",
             j["hostedUrl"], parse_dt(j.get("createdAt"))) for j in data]


def fetch_ashby(slug):
    data = _get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    return [(j["id"], j["title"], j.get("location") or "", j["jobUrl"],
             parse_dt(j.get("publishedAt"))) for j in data["jobs"]]


def fetch_workable(slug):
    data = _get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}")
    return [(j.get("shortcode") or j.get("id"), j["title"],
             ", ".join(x for x in (j.get("city"), j.get("state"), j.get("country")) if x),
             j.get("url") or j.get("application_url"),
             parse_dt(j.get("published_on") or j.get("created_at"))) for j in data.get("jobs", [])]


def fetch_smartrecruiters(slug):
    out, offset = [], 0
    while offset < 500:
        data = _get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings",
                    params={"limit": 100, "offset": offset})
        items = data.get("content", [])
        for j in items:
            loc = j.get("location") or {}
            place = ", ".join(x for x in (loc.get("city"), (loc.get("country") or "").upper()) if x)
            out.append((j["id"], j["name"], place,
                        f"https://jobs.smartrecruiters.com/{slug}/{j['id']}",
                        parse_dt(j.get("releasedDate"))))
        offset += 100
        if not items or offset >= data.get("totalFound", 0):
            break
    return out


def fetch_recruitee(slug):
    data = _get(f"https://{slug}.recruitee.com/api/offers/")
    return [(j["id"], j["title"], j.get("location") or "",
             j.get("careers_url") or f"https://{slug}.recruitee.com/o/{j.get('slug', '')}",
             parse_dt(j.get("published_at") or j.get("created_at"))) for j in data.get("offers", [])]


FETCHERS = {
    "greenhouse": fetch_greenhouse, "lever": fetch_lever, "ashby": fetch_ashby,
    "workable": fetch_workable, "smartrecruiters": fetch_smartrecruiters,
    "recruitee": fetch_recruitee,
}


def collect_company_jobs(broken):
    companies = json.loads(COMPANIES_FILE.read_text()) if COMPANIES_FILE.exists() else []
    jobs = []
    for c in companies:
        try:
            rows = FETCHERS[c["ats"]](c["slug"])
        except Exception:
            broken.append(f'{c["name"]} ({c["ats"]}/{c["slug"]})')
            continue
        for jid, title, loc, url, posted in rows:
            jobs.append({"key": f'{c["ats"]}:{c["slug"]}:{jid}', "company": c["name"],
                         "title": title, "loc": loc or "", "url": url,
                         "posted": posted, "tier": c.get("tier", "B")})
    return jobs


def fetch_adzuna(broken):
    """Searches every query in every target city, so it also finds companies that are not
    on your list. Needs ADZUNA_APP_ID and ADZUNA_APP_KEY secrets; skipped without them."""
    app_id, app_key = os.getenv("ADZUNA_APP_ID"), os.getenv("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        print("Adzuna not configured (optional): skipping the wide city search.")
        return []
    jobs, seen_keys = [], set()
    for q in ADZUNA_QUERIES:
        for city in ADZUNA_CITIES:
            try:
                data = _get("https://api.adzuna.com/v1/api/jobs/in/search/1", params={
                    "app_id": app_id, "app_key": app_key, "what": q, "where": city,
                    "results_per_page": 50, "max_days_old": MAX_AGE_DAYS, "sort_by": "date",
                    "content-type": "application/json"})
            except Exception:
                broken.append("Adzuna")
                return jobs
            time.sleep(2.5)  # stay under Adzuna's per-minute limit
            for j in data.get("results", []):
                key = f'adzuna:{j["id"]}'
                if key in seen_keys:
                    continue
                if not SAAS_HINT.search(f'{j.get("title", "")} {j.get("description", "")}'):
                    continue
                seen_keys.add(key)
                jobs.append({"key": key,
                             "company": (j.get("company") or {}).get("display_name") or "Unknown",
                             "title": re.sub(r"</?strong>", "", j.get("title", "")),
                             "loc": (j.get("location") or {}).get("display_name") or "",
                             "url": j.get("redirect_url"), "posted": parse_dt(j.get("created")),
                             "tier": "C"})
    return jobs


def location_ok(loc):
    """Keep a role only if its location names an Indian city or India (or is blank).
    A bare "Remote" or "Hybrid" is dropped: at global companies it usually means abroad."""
    return not loc or bool(INDIA.search(loc))


def wanted(job, now):
    t = job["title"]
    if not TITLE_INCLUDE.search(t) or TITLE_EXCLUDE.search(t):
        return False
    if not location_ok(job["loc"]):
        return False
    if job["posted"] and now - job["posted"] > timedelta(days=MAX_AGE_DAYS):
        return False
    return True


def rank(job):
    t, s = job["title"], 0
    if CORE_ROLE.search(t):
        s += 3
    if ENTRY_LEVEL.search(t):
        s += 2
    if re.search(r"\bmanager\b", t, re.I):
        s -= 2
    s += {"A": 2, "B": 1}.get(job["tier"], 0)
    if PREFERRED_CITIES.search(job["loc"]):
        s += 1
    return s


def age_label(posted, now):
    if not posted:
        return ""
    days = (now - posted).days
    return "posted today" if days <= 0 else f"posted {days}d ago"


TIP = ("Apply within 48 hours, then message one recruiter and one sales leader at the "
       "company (links under each role). Short, specific, one proof point.")


def render(jobs, broken, now):
    text, cards = [], []
    for j in jobs:
        recruiters = "https://www.linkedin.com/search/results/people/?keywords=" + quote_plus(j["company"] + " recruiter")
        leaders = "https://www.linkedin.com/search/results/people/?keywords=" + quote_plus(j["company"] + " head of sales")
        meta = " · ".join(x for x in (j["company"], j["loc"] or "location n/a", age_label(j["posted"], now)) if x)
        star = "★ " if j["score"] >= 6 else ""
        text.append(f'{star}{j["title"]}\n  {meta}\n  Apply: {j["url"]}\n'
                    f'  Recruiters: {recruiters}\n  Sales leaders: {leaders}')
        e = lambda s: html.escape(s or "", quote=True)
        cards.append(
            '<div style="margin:0 0 14px;padding:12px;border:1px solid #ddd;border-radius:8px">'
            f'<div style="font-size:16px;font-weight:600">{star}<a href="{e(j["url"])}">{e(j["title"])}</a></div>'
            f'<div style="color:#555;font-size:13px;margin:4px 0 8px">{e(meta)}</div>'
            f'<div style="font-size:13px"><a href="{e(recruiters)}">Find recruiters</a> · '
            f'<a href="{e(leaders)}">Find sales leaders</a></div></div>')
    footer_text = "\n\n" + TIP
    footer_html = f'<p style="color:#555;font-size:13px">{html.escape(TIP)}</p>'
    if broken:
        note = "Could not fetch (check slug / board): " + ", ".join(broken)
        footer_text += "\n\n" + note
        footer_html += f'<p style="color:#a33;font-size:12px">{html.escape(note)}</p>'
    body_text = "\n\n".join(text) + footer_text
    body_html = ('<div style="font-family:Arial,sans-serif;max-width:640px">'
                 + "".join(cards) + footer_html + "</div>")
    return body_text, body_html


def send_email(subject, body, html_body=None):
    """Returns True if an email was actually sent, False in local test mode."""
    user = os.getenv("GMAIL_USER")
    password = os.getenv("GMAIL_APP_PASSWORD")
    to = os.getenv("TO_EMAIL")
    if not (user and password and to):
        if os.getenv("GITHUB_ACTIONS"):
            raise SystemExit("Email secrets missing: check GMAIL_USER, GMAIL_APP_PASSWORD "
                             "and TO_EMAIL under Settings > Secrets and variables > Actions.")
        print(subject, "\n\n", body)  # local test mode
        return False
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.set_content(body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, password)
        s.send_message(msg)
    return True


def main():
    now = datetime.now(timezone.utc)
    seen = set(json.loads(SEEN_FILE.read_text())) if SEEN_FILE.exists() else set()
    broken = []
    jobs = collect_company_jobs(broken) + fetch_adzuna(broken)

    fresh = [j for j in jobs if j["key"] not in seen and wanted(j, now)]
    for j in fresh:
        j["score"] = rank(j)
    fresh.sort(key=lambda j: (-j["score"], -(j["posted"].timestamp() if j["posted"] else 0)))
    batch = fresh[:MAX_JOBS_PER_EMAIL]

    if batch:
        text, html_body = render(batch, broken, now)
        queued = len(fresh) - len(batch)
        subject = f"{len(batch)} new sales roles" + (f" (+{queued} queued for next email)" if queued else "")
        if send_email(subject, text, html_body):
            seen.update(j["key"] for j in batch)
    else:
        print("No new roles.")
    if broken:
        print("Broken feeds:", broken)

    SEEN_FILE.write_text(json.dumps(sorted(seen)))


if __name__ == "__main__":
    main()
