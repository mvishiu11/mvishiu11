#!/usr/bin/env python3
"""All-time GitHub totals and streaks, rendered as a preview card (not linked from the README).

Methods match the two common public cards:
- Total contributions, current and longest streak: summed contribution calendars for every
  year since the account was created (github-readme-streak-stats method).
- Total commits, all time: REST commit search `author:<user>` (github-readme-stats
  include_all_commits method; counts public commits on default branches).
"""
import json
import os
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from html import escape

USER = "mvishiu11"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "preview")
TOKEN = os.environ["GH_TOKEN"]


def api(url, data=None):
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode() if data else None,
        headers={
            "Authorization": f"bearer {TOKEN}",
            "User-Agent": "profile-totals",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def gql(query, **variables):
    body = api("https://api.github.com/graphql", {"query": query, "variables": variables})
    if "errors" in body:
        raise SystemExit(f"GraphQL error: {body['errors']}")
    return body["data"]


BASE = gql(
    """query($login: String!) { user(login: $login) {
      createdAt
      followers { totalCount }
      pullRequests { totalCount }
      openIssues: issues(states: OPEN) { totalCount }
      closedIssues: issues(states: CLOSED) { totalCount }
      repositoriesContributedTo(first: 1, contributionTypes: [COMMIT, PULL_REQUEST, ISSUE, REPOSITORY]) { totalCount }
    } }""",
    login=USER,
)["user"]

YEAR_Q = """query($login: String!, $from: DateTime!, $to: DateTime!) { user(login: $login) {
  contributionsCollection(from: $from, to: $to) {
    totalCommitContributions
    restrictedContributionsCount
    totalPullRequestContributions
    totalIssueContributions
    totalPullRequestReviewContributions
    contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
    commitContributionsByRepository(maxRepositories: 100) { repository { nameWithOwner isPrivate isFork } contributions { totalCount } }
    pullRequestContributionsByRepository(maxRepositories: 100) { repository { nameWithOwner isPrivate isFork } contributions { totalCount } }
    issueContributionsByRepository(maxRepositories: 100) { repository { nameWithOwner isPrivate isFork } contributions { totalCount } }
    pullRequestReviewContributionsByRepository(maxRepositories: 100) { repository { nameWithOwner isPrivate isFork } contributions { totalCount } }
  }
} }"""
by_repo = {}

created = datetime.fromisoformat(BASE["createdAt"].replace("Z", "+00:00"))
now = datetime.now(timezone.utc)
days = {}
per_year = []
for year in range(created.year, now.year + 1):
    start = max(created, datetime(year, 1, 1, tzinfo=timezone.utc))
    end = min(now, datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc))
    cc = gql(YEAR_Q, login=USER, **{"from": start.isoformat(), "to": end.isoformat()})["user"]["contributionsCollection"]
    for w in cc["contributionCalendar"]["weeks"]:
        for d in w["contributionDays"]:
            if start.date().isoformat() <= d["date"] <= end.date().isoformat():
                days[d["date"]] = d["contributionCount"]
    for kind, key in [("commits", "commitContributionsByRepository"), ("prs", "pullRequestContributionsByRepository"),
                      ("issues", "issueContributionsByRepository"), ("reviews", "pullRequestReviewContributionsByRepository")]:
        for item in cc[key]:
            r = item["repository"]
            rec = by_repo.setdefault(r["nameWithOwner"], {"private": r["isPrivate"], "fork": r["isFork"], "commits": 0, "prs": 0, "issues": 0, "reviews": 0, "years": {}})
            n = item["contributions"]["totalCount"]
            rec[kind] += n
            rec["years"][str(year)] = rec["years"].get(str(year), 0) + n
    per_year.append({
        "year": year,
        "contributions": cc["contributionCalendar"]["totalContributions"],
        "commits": cc["totalCommitContributions"] + cc["restrictedContributionsCount"],
        "prs": cc["totalPullRequestContributions"],
        "issues": cc["totalIssueContributions"],
        "reviews": cc["totalPullRequestReviewContributions"],
    })

