#!/usr/bin/env python3
"""Render the profile stats card (light and dark SVG) in the drawing-sheet style.

Data comes from the GitHub GraphQL API (public data only), token in $GH_TOKEN.
The rank follows github-readme-stats' calculateRank (MIT) so the letter grade
matches what the old public card showed.

Usage:
  GH_TOKEN=... python3 scripts/stats.py            # fetch live data
  python3 scripts/stats.py --fixture sample.json   # render from saved data
"""
import json
import math
import os
import sys
import urllib.request
from datetime import datetime, timezone
from html import escape

USER = "mvishiu11"
OUT = os.path.join(os.path.dirname(__file__), "..", "assets")
EXCLUDE_LANGS = {"Jupyter Notebook", "HTML", "CSS", "Makefile", "CMake", "Dockerfile", "Shell", "Batchfile"}

QUERY = """
query($login: String!, $after: String) {
  user(login: $login) {
    followers { totalCount }
    pullRequests { totalCount }
    openIssues: issues(states: OPEN) { totalCount }
    closedIssues: issues(states: CLOSED) { totalCount }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
      totalPullRequestReviewContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { contributionCount date } }
      }
    }
    repositories(first: 100, after: $after, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        stargazerCount
        languages(first: 10, orderBy: { field: SIZE, direction: DESC }) {
          edges { size node { name } }
        }
      }
    }
  }
}
"""


