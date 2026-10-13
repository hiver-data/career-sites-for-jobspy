# Company career-site jobs for JobSpy users

[JobSpy](https://github.com/speedyapply/JobSpy) searches job boards (LinkedIn, Indeed, Glassdoor, ZipRecruiter, Google and others). It does not read employers' own career sites; its open feature request ["Scrape directly from company career website" (#368)](https://github.com/speedyapply/JobSpy/issues/368) asks for that, and a 2024 Workday request was closed with "I prefer this repo to be major job boards".

`career_sites.py` fills that gap from Python. One call searches about 19,000 company career sites on 14 job systems (Greenhouse, Lever, Ashby, Workday, SmartRecruiters, Oracle, iCIMS, Personio, Teamtailor, BambooHR, Breezy, Pinpoint, Rippling, Recruitee) and returns a pandas DataFrame with **the same 34 columns, in the same order, as `jobspy.scrape_jobs()`**, so you can `pd.concat` the two.

```python
import pandas as pd
from jobspy import scrape_jobs
from career_sites import scrape_career_sites

boards = scrape_jobs(site_name=["indeed", "linkedin"], search_term="data engineer",
                     location="United States", results_wanted=20, hours_old=72)
careers = scrape_career_sites(search_term="data engineer", location="United States",
                              hours_old=72, results_wanted=20)
jobs = pd.concat([boards, careers], ignore_index=True)
jobs.to_csv("jobs.csv", index=False)
```

The search runs on the [hiver/career-site-job-search](https://apify.com/hiver/career-site-job-search?utm_source=github&utm_campaign=jobspy-career-sites) Apify Actor, so there is no proxy to set up and nothing to scrape locally. Unofficial: not affiliated with or endorsed by JobSpy, any job-system vendor or any employer.

## Setup

```bash
pip install -r requirements.txt          # pandas (python-jobspy only if you want to combine)
export APIFY_TOKEN=...                   # Apify Console > Settings > API & Integrations
python career_sites.py "data engineer" --location "United States" --hours-old 72 --results 20
```

The command line writes `career_site_jobs.csv` in JobSpy's columns and prints the first rows.

## What it costs

Pay per use on your own Apify account (Free plan prices on 2026-10-13): **$0.003 per search plus $0.004 per job delivered**, plus Apify's $0.00005 run start. 20 jobs cost about $0.083. `results_wanted` is a hard cap on jobs delivered and charged, and `max_charge_usd` (default $0.50) stops the run at that amount. Apify's free plan includes monthly credit for trying it.

## Arguments

| `scrape_career_sites()` | JobSpy equivalent | Notes |
|---|---|---|
| `search_term` | `search_term` | Matched against job titles, at the start of a word, not case sensitive. A list means any of them. No boolean syntax (`-senior`). |
| `location` | `location` | A country (`"United States"`, `"US"`, `"UK"`, `"Germany"`) matches the country the employer's job system records; any other term (`"Berlin"`, `"Remote"`) matches whole words in the location. A list means any. No `distance` radius. |
| `hours_old` | `hours_old` | Rounded up to whole days. Left empty: last 7 days. |
| `results_wanted` | `results_wanted` | Hard cap on jobs delivered and charged (default 15). |
| `is_remote` | `is_remote` | Only jobs the employer marks remote (or whose location says remote). |
| `min_salary` | none | Keep jobs whose posted pay range reaches this annual amount; jobs left out are not charged. |
| `fetch_description` | `fetch_description` | Adds `description` (plain text). Same price either way. |

## Columns

Every JobSpy column is present. Filled from the employer's own posting:

| JobSpy column | From the career site |
|---|---|
| `site` | the job system: `greenhouse`, `lever`, `ashby`, `workday`, `smartrecruiters`, ... |
| `id` | `<site>-<job id>` |
| `job_url`, `job_url_direct` | posting page, apply link |
| `title`, `company`, `location`, `date_posted` | as published |
| `job_type` | `fulltime`, `parttime`, `contract`, `internship`, `temporary` where the system states it |
| `min_amount`, `max_amount`, `interval`, `currency` | structured pay where the job system has it, otherwise a range stated in the posting text; empty when neither exists |
| `salary_source` | `career_site` when there is a pay range, else empty |
| `is_remote`, `work_from_home_type` | remote flag and `onsite` / `hybrid` / `remote` |
| `job_level`, `job_function` | experience level, department |
| `description` | plain-text description |
| `company_url` | the company's job board |

Board-only columns (`emails`, `company_logo`, `company_rating`, `company_reviews_count`, `company_industry`, `company_num_employees`, `skills`, ...) are empty for career-site rows.

Example rows (real items from a cloud run of the Actor on 2026-10-12, keyword `engineer`, last 7 days; full rows in `tests/rows.json`):

| site | company | title | location | min_amount | max_amount | interval |
|---|---|---|---|---|---|---|
| lever | cmgx | Senior Frontend Engineer (Analytics Product Lead) | United States | 180000 | 200000 | yearly |
| greenhouse | Goodshuffle Pro | Lead Software Engineer | Washington, D.C | 220000 | 250000 | yearly |
| workday | tencent | Senior AI Infrastructure Engineer | US-California-Palo Alto | 124800 | 283800 | yearly |
| smartrecruiters | LinkedIn | Sr. Software Engineer | New York, NY, United States | 129000 | 212000 | yearly |
| ashby | linro | Forward Deployed Engineer (all genders) | Germany | 60000 | 110000 | yearly |

In that run (893 jobs from 345 companies, 169 s), 400 of the 893 postings stated a pay range.

## How fresh are the jobs?

The Actor answers from an index of all 19,000 boards that is refreshed on a rotation, stalest parts first, then re-reads every match from the employer's own board, which drops jobs closed since the refresh and adds the description, pay and current date. Each run's status line says how old the oldest part of the index was. A company board the directory lacks can be added in the Actor's `extraBoards` input (not exposed here).

## Limits

- One call waits for the run (Apify's `run-sync-get-dataset-items`, up to 5 minutes). Keep `results_wanted` under about 1,000: the 893-job run above took 169 s.
- Titles are matched as text, not by meaning: "software developer" will not find "programmer".
- Workable boards are off (Workable rate-limits hard); SAP SuccessFactors and Taleo are not covered.
- `hours_old` is day-precise; Workday reports "posted N days ago" only.

## Tests (offline, no Apify account)

```bash
pip install -r requirements.txt
python tests/test_career_sites.py
```

A mock Apify API serves 8 real dataset items (7 job systems) from cloud run `kfCsYechpPuaD515k` of the Actor (build 0.11.6, 2026-10-12). The test checks the input sent to the Actor, the mapping, that a JobSpy-shaped frame concatenates, and, when `python-jobspy` is installed, that the column list equals `jobspy.util.desired_order` of the installed version (checked against python-jobspy 1.3.0). This script has not yet been run against the live Apify API; the rows and the endpoint are real, the call in between is mocked.

## Related

- [hiver/all-open-jobs-by-company](https://apify.com/hiver/all-open-jobs-by-company?utm_source=github&utm_campaign=jobspy-career-sites): every open job at a list of companies you name (`stripe.com`, `Spotify`), when you know the employers rather than the keywords. Examples: [hiver-data/all-open-jobs-by-company](https://github.com/hiver-data/all-open-jobs-by-company).
- [hiver-data/career-site-job-alerts](https://github.com/hiver-data/career-site-job-alerts): the same search as a daily GitHub Actions alert to Slack or Discord.

MIT licence.