# Streaks (same rule as streak-stats: today without contributions doesn't break the current streak)
ordered = sorted(days)
longest = (0, None, None)
run_len, run_start = 0, None
for ds in ordered:
    if days[ds] > 0:
        if run_len == 0:
            run_start = ds
        run_len += 1
        if run_len > longest[0]:
            longest = (run_len, run_start, ds)
    else:
        run_len = 0
today = now.date()
cur = today if days.get(today.isoformat(), 0) > 0 else today - timedelta(days=1)
current_end = cur
current = 0
while days.get(cur.isoformat(), 0) > 0:
    current += 1
    cur -= timedelta(days=1)
current_start = cur + timedelta(days=1)

search = api("https://api.github.com/search/commits?" + urllib.parse.urlencode({"q": f"author:{USER}", "per_page": 1}))

totals = {
    "generated": now.strftime("%Y-%m-%d %H:%M UTC"),
    "joined": created.date().isoformat(),
    "total_contributions": sum(days.values()),
    "total_commits_all_time_search": search["total_count"],
    "commit_contributions_all_years": sum(y["commits"] for y in per_year),
    "total_prs": BASE["pullRequests"]["totalCount"],
    "total_issues": BASE["openIssues"]["totalCount"] + BASE["closedIssues"]["totalCount"],
    "followers": BASE["followers"]["totalCount"],
    "contributed_to": BASE["repositoriesContributedTo"]["totalCount"],
    "active_days": sum(1 for v in days.values() if v > 0),
    "best_day": max(days.items(), key=lambda kv: kv[1]) if days else None,
    "current_streak": {"days": current, "from": current_start.isoformat() if current else None, "to": current_end.isoformat() if current else None},
    "longest_streak": {"days": longest[0], "from": longest[1], "to": longest[2]},
    "per_year": per_year,
}
for rec in by_repo.values():
    rec["total"] = rec["commits"] + rec["prs"] + rec["issues"] + rec["reviews"]
totals["by_repo"] = dict(sorted(by_repo.items(), key=lambda kv: -kv[1]["total"]))

os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, "totals.json"), "w") as f:
    json.dump(totals, f, indent=2)
print(json.dumps({k: v for k, v in totals.items() if k not in ("per_year", "by_repo")}, indent=2))

# ---------- preview card, drawing-sheet style ----------
THEMES = {
    "light": dict(paper="#F4F5F1", grid="#E2E5DE", ink="#1B2024", ink2="#565E65", rule="#C3C8C0", red="#C4122F"),
    "dark": dict(paper="#0E1A29", grid="#172A40", ink="#E4ECF4", ink2="#9DB0C4", rule="#2B4260", red="#FF7A7A"),
}
MONO = "'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
DISPLAY = "'Archivo Narrow', 'Arial Narrow', 'Helvetica Neue', Arial, sans-serif"


def fmt(n):
    return f"{n:,}".replace(",", " ")


def days_label(n):
    return f"{n} day" if n == 1 else f"{n} days"


def dshort(s):
    return datetime.fromisoformat(s).strftime("%-d %b %Y") if s else "none"


