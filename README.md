# Job Alerts

A free bot that runs on GitHub (no server, nothing on your laptop) twice a day, at 9:00 AM and 4:00 PM IST, and emails you:

1. **New sales roles** (`job_alerts.py`): SDR, BDR, inside sales, account executive, customer success and related roles at a target list of SaaS companies, ranked best-first. Each role comes with one-click LinkedIn searches for the company's recruiters and sales leaders.
2. **Funding news** (`funding_watch.py`): SaaS funding stories from Inc42, Entrackr and YourStory, each with links to that company's jobs. A freshly funded company usually hires sales soon.

The watch list grows by itself: every company in a funding story is added automatically, and a weekly run starts watching its job board.

## Files

```
job-alerts/
├── job_alerts.py            # job watcher
├── funding_watch.py         # funding-news watcher
├── find_slugs.py            # bulk-adds companies to companies.json
├── company_names.txt        # your starting list of company names
├── discovered_names.txt     # auto-created: companies found in funding news
├── companies.json           # the companies the bot actually watches
├── slug_misses.json         # auto-created: names with no supported job board
├── seen.json                # auto-created: jobs already emailed
├── seen_news.json           # auto-created: stories already emailed
└── .github/workflows/
    ├── job-alerts.yml       # twice-daily job and funding emails
    └── find-slugs.yml       # weekly (or one-click) company discovery
```

The workflow file must sit at exactly `.github/workflows/job-alerts.yml` in the repo.

## Setup (about 15 minutes)

1. **Create a GitHub repo** (private is fine) and push everything, keeping the folder layout.
2. **Make a Gmail app password.** Turn on 2-Step Verification on a throwaway sender Gmail account, then create an app password at https://myaccount.google.com/apppasswords.
3. **Add secrets** under Settings → Secrets and variables → Actions:
   - `GMAIL_USER`: the sender address
   - `GMAIL_APP_PASSWORD`: the 16-character app password
   - `TO_EMAIL`: where alerts go. Comma-separate addresses to send to more than one person.
4. **Allow commits.** Under Settings → Actions → General → Workflow permissions, choose "Read and write permissions".
5. **Test.** Open the Actions tab, pick `job-alerts`, click Run workflow.

The first run sends the 60 best-ranked matches. Anything beyond that is queued and arrives in the next emails, so the inbox is never flooded.

## Making the search wide

The bot reaches jobs three ways, so the list of companies is only part of the picture.

**1. Your company list (`company_names.txt`).**
About 160 companies across Delhi NCR, Mumbai, Bangalore, Pune and Hyderabad: global SaaS and cloud (tier A), growth-stage Indian product companies (tier B), and early-growth startups (tier C). To add more, edit the file on GitHub (one per line: `Name, A`, `Name, B` or `Name, C`), then open the Actions tab, pick `find-slugs`, and click Run workflow. For each name it tries six job-board systems (Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Recruitee) and saves the hits into `companies.json`. The run summary lists each hit with a sample job title. If a title belongs to the wrong company, delete that entry. Names with no supported board are remembered and retried after 30 days.

**2. Funding news (automatic).**
Every funding story the bot reads adds its company to `discovered_names.txt` as tier C. The `find-slugs` workflow also runs every Monday morning, so new Series A to D companies start being watched within a week, with no action from you.

**3. Adzuna (strongly recommended).**
Adzuna is a free job-search API that covers India. The bot uses it to search four SaaS sales queries in each of seven cities (Delhi, Gurgaon, Noida, Mumbai, Bangalore, Pune, Hyderabad). That finds jobs at companies that are on no list, including enterprise firms. Register at https://developer.adzuna.com, then add secrets `ADZUNA_APP_ID` and `ADZUNA_APP_KEY`. Without them the bot skips this step. Results are filtered to SaaS-sounding postings to keep out call-centre noise.

**4. Dream companies by hand.**
Salesforce (Workday), LinkedIn, SAP, Oracle, ServiceNow, Adobe and Microsoft use their own career sites, so this bot can't watch them. Set their native job alerts for sales roles in India.

