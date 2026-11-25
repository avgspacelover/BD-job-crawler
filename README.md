# Job Alerts

A free, zero-server bot that does two things every morning at 9:00 AM IST and emails you the results:

1. **Job watch** (`job_alerts.py`): checks the careers pages of a target list of SaaS companies for new sales roles (SDR, BDR, inside sales, account executive, customer success) in your chosen cities.
2. **Funding watch** (`funding_watch.py`): scans Inc42, Entrackr and YourStory for new SaaS funding stories. A freshly funded company usually hires sales soon, so these are leads.

It runs on GitHub Actions. Nothing runs on your laptop.

## Files

```
job-alerts/
├── job_alerts.py            # job watcher
├── funding_watch.py         # funding-news watcher
├── companies.json           # your target company list
├── seen.json                # auto-created: jobs already emailed
├── seen_news.json           # auto-created: stories already emailed
└── .github/workflows/
    └── job-alerts.yml       # the daily schedule (the cron)
```

The workflow file must sit at exactly `.github/workflows/job-alerts.yml` in the repo, or GitHub ignores it.

## Setup (about 15 minutes)

1. **Create a GitHub repo** (private is fine) and push all the files above, keeping the folder layout.
2. **Make a Gmail app password.** Turn on 2-Step Verification on the sender Gmail account, then create an app password at https://myaccount.google.com/apppasswords. Use a throwaway Gmail account for sending, not your main one.
3. **Add three secrets** in the repo under Settings → Secrets and variables → Actions:
   - `GMAIL_USER`: the sender address
   - `GMAIL_APP_PASSWORD`: the 16-character app password
   - `TO_EMAIL`: where alerts go. Comma-separate several addresses to send to more than one person.
4. **Check workflow permissions.** Under Settings → Actions → General → Workflow permissions, choose "Read and write permissions" (the workflow commits `seen.json` back to the repo).
5. **Test it.** Open the Actions tab, pick `job-alerts`, click Run workflow. You should get an email in a couple of minutes.

The first run emails every currently open matching role and every matching story in the feeds, so expect a long email. After that you only get new items.

## Adding companies

Add one line per company to `companies.json`:

```json
{"name": "Postman", "ats": "greenhouse", "slug": "postman", "tier": "A"}
```

- **ats** is `greenhouse`, `lever` or `ashby`.
- **slug** is the company's name on that job board. Open the company's careers page and click a job. If the URL looks like `boards.greenhouse.io/postman/...`, `jobs.lever.co/postman/...` or `jobs.ashbyhq.com/postman/...`, the slug is `postman`.
- **tier** is `A` for dream targets (LinkedIn, Salesforce-adjacent brands) and `B` for strong feeder companies. Emails list tier A first, so apply top-down.

The starter slugs in the file are best guesses. Any that fail are listed at the bottom of the email as "Could not fetch". Fix or remove those. Companies on other systems (Workday, custom career sites, Workable) are not covered yet; each needs a small fetch function.

Where to find companies: SaaSBoomi's member directory, Tracxn lists, and the funding stories this bot emails. Build the list once, then let the bot watch it.

## Tuning the filters

Both scripts have an `EDIT THESE FILTERS` block at the top.

- `TITLE_INCLUDE` and `TITLE_EXCLUDE` in `job_alerts.py` decide which job titles match. Too much noise: add words to the exclude list. Missing roles: add words to the include list.
- `LOCATION_OK` lists the cities. Jobs with a blank location are kept.
- `FUNDING` and `SAAS` in `funding_watch.py` decide which stories count as SaaS funding news.

## Testing on your own machine

```
pip install requests
python job_alerts.py
python funding_watch.py
```

Without the three environment variables set, both scripts print results instead of emailing. Delete the `seen.json` and `seen_news.json` files this creates before you push, otherwise the first real run will email nothing.

## Changing the schedule

Edit the cron line in `job-alerts.yml`. GitHub uses UTC, so `30 3 * * *` is 9:00 AM IST. The funding watcher should stay daily: RSS feeds only hold each site's latest posts, so a weekly run would miss most stories.

## If something breaks

- **No emails.** Open the Actions tab and read the log of the latest run. Common causes: a wrong secret name, an app password with spaces pasted wrongly, or 2-Step Verification not enabled.
- **Emails land in spam.** Mark one as "Not spam" and add the sender to contacts.
- **The workflow stopped running.** GitHub can disable scheduled workflows after about 60 days without repo activity, mostly in public repos. Open the Actions tab and re-enable it.
- **Runs are 10 to 30 minutes late.** Normal for GitHub's scheduler.
- **Push fails at the end of the run.** Revisit step 4 of the setup.
- **A feed shows as failed.** Open its URL in a browser. If the site changed or blocked the feed, remove it from `FEEDS` or replace it.

## Limits to know about

- **Titles only.** The filter reads job titles, not descriptions. It cannot tell a good SDR role from a bad one, and postings rarely list pay.
- **Not LinkedIn.** Scraping LinkedIn breaks its terms and gets accounts banned. Set up LinkedIn's own saved-search job alerts alongside this bot; they are free.
- **Cost.** A private repo gets 2,000 free Actions minutes a month. This bot uses about one minute a day.
- **Be polite to sources.** Do not run it more than once or twice a day.

## Advice for the job search itself

1. **Go top-down.** Apply to tier A companies first, then tier B. A year or two at a strong feeder company is the realistic route into LinkedIn or Salesforce account management.
2. **Quota attainment is the credential.** Companies hiring from feeders look at the numbers you hit more than at the logo. Choose roles where you will carry a quota and make demo calls over service-style "sales" jobs that never sell a product.
3. **Read the pay structure.** Ask for the fixed-to-variable split, the quota, and how many reps hit it. A big OTE with a low fixed part is a red flag for a fresher.
4. **Apply fast.** The first few days after a posting goes up are when applications get read. This is the point of a daily alert.
5. **Use funding leads.** When a funding story arrives, open that company's careers page the same day and message the sales lead or recruiter on LinkedIn with one specific line about what you would sell.
6. **Track everything** in a simple sheet: company, role, date applied, contact, status, follow-up date. Follow up after 5 to 7 days.