def render(t):
    W, H = 900, 300
    o = []
    a = o.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
      f'aria-label="All-time GitHub totals for {USER}: {totals["total_contributions"]} contributions, longest streak {totals["longest_streak"]["days"]} days">')
    a(f'<defs><pattern id="g" width="16" height="16" patternUnits="userSpaceOnUse"><path d="M16 0H0V16" fill="none" stroke="{t["grid"]}"/></pattern></defs>')
    a(f'<rect width="{W}" height="{H}" fill="{t["paper"]}"/><rect width="{W}" height="{H}" fill="url(#g)"/>')
    a(f'<rect x="8" y="8" width="{W-16}" height="{H-16}" fill="none" stroke="{t["ink"]}" stroke-width="1.5"/>')
    a(f'<line x1="8" y1="34" x2="{W-8}" y2="34" stroke="{t["ink"]}"/>')
    a(f'<text x="24" y="26" font-family="{MONO}" font-size="11" fill="{t["ink2"]}" letter-spacing="0.6">SHEET 3 | ALL-TIME, SINCE {totals["joined"][:4]}</text>')
    a(f'<text x="{W-24}" y="26" text-anchor="end" font-family="{MONO}" font-size="11" fill="{t["ink2"]}">REV {totals["generated"][:10]}</text>')

    # three big figures
    figs = [
        ("TOTAL CONTRIBUTIONS", fmt(totals["total_contributions"]), f'{dshort(totals["joined"])} to today'),
        ("LONGEST STREAK", days_label(totals["longest_streak"]["days"]), f'{dshort(totals["longest_streak"]["from"])} to {dshort(totals["longest_streak"]["to"])}'),
        ("CURRENT STREAK", days_label(totals["current_streak"]["days"]), (f'since {dshort(totals["current_streak"]["from"])}' if totals["current_streak"]["days"] else "start one today")),
    ]
    cw = (W - 16) / 3
    for i, (label, big, sub) in enumerate(figs):
        x = 8 + i * cw
        if i:
            a(f'<line x1="{x:.1f}" y1="34" x2="{x:.1f}" y2="160" stroke="{t["ink"]}"/>')
        cx = x + cw / 2
        a(f'<text x="{cx:.1f}" y="60" text-anchor="middle" font-family="{MONO}" font-size="10" fill="{t["ink2"]}" letter-spacing="0.8">{label}</text>')
        a(f'<text x="{cx:.1f}" y="112" text-anchor="middle" font-family="{DISPLAY}" font-size="46" font-weight="700" fill="{t["ink"]}">{escape(big)}</text>')
        if i == 1:
            a(f'<ellipse cx="{cx:.1f}" cy="96" rx="{min(28 + 13 * len(big), cw/2 - 14):.0f}" ry="32" transform="rotate(-4 {cx:.1f} 96)" fill="none" stroke="{t["red"]}" stroke-width="2"/>')
        a(f'<text x="{cx:.1f}" y="146" text-anchor="middle" font-family="{MONO}" font-size="11" fill="{t["ink2"]}">{escape(sub)}</text>')

    a(f'<line x1="8" y1="160" x2="{W-8}" y2="160" stroke="{t["ink"]}"/>')
    # left: secondary totals
    rows = [("Commits, all time", totals["total_commits_all_time_search"]), ("Pull requests", totals["total_prs"]),
            ("Active days", totals["active_days"]), ("Repos contributed to", totals["contributed_to"])]
    for i, (label, val) in enumerate(rows):
        y = 186 + i * 25
        a(f'<text x="24" y="{y}" font-family="{MONO}" font-size="12" fill="{t["ink2"]}">{label}</text>')
        a(f'<text x="306" y="{y}" text-anchor="end" font-family="{MONO}" font-size="12.5" font-weight="500" fill="{t["ink"]}">{fmt(val)}</text>')
        a(f'<line x1="24" y1="{y+8}" x2="306" y2="{y+8}" stroke="{t["rule"]}"/>')
    a(f'<line x1="330" y1="160" x2="330" y2="{H-8}" stroke="{t["ink"]}"/>')
    # right: contributions per year bars
    a(f'<text x="352" y="182" font-family="{MONO}" font-size="10" fill="{t["ink2"]}" letter-spacing="0.8">CONTRIBUTIONS PER YEAR</text>')
    py = totals["per_year"]
    mx = max(y["contributions"] for y in py) or 1
    bw = (W - 24 - 352) / len(py)
    for i, y in enumerate(py):
        h = 62 * y["contributions"] / mx
        x = 352 + i * bw
        color = t["red"] if y["contributions"] == mx else t["ink"]
        a(f'<rect x="{x+6:.1f}" y="{262-h:.1f}" width="{bw-12:.1f}" height="{max(h,1):.1f}" fill="{color}"/>')
        a(f'<text x="{x+bw/2:.1f}" y="{256-h:.1f}" text-anchor="middle" font-family="{MONO}" font-size="10.5" fill="{t["ink"]}">{fmt(y["contributions"])}</text>')
        a(f'<text x="{x+bw/2:.1f}" y="278" text-anchor="middle" font-family="{MONO}" font-size="10.5" fill="{t["ink2"]}">{y["year"]}</text>')
    a("</svg>")
    return "\n".join(o)


for name, t in THEMES.items():
    with open(os.path.join(OUT, f"totals-{name}.svg"), "w") as f:
        f.write(render(t))
