"""Checks every slug in config/companies.yaml against its ATS.
Run locally:  python scripts/check_companies.py"""
from __future__ import annotations

import sys
from pathlib import Path

import requests
import yaml

URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{}/jobs",
    "lever": "https://api.lever.co/v0/postings/{}?mode=json&limit=1",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{}",
}

cfg = yaml.safe_load((Path(__file__).parent.parent / "config" / "companies.yaml").read_text())
bad = 0
for ats, slugs in cfg.items():
    for slug in slugs or []:
        try:
            code = requests.get(URLS[ats].format(slug), timeout=20).status_code
        except requests.RequestException as e:
            code = type(e).__name__
        ok = code == 200
        bad += not ok
        print(f"{'OK ' if ok else 'BAD'}  {ats:<10} {slug:<20} {code}")
print(f"\n{bad} broken slug(s). Find the right one in the company's careers-page URL.")
sys.exit(1 if bad else 0)