def gql(token, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": "profile-stats"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.load(r)
    if "errors" in body:
        raise SystemExit(f"GraphQL error: {body['errors']}")
    return body["data"]["user"]


def fetch(token):
    first = gql(token, {"login": USER, "after": None})
    repos = list(first["repositories"]["nodes"])
    page = first["repositories"]["pageInfo"]
    while page["hasNextPage"]:
        nxt = gql(token, {"login": USER, "after": page["endCursor"]})
        repos += nxt["repositories"]["nodes"]
        page = nxt["repositories"]["pageInfo"]

    cc = first["contributionsCollection"]
    langs = {}
    for repo in repos:
        for e in repo["languages"]["edges"]:
            langs[e["node"]["name"]] = langs.get(e["node"]["name"], 0) + e["size"]
    days = [d["contributionCount"] for w in cc["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    return {
        "stars": sum(r["stargazerCount"] for r in repos),
        "commits": cc["totalCommitContributions"] + cc["restrictedContributionsCount"],
        "prs": first["pullRequests"]["totalCount"],
        "issues": first["openIssues"]["totalCount"] + first["closedIssues"]["totalCount"],
        "reviews": cc["totalPullRequestReviewContributions"],
        "followers": first["followers"]["totalCount"],
        "repos": first["repositories"]["totalCount"],
        "contributions": cc["contributionCalendar"]["totalContributions"],
        "languages": langs,
        "days": days,
    }


def rank(s):
    """Port of github-readme-stats calculateRank (commits = last year, not all-time)."""
    exp = lambda x: 1 - 2 ** -x
    lnorm = lambda x: x / (1 + x)
    parts = [
        (2, exp(s["commits"] / 250)),
        (3, exp(s["prs"] / 50)),
        (1, exp(s["issues"] / 25)),
        (1, exp(s["reviews"] / 2)),
        (4, lnorm(s["stars"] / 50)),
        (1, lnorm(s["followers"] / 10)),
    ]
    total = sum(w for w, _ in parts)
    r = 1 - sum(w * v for w, v in parts) / total
    thresholds = [1, 12.5, 25, 37.5, 50, 62.5, 75, 87.5, 100]
    levels = ["S", "A+", "A", "A-", "B+", "B", "B-", "C+", "C"]
    level = next(l for t, l in zip(thresholds, levels) if r * 100 <= t)
    return level, r * 100


THEMES = {
    "light": dict(paper="#F4F5F1", grid="#E2E5DE", ink="#1B2024", ink2="#565E65", rule="#C3C8C0", red="#C4122F",
                  ramp=["#1B2024", "#3D454B", "#5F676E", "#848B91", "#A9AFB3", "#CDD1CE"], cell0="#E6E9E3"),
    "dark": dict(paper="#0E1A29", grid="#172A40", ink="#E4ECF4", ink2="#9DB0C4", rule="#2B4260", red="#FF7A7A",
                 ramp=["#E4ECF4", "#B9C8D7", "#8FA4BA", "#6B829C", "#4C627E", "#344A66"], cell0="#152438"),
}
MONO = "'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
DISPLAY = "'Archivo Narrow', 'Arial Narrow', 'Helvetica Neue', Arial, sans-serif"


def fmt(n):
    return f"{n / 1000:.1f}k" if n >= 10000 else f"{n:,}".replace(",", " ")


def render(s, theme, updated):
    t = THEMES[theme]
    W, H = 900, 360
    level, pct = rank(s)
    out = []
    add = out.append
    add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
        f'aria-label="GitHub statistics for {USER}: {s["stars"]} stars, {s["commits"]} commits last year, rank {level}">')
    add(f'<defs><pattern id="g" width="16" height="16" patternUnits="userSpaceOnUse">'
        f'<path d="M16 0H0V16" fill="none" stroke="{t["grid"]}" stroke-width="1"/></pattern></defs>')
    add(f'<rect width="{W}" height="{H}" fill="{t["paper"]}"/><rect width="{W}" height="{H}" fill="url(#g)"/>')
    add(f'<rect x="8" y="8" width="{W-16}" height="{H-16}" fill="none" stroke="{t["ink"]}" stroke-width="1.5"/>')
    # header strip
    add(f'<line x1="8" y1="34" x2="{W-8}" y2="34" stroke="{t["ink"]}" stroke-width="1"/>')
    add(f'<text x="24" y="26" font-family="{MONO}" font-size="11" fill="{t["ink2"]}" letter-spacing="0.6">SHEET 2 | GITHUB STATISTICS</text>')
    add(f'<text x="{W-24}" y="26" text-anchor="end" font-family="{MONO}" font-size="11" fill="{t["ink2"]}">REV {escape(updated)}</text>')

    # column 1: stats table
    x0, y0 = 24, 62
    rows = [("Stars earned", s["stars"]), ("Commits, last 12 months", s["commits"]), ("Pull requests", s["prs"]),
            ("Issues", s["issues"]), ("Followers", s["followers"]), ("Public repositories", s["repos"])]
    for i, (label, val) in enumerate(rows):
        y = y0 + i * 30
        add(f'<text x="{x0}" y="{y}" font-family="{MONO}" font-size="12.5" fill="{t["ink2"]}">{escape(label)}</text>')
        add(f'<text x="{x0+282}" y="{y}" text-anchor="end" font-family="{MONO}" font-size="13" font-weight="500" fill="{t["ink"]}">{fmt(val)}</text>')
        add(f'<line x1="{x0}" y1="{y+10}" x2="{x0+282}" y2="{y+10}" stroke="{t["rule"]}" stroke-width="1"/>')

    # column 2: rank
    cx, cy = 400, 128
    add(f'<line x1="330" y1="34" x2="330" y2="{H-124}" stroke="{t["ink"]}" stroke-width="1"/>')
    add(f'<line x1="470" y1="34" x2="470" y2="{H-124}" stroke="{t["ink"]}" stroke-width="1"/>')
    add(f'<text x="{cx}" y="58" text-anchor="middle" font-family="{MONO}" font-size="10" fill="{t["ink2"]}" letter-spacing="0.8">RANK</text>')
    add(f'<text x="{cx}" y="{cy+22}" text-anchor="middle" font-family="{DISPLAY}" font-size="{60 if len(level) == 1 else 50}" font-weight="700" fill="{t["ink"]}">{escape(level)}</text>')
    add(f'<ellipse cx="{cx+2}" cy="{cy+2}" rx="44" ry="38" transform="rotate(-8 {cx} {cy})" fill="none" stroke="{t["red"]}" stroke-width="2.2"/>')
    add(f'<text x="{cx}" y="{cy+70}" text-anchor="middle" font-family="{MONO}" font-size="11" fill="{t["ink2"]}">top {pct:.0f}%</text>')

    # column 3: languages
    lx, lw = 494, W - 24 - 494
    langs = sorted(((k, v) for k, v in s["languages"].items() if k not in EXCLUDE_LANGS), key=lambda kv: -kv[1])
    total = sum(v for _, v in langs) or 1
    top = langs[:6]
    add(f'<text x="{lx}" y="58" font-family="{MONO}" font-size="10" fill="{t["ink2"]}" letter-spacing="0.8">LANGUAGES, BY BYTES OF CODE</text>')
    bx = lx
    for i, (name, size) in enumerate(top):
        w = lw * size / total
        color = t["red"] if i == 0 else t["ramp"][min(i, 5)]
        add(f'<rect x="{bx:.1f}" y="70" width="{max(w, 1.5):.1f}" height="10" fill="{color}"/>')
        bx += w
    if bx < lx + lw:
        add(f'<rect x="{bx:.1f}" y="70" width="{lx + lw - bx:.1f}" height="10" fill="{t["cell0"]}"/>')
    for i, (name, size) in enumerate(top):
        col, row = i % 2, i // 2
        x = lx + col * (lw / 2)
        y = 108 + row * 28
        color = t["red"] if i == 0 else t["ramp"][min(i, 5)]
        add(f'<rect x="{x:.1f}" y="{y-9}" width="9" height="9" fill="{color}"/>')
        add(f'<text x="{x+16:.1f}" y="{y}" font-family="{MONO}" font-size="12.5" fill="{t["ink"]}">{escape(name)}</text>')
        add(f'<text x="{x + lw/2 - 16:.1f}" y="{y}" text-anchor="end" font-family="{MONO}" font-size="12" fill="{t["ink2"]}">{100*size/total:.1f}%</text>')

    # bottom: contribution strip
    add(f'<line x1="8" y1="{H-124}" x2="{W-8}" y2="{H-124}" stroke="{t["ink"]}" stroke-width="1"/>')
    add(f'<text x="24" y="{H-104}" font-family="{MONO}" font-size="10" fill="{t["ink2"]}" letter-spacing="0.8">CONTRIBUTIONS, LAST 12 MONTHS</text>')
    add(f'<text x="{W-24}" y="{H-104}" text-anchor="end" font-family="{MONO}" font-size="12" font-weight="500" fill="{t["ink"]}">{fmt(s["contributions"])}</text>')
    days = s["days"][-364:]
    weeks = [days[i:i + 7] for i in range(0, len(days), 7)]
    mx = max(days) if days else 1
    cw = (W - 48) / max(len(weeks), 1)
    size = min(cw - 3, 10)
    for wi, wk in enumerate(weeks):
        for di, c in enumerate(wk):
            x = 24 + wi * cw
            y = H - 94 + di * (size + 2)
            if c == 0:
                add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{size:.1f}" height="{size:.1f}" fill="{t["cell0"]}"/>')
            else:
                op = 0.25 + 0.75 * math.sqrt(c / mx)
                add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{size:.1f}" height="{size:.1f}" fill="{t["ink"]}" fill-opacity="{op:.2f}"/>')
    add("</svg>")
    return "\n".join(out)


def main():
    if "--fixture" in sys.argv:
        with open(sys.argv[sys.argv.index("--fixture") + 1]) as f:
            s = json.load(f)
    else:
        token = os.environ.get("GH_TOKEN")
        if not token:
            raise SystemExit("Set GH_TOKEN")
        s = fetch(token)
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    os.makedirs(OUT, exist_ok=True)
    for theme in THEMES:
        with open(os.path.join(OUT, f"stats-{theme}.svg"), "w") as f:
            f.write(render(s, theme, updated))
    level, pct = rank(s)
    print(f"stars={s['stars']} commits={s['commits']} prs={s['prs']} rank={level} (top {pct:.1f}%) langs={len(s['languages'])}")


if __name__ == "__main__":
    main()
