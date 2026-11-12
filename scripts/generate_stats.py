"""Generate a self-hosted GitHub stats card (SVG) for the profile README.

Runs inside GitHub Actions with the built-in GITHUB_TOKEN, so no third-party
stats service is needed. Usage:

    python scripts/generate_stats.py <username> <output.svg>
    python scripts/generate_stats.py --mock <output.svg>   # local preview
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from xml.sax.saxutils import escape

API_URL = "https://api.github.com/graphql"

QUERY = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, first: 100) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 10, orderBy: { field: SIZE, direction: DESC }) {
          edges { size node { name color } }
        }
      }
    }
    contributionsCollection {
      totalCommitContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""

FONT = "'Segoe UI', Inter, -apple-system, BlinkMacSystemFont, Roboto, Helvetica, Arial, sans-serif"
IGNORED_LANGUAGES = {"Jupyter Notebook"}


def fetch(login: str) -> dict:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is not set")
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    request = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": f"{login}-profile-stats",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("errors"):
        sys.exit(f"GitHub API error: {payload['errors']}")
    return payload["data"]["user"]


def mock() -> dict:
    import random

    random.seed(7)
    start = date.today() - timedelta(days=364)
    days = [
        {"date": (start + timedelta(days=i)).isoformat(),
         "contributionCount": random.choice([0, 0, 0, 1, 2, 4, 7]) if i > 280 else random.choice([0, 0, 0, 0, 1])}
        for i in range(365)
    ]
    weeks = [{"contributionDays": days[i:i + 7]} for i in range(0, 365, 7)]
    langs = lambda *pairs: {"edges": [{"size": s, "node": {"name": n, "color": c}} for n, c, s in pairs]}
    return {
        "followers": {"totalCount": 3},
        "repositories": {
            "totalCount": 26,
            "nodes": [
                {"stargazerCount": 2, "languages": langs(("TypeScript", "#3178c6", 90000), ("CSS", "#663399", 8000))},
                {"stargazerCount": 1, "languages": langs(("HTML", "#e34c26", 60000), ("CSS", "#663399", 30000), ("JavaScript", "#f1e05a", 20000))},
                {"stargazerCount": 0, "languages": langs(("Dart", "#00B4AB", 40000))},
                {"stargazerCount": 0, "languages": langs(("Python", "#3572A5", 15000))},
            ],
        },
        "contributionsCollection": {
            "totalCommitContributions": 221,
            "contributionCalendar": {"totalContributions": 273, "weeks": weeks},
        },
    }


def streaks(days: list[dict]) -> tuple[int, int]:
    counts = [d["contributionCount"] for d in sorted(days, key=lambda d: d["date"])]
    longest = run = 0
    for c in counts:
        run = run + 1 if c > 0 else 0
        longest = max(longest, run)
    # Current streak: a quiet "today" does not break it yet.
    current = 0
    tail = counts[:-1] if counts and counts[-1] == 0 else counts
    for c in reversed(tail):
        if c == 0:
            break
        current += 1
    return current, longest


def top_languages(repos: list[dict], limit: int = 6) -> list[tuple[str, str, float]]:
    totals: dict[str, list] = {}
    for repo in repos:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            if name in IGNORED_LANGUAGES:
                continue
            entry = totals.setdefault(name, [edge["node"]["color"] or "#8b949e", 0])
            entry[1] += edge["size"]
    total = sum(v[1] for v in totals.values()) or 1
    ranked = sorted(totals.items(), key=lambda kv: kv[1][1], reverse=True)[:limit]
    return [(name, color, size / total * 100) for name, (color, size) in ranked]


def fmt(n: int) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


def render(user: dict) -> str:
    calendar = user["contributionsCollection"]["contributionCalendar"]
    days = [d for week in calendar["weeks"] for d in week["contributionDays"]]
    current, longest = streaks(days)
    repos = user["repositories"]["nodes"]
    stars = sum(r["stargazerCount"] for r in repos)
    languages = top_languages(repos)

    tiles = [
        ("Contributions", fmt(calendar["totalContributions"]), "past 12 months", "#38bdf8"),
        ("Current streak", f"{current}d", "days in a row", "#a78bfa"),
        ("Longest streak", f"{longest}d", "past 12 months", "#f472b6"),
        ("Public repos", fmt(user["repositories"]["totalCount"]), f"{fmt(stars)} stars earned", "#34d399"),
    ]

    W, H = 1200, 360
    parts: list[str] = []

    # Stat tiles (2 x 2)
    tw, th, gap, x0, y0 = 250, 104, 16, 40, 110
    for i, (label, value, sub, color) in enumerate(tiles):
        x = x0 + (i % 2) * (tw + gap)
        y = y0 + (i // 2) * (th + gap)
        parts.append(
            f'<g class="rise" style="animation-delay:{0.1 + i * 0.12:.2f}s">'
            f'<rect x="{x}" y="{y}" width="{tw}" height="{th}" rx="14" fill="#0f172a" stroke="#1e293b"/>'
            f'<rect x="{x}" y="{y + 20}" width="3" height="{th - 40}" rx="1.5" fill="{color}"/>'
            f'<text x="{x + 22}" y="{y + 32}" class="t" font-size="12" font-weight="700" fill="#64748b" letter-spacing="1.4">{escape(label.upper())}</text>'
            f'<text x="{x + 22}" y="{y + 70}" class="t" font-size="34" font-weight="800" fill="#f8fafc">{escape(value)}</text>'
            f'<text x="{x + 22}" y="{y + 90}" class="t" font-size="12.5" fill="#94a3b8">{escape(sub)}</text>'
            f"</g>"
        )

    # Weekly activity area chart
    weekly = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in calendar["weeks"]]
    cx, cy, cw, ch = 596, 110, 564, 104
    peak = max(weekly) or 1
    step = cw / max(len(weekly) - 1, 1)
    pts = [(cx + i * step, cy + ch - (v / peak) * (ch - 10)) for i, v in enumerate(weekly)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{cx},{cy + ch} " + line + f" {cx + cw},{cy + ch}"
    parts.append(
        f'<text x="{cx}" y="{cy - 12}" class="t" font-size="12" font-weight="700" fill="#64748b" letter-spacing="1.4">WEEKLY ACTIVITY</text>'
        f'<line x1="{cx}" y1="{cy + ch}" x2="{cx + cw}" y2="{cy + ch}" stroke="#1e293b"/>'
        f'<polygon points="{area}" fill="url(#area)"/>'
        f'<polyline class="draw" points="{line}" fill="none" stroke="url(#ac)" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" pathLength="1"/>'
    )

    # Language bar + legend
    ly = 262
    parts.append(f'<text x="{cx}" y="{ly - 14}" class="t" font-size="12" font-weight="700" fill="#64748b" letter-spacing="1.4">TOP LANGUAGES</text>')
    parts.append(f'<clipPath id="bar"><rect x="{cx}" y="{ly}" width="{cw}" height="10" rx="5"/></clipPath><g clip-path="url(#bar)"><rect x="{cx}" y="{ly}" width="{cw}" height="10" fill="#1e293b"/>')
    bx = cx
    for name, color, pct in languages:
        w = cw * pct / sum(p for _, _, p in languages)
        parts.append(f'<rect x="{bx:.1f}" y="{ly}" width="{w:.1f}" height="10" fill="{color}"/>')
        bx += w
    parts.append("</g>")
    for i, (name, color, pct) in enumerate(languages):
        lx = cx + (i % 3) * 188
        lyy = ly + 38 + (i // 3) * 26
        parts.append(
            f'<circle cx="{lx + 6}" cy="{lyy - 4}" r="5" fill="{color}"/>'
            f'<text x="{lx + 18}" y="{lyy}" class="t" font-size="13.5" fill="#e2e8f0">{escape(name)} '
            f'<tspan fill="#64748b">{pct:.1f}%</tspan></text>'
        )

    updated = datetime.now(timezone.utc).strftime("%d %b %Y")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" xml:space="preserve" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="GitHub stats">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#070b14"/><stop offset="1" stop-color="#0c1528"/></linearGradient>
    <linearGradient id="ac" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#38bdf8"/><stop offset="0.5" stop-color="#6366f1"/><stop offset="1" stop-color="#a855f7"/></linearGradient>
    <linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#6366f1" stop-opacity="0.35"/><stop offset="1" stop-color="#6366f1" stop-opacity="0"/></linearGradient>
    <style>
      .t {{ font-family: {FONT}; }}
      .rise {{ animation: rise .7s ease-out both; }}
      .draw {{ stroke-dasharray: 1; stroke-dashoffset: 0; animation: draw 2.2s ease-out both; }}
      @keyframes rise {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: none; }} }}
      @keyframes draw {{ from {{ stroke-dashoffset: 1; }} to {{ stroke-dashoffset: 0; }} }}
    </style>
  </defs>
  <rect width="{W}" height="{H}" rx="18" fill="url(#bg)"/>
  <rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="18" fill="none" stroke="#1e293b"/>
  <rect x="40" y="40" width="4" height="40" rx="2" fill="url(#ac)"/>
  <text x="58" y="60" class="t" font-size="24" font-weight="800" fill="#f8fafc">GitHub Stats</text>
  <text x="58" y="82" class="t" font-size="14" fill="#94a3b8">Auto-updated daily from my public activity · last update {updated}</text>
  {"".join(parts)}
</svg>
"""


def main() -> None:
    args = sys.argv[1:]
    if len(args) != 2:
        sys.exit(__doc__)
    user = mock() if args[0] == "--mock" else fetch(args[0])
    os.makedirs(os.path.dirname(os.path.abspath(args[1])), exist_ok=True)
    with open(args[1], "w", encoding="utf-8") as fh:
        fh.write(render(user))
    print(f"Wrote {args[1]}")


if __name__ == "__main__":
    main()
