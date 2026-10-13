"""Offline test: no Apify account, no spend. From the repo root: python tests/test_career_sites.py

A mock Apify API serves tests/rows.json (real dataset items from a cloud run of
hiver/career-site-job-search 0.11.6, run kfCsYechpPuaD515k, 2026-10-12). Checks the input sent, the
column order, the mapping, and that the frame concatenates with a real jobspy.scrape_jobs()-shaped
frame. If python-jobspy is installed, the column list is compared with jobspy's own.
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from career_sites import JOBSPY_COLUMNS, scrape_career_sites  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROWS = json.load(open(os.path.join(HERE, "rows.json")))["rows"]
SEEN = {}


class Mock(BaseHTTPRequestHandler):
    def do_POST(self):
        SEEN["path"] = self.path
        SEEN["input"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        body = json.dumps(ROWS).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main():
    server = HTTPServer(("127.0.0.1", 0), Mock)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"

    df = scrape_career_sites(["data engineer", "engineer"], location="United States", hours_old=72,
                             results_wanted=20, min_salary=150000, token="test", api_base=base)

    # input sent to the Actor
    assert SEEN["path"].startswith("/v2/acts/hiver~career-site-job-search/run-sync-get-dataset-items?"), SEEN["path"]
    assert "maxTotalChargeUsd=0.5" in SEEN["path"] and "token=test" in SEEN["path"]
    assert SEEN["input"] == {"keywords": ["data engineer", "engineer"], "maxJobs": 20, "includeDescription": True,
                             "remoteOnly": False, "locations": ["United States"], "postedWithinDays": 3,
                             "minSalary": 150000, "salaryCurrency": "USD"}, SEEN["input"]

    # same columns, same order as jobspy.scrape_jobs()
    assert list(df.columns) == JOBSPY_COLUMNS and len(JOBSPY_COLUMNS) == 34
    try:
        from jobspy.util import desired_order
        assert list(desired_order) == JOBSPY_COLUMNS, "column list differs from installed python-jobspy"
        print("OK: columns == jobspy.util.desired_order of the installed python-jobspy")
    except ImportError:
        print("skip: python-jobspy not installed, column list checked against the copy in career_sites.py")

    assert len(df) == len(ROWS) == 8
    assert sorted(df["site"].unique()) == ["ashby", "breezy", "greenhouse", "lever", "smartrecruiters",
                                          "teamtailor", "workday"]
    assert df["date_posted"].is_monotonic_decreasing  # newest first, like jobspy within a site
    lever = df[df["site"] == "lever"].iloc[0]
    assert (lever["company"], lever["min_amount"], lever["max_amount"], lever["interval"], lever["currency"],
            lever["job_type"], lever["salary_source"]) == ("cmgx", 180000, 200000, "yearly", "USD", "fulltime",
                                                            "career_site"), lever.to_dict()
    hourly = df[df["min_amount"] == 30].iloc[0]
    assert (hourly["interval"], hourly["job_type"]) == ("hourly", "contract")
    no_pay = df[df["site"] == "teamtailor"].iloc[0]
    assert pd.isna(no_pay["min_amount"]) and pd.isna(no_pay["salary_source"]) and pd.isna(no_pay["currency"])
    assert df["job_url"].str.startswith("https://").all() and df["id"].is_unique

    # concatenates with a JobSpy frame (one row shaped like jobspy's output)
    board = pd.DataFrame([{**dict.fromkeys(JOBSPY_COLUMNS), "id": "in-1", "site": "indeed", "title": "Data Engineer",
                           "company": "Example Co", "job_url": "https://www.indeed.com/viewjob?jk=1"}],
                         columns=JOBSPY_COLUMNS)
    both = pd.concat([board, df], ignore_index=True)
    assert list(both.columns) == JOBSPY_COLUMNS and len(both) == 9

    server.shutdown()
    print(f"OK: {len(df)} career-site jobs from {df['site'].nunique()} job systems in JobSpy's 34 columns; "
          f"concat with a JobSpy frame -> {len(both)} rows")
    print(df[["site", "company", "title", "location", "date_posted", "min_amount", "max_amount", "interval"]]
          .to_string(index=False))


if __name__ == "__main__":
    main()
