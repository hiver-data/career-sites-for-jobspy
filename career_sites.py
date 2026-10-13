"""Company career-site jobs (Greenhouse, Lever, Ashby, Workday and 10 more) as a JobSpy-shaped DataFrame.

JobSpy (python-jobspy) searches job boards such as LinkedIn, Indeed and Glassdoor. It does not read
employers' own career sites. `scrape_career_sites()` does that through the hiver/career-site-job-search
Apify Actor and returns the same 34 columns, in the same order, as `jobspy.scrape_jobs()`, so the two
frames can be concatenated.

    from jobspy import scrape_jobs
    from career_sites import scrape_career_sites
    import pandas as pd

    boards = scrape_jobs(site_name=["indeed"], search_term="data engineer", results_wanted=20)
    careers = scrape_career_sites(search_term="data engineer", location="United States", hours_old=72)
    jobs = pd.concat([boards, careers], ignore_index=True)

Needs APIFY_TOKEN (Apify Console > Settings > API & Integrations). Pay per use on your own Apify
account: $0.003 per search plus $0.004 per job delivered (Free plan price, 2026-10-13).
"""
from __future__ import annotations

import json
import math
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime

import pandas as pd

ACTOR = "hiver~career-site-job-search"

# Column order of jobspy.scrape_jobs() (python-jobspy 1.3.0, jobspy/util.py `desired_order`).
JOBSPY_COLUMNS = [
    "id", "site", "job_url", "job_url_direct", "title", "company", "location", "date_posted", "job_type",
    "salary_source", "interval", "min_amount", "max_amount", "currency", "is_remote", "job_level",
    "job_function", "listing_type", "emails", "description", "company_industry", "company_url",
    "company_logo", "company_url_direct", "company_addresses", "company_num_employees", "company_revenue",
    "company_description", "skills", "experience_range", "company_rating", "company_reviews_count",
    "vacancy_count", "work_from_home_type",
]

_INTERVAL = {"year": "yearly", "month": "monthly", "week": "weekly", "day": "daily", "hour": "hourly"}
_JOB_TYPES = [("fulltime", "fulltime"), ("parttime", "parttime"), ("contract", "contract"),
              ("freelance", "contract"), ("intern", "internship"), ("temporary", "temporary"),
              ("temp", "temporary")]


def _job_type(value):
    """'Full time', 'FullTime', 'Full-Time Employee' -> 'fulltime' (JobSpy's job_type values)."""
    if not value:
        return None
    key = re.sub(r"[^a-z]", "", str(value).lower())
    for needle, jobspy_value in _JOB_TYPES:
        if needle in key:
            return jobspy_value
    return None


def _date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def to_jobspy_row(job: dict) -> dict:
    """One hiver/career-site-job-search dataset item -> one row with JobSpy's columns."""
    row = dict.fromkeys(JOBSPY_COLUMNS)
    has_pay = job.get("salaryMin") is not None or job.get("salaryMax") is not None
    row.update({
        "id": f"{job.get('source')}-{job.get('jobId')}",
        "site": job.get("source"),  # greenhouse, lever, ashby, workday, ...
        "job_url": job.get("url"),
        "job_url_direct": job.get("applyUrl") or job.get("url"),
        "title": job.get("title"),
        "company": job.get("company"),
        "location": job.get("location"),
        "date_posted": _date(job.get("postedAt")),
        "job_type": _job_type(job.get("employmentType")),
        # The employer's own posting: structured pay where its job system has it, else a range read from the text.
        "salary_source": "career_site" if has_pay else None,
        "interval": _INTERVAL.get(job.get("salaryInterval")) if has_pay else None,
        "min_amount": job.get("salaryMin"),
        "max_amount": job.get("salaryMax"),
        "currency": job.get("salaryCurrency") if has_pay else None,
        "is_remote": job.get("isRemote"),
        "job_level": (job.get("experienceLevel") or "").lower() or None,
        "job_function": job.get("department") or job.get("team"),
        "description": job.get("descriptionText"),
        "company_url": job.get("boardUrl"),
        "work_from_home_type": job.get("workplaceType"),
    })
    return row


