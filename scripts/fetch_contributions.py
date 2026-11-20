#!/usr/bin/env python3
"""Write data/contributions.json from the GitHub API.

Reads the real contribution calendar of the profile owner, nothing else:
this script never creates commits or activity. If the request fails, the
existing file is left untouched and the script exits with an error.

    GITHUB_TOKEN=... python scripts/fetch_contributions.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "contributions.json"
API = "https://api.github.com/graphql"
QUERY = """
query($login: String!) {
  user(login: $login) {
    repositories(privacy: PUBLIC, ownerAffiliations: OWNER) { totalCount }
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def parse(payload: dict, login: str) -> dict:
    """Turn the GraphQL answer into the shape render_cards.py reads."""
    if payload.get("errors"):
        raise ValueError(f"GitHub API error: {payload['errors'][0].get('message', 'unknown')}")
    user = (payload.get("data") or {}).get("user")
    if not user:
        raise ValueError(f"GitHub user not found: {login}")
    calendar = user["contributionsCollection"]["contributionCalendar"]
    days = [
        {"date": day["date"], "count": int(day["contributionCount"])}
        for week in calendar["weeks"]
        for day in week["contributionDays"]
    ]
    days.sort(key=lambda day: day["date"])
    return {
        "login": login,
        "public_repos": int(user["repositories"]["totalCount"]),
        "total": int(calendar["totalContributions"]),
        "days": days,
    }


def fetch(login: str, token: str) -> dict:
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode("utf-8")
    request = urllib.request.Request(
        API,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": f"{login}-profile-cards",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return parse(json.load(response), login)


def main() -> int:
    profile = json.loads((ROOT / "data" / "profile.json").read_text(encoding="utf-8"))
    login = os.environ.get("PROFILE_LOGIN") or profile["login"]
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("GITHUB_TOKEN is not set; keeping the existing data file.", file=sys.stderr)
        return 1
    try:
        data = fetch(login, token)
    except (urllib.error.URLError, ValueError, KeyError, TypeError) as error:
        print(f"Could not read contributions ({error}); keeping the existing data file.", file=sys.stderr)
        return 1
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    print(f"{login}: {data['total']} contributions over {len(data['days'])} days, {data['public_repos']} public repos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