## How roles are ranked

Higher score goes first, and roles scoring 6 or more get a ★.

- +3 for core entry roles (SDR, BDR, sales development, business development, inside sales)
- +2 for entry-level words (associate, executive, trainee, fresher, junior)
- +2 for tier A companies, +1 for tier B (tier C and Adzuna finds get no boost)
- +1 for Delhi NCR (edit `PREFERRED_CITIES` for other cities)
- −2 for "manager" titles

Senior, director, head, lead, engineering, recruiting, operations and marketing titles are dropped. A role is kept only if its location names an Indian city or "India" (or is blank); a bare "Remote" or "Hybrid" is dropped. Postings older than 30 days are skipped.

## Tuning

Everything lives in the `EDIT THESE` block at the top of each script: title include and exclude lists, cities, `MAX_AGE_DAYS`, `MAX_JOBS_PER_EMAIL`, and the funding keywords. Too much noise: add words to the exclude list. Missing roles: add words to the include list.

## Testing on your own machine

```
python job_alerts.py
python funding_watch.py
```

Without the Gmail environment variables set, both scripts print the email instead of sending it, and they don't mark anything as seen.

## If something breaks

- **No emails.** Open the Actions tab and read the latest run's log. Usual causes: a misspelled secret name, a wrongly pasted app password, or 2-Step Verification not enabled.
- **Emails land in spam.** Mark one as "Not spam" and add the sender to contacts.
- **"Could not fetch" in the email footer.** That company's slug or job board is wrong, or its board changed. Fix it in `companies.json` or delete the line.
- **A funding feed failed.** Open its URL in a browser. If it's dead, remove or replace it in `FEEDS`.
- **The workflow stopped running.** GitHub can disable scheduled workflows after about 60 days without repo activity. Open the Actions tab and re-enable it.
- **Runs are 10 to 30 minutes late.** Normal for GitHub's scheduler.
- **Push fails at the end of a run.** Redo setup step 4.

## Limits

- **Titles only.** The filter reads titles, not descriptions. It can't tell a good SDR role from a bad one, and postings rarely list pay.
- **No LinkedIn scraping.** It breaks LinkedIn's terms and gets accounts banned. The email only links to LinkedIn searches; you click them yourself.
- **Not every job board.** Companies on Workday or custom career sites aren't covered.
- **Cost.** A private repo gets 2,000 free Actions minutes a month. This uses about two minutes a day.

## The playbook: how to get hired faster

The bot finds roles. Speed and follow-through get the offer.

**Daily routine (30 minutes, same time every day):**
1. Open the morning email. Start with the ★ roles.
2. Apply to 3 to 5 roles the same day. Fresh postings get read; old ones pile up.
3. For each application, message one recruiter and one sales leader at that company (the links are in the email). Use a short message:
   *"Hi [name], I saw the [role] opening at [company]. I'm focused on SaaS sales and [one proof point, with a number]. Could I send you my profile?"*
4. Log it in a sheet: company, role, date applied, who you messaged, status, follow-up date.
5. Follow up once after 5 to 7 days.

**Rules that matter:**
- **Quota and numbers are the credential.** Feeder hires are judged on what you closed or booked. Prepare a one-page proof sheet: calls, demos booked, conversion rates, even from internships or campus work.
- **A referral beats a cold application.** Use LinkedIn's alumni search for each target company and ask for a 10-minute chat, not a job.
- **Funding story = same-day action.** Open the company's careers page, apply, and message the sales lead.
- **Check pay structure before accepting.** Ask for the fixed-to-variable split, the quota, and how many reps hit it.
- **Pick roles that sell a real SaaS product with demos.** Service-style "sales" jobs don't build the record that LinkedIn or Salesforce hires from.
- **Two years at a strong feeder is the path.** Hit quota, then move up to LinkedIn, Salesforce and similar companies.