def scrape_career_sites(
    search_term: str | list[str],
    location: str | list[str] | None = None,
    hours_old: int | None = None,
    results_wanted: int = 15,
    is_remote: bool = False,
    min_salary: int | None = None,
    salary_currency: str = "USD",
    fetch_description: bool = True,
    max_charge_usd: float = 0.50,
    token: str | None = None,
    api_base: str | None = None,
    timeout: int = 330,
) -> pd.DataFrame:
    """Search ~19,000 company career sites; returns a DataFrame with jobspy.scrape_jobs()'s columns.

    search_term: matched against job titles (at the start of a word, not case sensitive); a list
        means any of them. Boolean syntax such as "-senior" is not supported.
    location: a country ("United States", "US", "UK", "Germany") matches the job's country; any other
        term ("Berlin", "Remote") matches whole words of the location text. There is no radius.
    hours_old: rounded up to whole days (72 -> jobs posted in the last 3 days). Left empty, the
        Actor's default applies (last 7 days).
    results_wanted: hard cap on jobs delivered and charged.
    max_charge_usd: the run stops once it has cost this much on your Apify account.
    """
    token = token or os.environ.get("APIFY_TOKEN")
    if not token:
        raise RuntimeError("Set APIFY_TOKEN (Apify Console > Settings > API & Integrations).")
    actor_input = {
        "keywords": [search_term] if isinstance(search_term, str) else list(search_term),
        "maxJobs": int(results_wanted),
        "includeDescription": bool(fetch_description),
        "remoteOnly": bool(is_remote),
    }
    if location:
        actor_input["locations"] = [location] if isinstance(location, str) else list(location)
    if hours_old:  # without it the Actor's default applies: jobs posted in the last 7 days
        actor_input["postedWithinDays"] = max(1, math.ceil(hours_old / 24))
    if min_salary:
        actor_input["minSalary"] = int(min_salary)
        actor_input["salaryCurrency"] = salary_currency

    base = (api_base or os.environ.get("APIFY_API_BASE", "https://api.apify.com")).rstrip("/")
    query = urllib.parse.urlencode({"token": token, "maxTotalChargeUsd": max_charge_usd, "clean": "true"})
    req = urllib.request.Request(
        f"{base}/v2/acts/{ACTOR}/run-sync-get-dataset-items?{query}",
        data=json.dumps(actor_input).encode(), method="POST", headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        items = json.load(resp)

    rows = [to_jobspy_row(job) for job in items if job.get("title") and job.get("url")]
    if not rows:
        return pd.DataFrame(columns=JOBSPY_COLUMNS)
    df = pd.DataFrame(rows, columns=JOBSPY_COLUMNS)
    return df.sort_values(by=["date_posted"], ascending=False, na_position="last").reset_index(drop=True)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Company career-site jobs to CSV, in JobSpy's columns.")
    p.add_argument("search_term", nargs="+", help='e.g. "data engineer" (several = any of them)')
    p.add_argument("--location", nargs="+", help='country or place words, e.g. "United States" or Berlin')
    p.add_argument("--hours-old", type=int, default=72)
    p.add_argument("--results", type=int, default=15, help="jobs wanted (and charged), default 15")
    p.add_argument("--remote", action="store_true")
    p.add_argument("--min-salary", type=int)
    p.add_argument("--max-charge", type=float, default=0.50, help="USD cap for the run, default 0.50")
    p.add_argument("--out", default="career_site_jobs.csv")
    a = p.parse_args()
    jobs = scrape_career_sites(a.search_term, location=a.location, hours_old=a.hours_old,
                               results_wanted=a.results, is_remote=a.remote, min_salary=a.min_salary,
                               max_charge_usd=a.max_charge)
    jobs.to_csv(a.out, index=False)
    print(f"{len(jobs)} jobs from {jobs['company'].nunique()} companies -> {a.out}")
    print(jobs[["site", "company", "title", "location", "date_posted", "min_amount", "max_amount"]].head(10).to_string())
