#!/usr/bin/env python3
"""Raw data dump for the trajectory analysis (preview branch only).

Writes preview/raw.json with: daily contribution calendar since joining, metadata for every
public repo with contributions (owner, description, topics, languages, dates, stars), and
timestamps of the user's own commits in those repos (REST, author=<user>).
"""
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone

USER = "mvishiu11"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "preview")
TOKEN = os.environ["GH_TOKEN"]


def get(url, data=None):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data else None, headers={
        "Authorization": f"bearer {TOKEN}", "User-Agent": "profile-dump", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r), r.headers


def gql(q, **v):
    body, _ = get("https://api.github.com/graphql", {"query": q, "variables": v})
    if "errors" in body:
        raise SystemExit(body["errors"])
    return body["data"]


totals = json.load(open(os.path.join(OUT, "totals.json")))
created = datetime.fromisoformat(totals["joined"]).replace(tzinfo=timezone.utc)
now = datetime.now(timezone.utc)

# daily calendar
days = {}
for year in range(created.year, now.year + 1):
    start = max(created, datetime(year, 1, 1, tzinfo=timezone.utc))
    end = min(now, datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc))
    cal = gql("""query($l:String!,$f:DateTime!,$t:DateTime!){user(login:$l){contributionsCollection(from:$f,to:$t){
      contributionCalendar{weeks{contributionDays{date contributionCount}}}}}}""",
              l=USER, f=start.isoformat(), t=end.isoformat())["user"]["contributionsCollection"]["contributionCalendar"]
    for w in cal["weeks"]:
        for d in w["contributionDays"]:
            if start.date().isoformat() <= d["date"] <= end.date().isoformat():
                days[d["date"]] = d["contributionCount"]

repos = {}
for nwo, rec in totals["by_repo"].items():
    if rec["private"]:
        continue
    try:
        meta, _ = get(f"https://api.github.com/repos/{nwo}")
        langs, _ = get(f"https://api.github.com/repos/{nwo}/languages")
    except Exception as e:  # repo renamed or gone
        print("skip", nwo, e)
        continue
    commits = []
    page = 1
    while page <= 20:
        q = urllib.parse.urlencode({"author": USER, "per_page": 100, "page": page})
        try:
            batch, _ = get(f"https://api.github.com/repos/{nwo}/commits?{q}")
        except Exception as e:
            print("commits fail", nwo, e)
            break
        for c in batch:
            commits.append({
                "date": c["commit"]["author"]["date"],
                "msg": c["commit"]["message"].split("\n")[0][:120],
                "files": None,
            })
        if len(batch) < 100:
            break
        page += 1
    repos[nwo] = {
        "owner": meta["owner"]["login"],
        "owner_type": meta["owner"]["type"],
        "description": meta.get("description"),
        "topics": meta.get("topics", []),
        "language": meta.get("language"),
        "languages": langs,
        "created_at": meta["created_at"],
        "pushed_at": meta["pushed_at"],
        "stars": meta["stargazers_count"],
        "forks": meta["forks_count"],
        "fork": meta["fork"],
        "size_kb": meta["size"],
        "contrib": rec,
        "commits": commits,
    }
    print(f"{nwo}: {len(commits)} commits")

with open(os.path.join(OUT, "raw.json"), "w") as f:
    json.dump({"generated": now.isoformat(), "days": days, "repos": repos}, f)
