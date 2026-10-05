#!/usr/bin/env python3
"""Generate self-hosted GitHub activity SVGs for the profile README.

Normal mode reads GitHub's official GraphQL contribution calendar and REST API.
Set PROFILE_TOKEN to a classic PAT with only the `read:user` scope. The GitHub
Actions workflow uses its built-in GITHUB_TOKEN for the commit/push permission.

`--bootstrap-html` exists only to seed the first committed snapshot when the
profile is being assembled locally. It reads the public contribution-calendar
HTML once; scheduled refreshes must use the authenticated GraphQL API.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USERNAME = "marufhossen-in"
API_ROOT = "https://api.github.com"
GRAPHQL_URL = "https://api.github.com/graphql"
USER_AGENT = "marufhossen-in-profile-assets/1.0"
ASSET_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")

COLORS = ["#111923", "#17345B", "#205AA4", "#2D88DB", "#62D3FF"]


def request_json(url: str, token: str | None, method: str = "GET", payload: dict[str, Any] | None = None) -> tuple[Any, dict[str, str]]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": USER_AGENT,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8")), {k.lower(): v for k, v in response.headers.items()}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"GitHub returned HTTP {exc.code} for {url}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach GitHub API: {exc.reason}") from exc


class PublicCalendarParser(HTMLParser):
    """Parse GitHub's public profile calendar to seed the initial local snapshot."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.total_text: list[str] = []
        self.in_total = False
        self.tooltip_for: str | None = None
        self.tooltip_text: list[str] = []
        self.in_tooltip = False
        self.days_by_id: dict[str, dict[str, Any]] = {}
        self.days: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {key: (value or "") for key, value in attrs}
        if tag == "h2" and attrs_map.get("id") == "js-contribution-activity-description":
            self.in_total = True
            self.total_text = []
        if tag == "td" and "ContributionCalendar-day" in attrs_map.get("class", "").split():
            day_id = attrs_map.get("id")
            day_date = attrs_map.get("data-date")
            if day_id and day_date:
                item = {
                    "date": day_date,
                    "count": 0,
                    "level": int(attrs_map.get("data-level", "0") or 0),
                }
                self.days_by_id[day_id] = item
                self.days.append(item)
        if tag == "tool-tip" and attrs_map.get("for") in self.days_by_id:
            self.tooltip_for = attrs_map["for"]
            self.tooltip_text = []
            self.in_tooltip = True

    def handle_data(self, data: str) -> None:
        if self.in_total:
            self.total_text.append(data)
        if self.in_tooltip:
            self.tooltip_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "h2" and self.in_total:
            self.in_total = False
        if tag == "tool-tip" and self.in_tooltip:
            text = " ".join(" ".join(self.tooltip_text).split())
            match = re.match(r"([\d,]+)\s+contributions?\b", text, flags=re.IGNORECASE)
            count = int(match.group(1).replace(",", "")) if match else 0
            if self.tooltip_for in self.days_by_id:
                item = self.days_by_id[self.tooltip_for]
                item["count"] = count
                if count > 0 and item["level"] == 0:
                    item["level"] = 1
            self.tooltip_for = None
            self.tooltip_text = []
            self.in_tooltip = False

    def total(self) -> int:
        match = re.search(r"([\d,]+)\s+contributions?\s+in the last year", " ".join(self.total_text), flags=re.IGNORECASE)
        if not match:
            raise RuntimeError("Could not read the total from GitHub's public contribution calendar.")
        return int(match.group(1).replace(",", ""))


def fetch_public_calendar_html() -> dict[str, Any]:
    url = f"https://github.com/users/{USERNAME}/contributions"
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    try:
        with urlopen(request, timeout=30) as response:
            page = response.read().decode("utf-8", "replace")
    except (HTTPError, URLError) as exc:
        raise RuntimeError(f"Could not fetch GitHub's public contribution calendar: {exc}") from exc
    parser = PublicCalendarParser()
    parser.feed(page)
    if not parser.days:
        raise RuntimeError("No contribution days were found in GitHub's public calendar HTML.")
    return {"total": parser.total(), "days": parser.days}


def fetch_graphql_calendar(token: str) -> dict[str, Any]:
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                contributionCount
                contributionLevel
              }
            }
          }
        }
      }
    }
    """
    data, _ = request_json(GRAPHQL_URL, token, "POST", {"query": query, "variables": {"login": USERNAME}})
    if data.get("errors"):
        message = "; ".join(error.get("message", "GraphQL query failed") for error in data["errors"])
        raise RuntimeError(f"GitHub GraphQL error: {message}")
    user = (data.get("data") or {}).get("user")
    calendar = ((user or {}).get("contributionsCollection") or {}).get("contributionCalendar")
    if not calendar:
        raise RuntimeError(f"GitHub returned no contribution calendar for {USERNAME}.")
    level_map = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}
    days = []
    for week in calendar.get("weeks", []):
        for item in week.get("contributionDays", []):
            days.append({
                "date": item["date"][:10],
                "count": int(item.get("contributionCount", 0)),
                "level": level_map.get(item.get("contributionLevel", "NONE"), 0),
            })
    if not days:
        raise RuntimeError("GitHub returned an empty contribution calendar.")
    return {"total": int(calendar.get("totalContributions", 0)), "days": days}


def fetch_profile_and_repositories(token: str | None) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, int]]:
    profile, _ = request_json(f"{API_ROOT}/users/{USERNAME}", token)
    repos: list[dict[str, Any]] = []
    page = 1
    while True:
        url = f"{API_ROOT}/users/{USERNAME}/repos?{urlencode({'type': 'owner', 'per_page': 100, 'page': page, 'sort': 'updated'})}"
        batch, _ = request_json(url, token)
        if not isinstance(batch, list):
            raise RuntimeError("Unexpected response while listing public repositories.")
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    language_bytes: dict[str, int] = {}
    owned_public = [repo for repo in repos if not repo.get("private", False) and not repo.get("fork", False)]
    for repo in owned_public:
        languages_url = repo.get("languages_url")
        if not languages_url:
            continue
        languages, _ = request_json(languages_url, token)
        if isinstance(languages, dict):
            for name, size in languages.items():
                language_bytes[name] = language_bytes.get(name, 0) + int(size or 0)
    return profile, repos, language_bytes


def calendar_streaks(calendar: dict[str, Any]) -> tuple[int, int]:
    daily = {}
    for day in calendar["days"]:
        daily[dt.date.fromisoformat(day["date"][:10])] = int(day.get("count", 0))
    if not daily:
        return 0, 0
    ordered = sorted(daily)
    best = 0
    run = 0
    previous: dt.date | None = None
    for day in ordered:
        if daily[day] > 0:
            run = run + 1 if previous is not None and day == previous + dt.timedelta(days=1) else 1
            best = max(best, run)
        else:
            run = 0
        previous = day

    today = dt.datetime.now(dt.timezone.utc).date()
    end = min(today, ordered[-1])
    if end in daily and daily[end] == 0:
        end -= dt.timedelta(days=1)
    current = 0
    while end in daily and daily[end] > 0:
        current += 1
        end -= dt.timedelta(days=1)
    return current, best


def _text(x: Any) -> str:
    return html.escape(str(x), quote=True)


def _write(path: str, data: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(data)


def generate_contribution_svg(calendar: dict[str, Any], generated: dt.date) -> str:
    days = sorted(calendar["days"], key=lambda item: item["date"])
    dates = [dt.date.fromisoformat(item["date"][:10]) for item in days]
    first = dates[0]
    start_sunday = first - dt.timedelta(days=(first.weekday() + 1) % 7)
    last = dates[-1]
    columns = ((last - start_sunday).days // 7) + 1
    width, height = 1000, 254
    left, top, cell, gap = 104, 94, 11, 5
    step = cell + gap
    day_map = {dt.date.fromisoformat(item["date"][:10]): item for item in days}

    month_labels: list[str] = [f'<text x="{left}" y="78" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="12" fill="#8997AA">{_text(first.strftime("%b"))}</text>']
    seen_months: set[tuple[int, int]] = {(first.year, first.month)}
    for week in range(columns):
        sunday = start_sunday + dt.timedelta(days=7 * week)
        candidates = [sunday + dt.timedelta(days=offset) for offset in range(7)]
        month_day = next((day for day in candidates if day.day == 1 and day in day_map), None)
        if month_day:
            key = (month_day.year, month_day.month)
            if key not in seen_months:
                month_labels.append(f'<text x="{left + week * step}" y="78" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="12" fill="#8997AA">{_text(month_day.strftime("%b"))}</text>')
                seen_months.add(key)

    rects: list[str] = []
    for day_date, item in day_map.items():
        column = (day_date - start_sunday).days // 7
        row = (day_date.weekday() + 1) % 7  # GitHub-style Sunday-first rows.
        level = max(0, min(4, int(item.get("level", 0))))
        x = left + column * step
        y = top + row * step
        count = int(item.get("count", 0))
        title = f'{count} contribution{"s" if count != 1 else ""} on {day_date.isoformat()}'
        rects.append(
            f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="3" fill="{COLORS[level]}" stroke="#223248" stroke-width="0.35"><title>{_text(title)}</title></rect>'
        )

    row_labels = []
    for label, row in [("Mon", 1), ("Wed", 3), ("Fri", 5)]:
        row_labels.append(f'<text x="59" y="{top + row * step + 9}" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="11" fill="#748196" text-anchor="end">{label}</text>')

    legend = []
    legend.append(f'<text x="{left}" y="225" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="11" fill="#748196">Less</text>')
    for index in range(5):
        legend.append(f'<rect x="{left + 39 + index * 16}" y="214" width="11" height="11" rx="3" fill="{COLORS[index]}" stroke="#223248" stroke-width="0.35"/>')
    legend.append(f'<text x="{left + 127}" y="225" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="11" fill="#748196">More</text>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">GitHub contributions for Md. Maruf Hossen</title>
<desc id="desc">A GitHub-style heatmap of the last 12 months, based on the real contribution calendar. Total contributions: {int(calendar['total'])}.</desc>
<defs><linearGradient id="panel" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0d1520"/><stop offset="1" stop-color="#080d14"/></linearGradient></defs>

<rect x="1" y="1" width="998" height="252" rx="16" fill="url(#panel)" stroke="#203047"/>
<path d="M30 49H970" stroke="#1b2839"/>
<text x="32" y="34" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="21" font-weight="600" fill="#F4F7FB" letter-spacing=".04em">CONTRIBUTION CALENDAR</text>
<text x="32" y="67" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="13" fill="#91A0B3">{int(calendar['total'])} contributions · last 12 months</text>
<text x="968" y="34" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="13" fill="#91A0B3" text-anchor="end">UPDATED {_text(generated.strftime('%d %b %Y').upper())}</text>
{''.join(month_labels)}
{''.join(row_labels)}
{''.join(rects)}
{''.join(legend)}
</svg>'''


def generate_stats_svg(profile: dict[str, Any], repos: list[dict[str, Any]], calendar: dict[str, Any], current_streak: int, best_streak: int, generated: dt.date) -> str:
    public_repos = int(profile.get("public_repos", sum(not repo.get("private", False) for repo in repos)))
    followers = int(profile.get("followers", 0))
    public_owned = [repo for repo in repos if not repo.get("private", False) and not repo.get("fork", False)]
    stars = sum(int(repo.get("stargazers_count", 0)) for repo in public_owned)
    items = [
        ("PUBLIC REPOSITORIES", f"{public_repos}", "#3b82f6"),
        ("FOLLOWERS", f"{followers}", "#54c7ec"),
        ("REPOSITORY STARS · NON-FORKS", f"{stars}", "#9b8cff"),
        ("CONTRIBUTIONS · LAST 12 MONTHS", f"{int(calendar['total'])}", "#58d5ba"),
        ("CURRENT STREAK", f"{current_streak} days", "#57c8ff"),
        ("BEST STREAK · LAST 12 MONTHS", f"{best_streak} days", "#a4b8ff"),
    ]
    width, height = 900, 464
    card_w, card_h = 410, 104
    x_positions = [28, 462]
    y_positions = [74, 198, 322]
    cards = []
    for index, (label, value, accent) in enumerate(items):
        col, row = index % 2, index // 2
        x, y = x_positions[col], y_positions[row]
        cards.append(f'''<g>
<rect x="{x}" y="{y}" width="{card_w}" height="{card_h}" rx="14" fill="#0d1520" stroke="#213149"/>
<rect x="{x}" y="{y + 18}" width="3" height="68" rx="2" fill="{accent}"/>
<text x="{x + 22}" y="{y + 36}" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="13" font-weight="600" fill="#91A0B3" letter-spacing=".05em">{_text(label)}</text>
<text x="{x + 22}" y="{y + 76}" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="31" font-weight="700" fill="#F4F7FB">{_text(value)}</text>
</g>''')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">GitHub profile statistics for Md. Maruf Hossen</title>
<desc id="desc">Public repositories: {public_repos}; followers: {followers}; stars on non-fork public repositories: {stars}; contributions in the last year: {int(calendar['total'])}; current streak: {current_streak} days; best streak in the last year: {best_streak} days.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0d1520"/><stop offset="1" stop-color="#080d14"/></linearGradient></defs>

<rect x="1" y="1" width="898" height="462" rx="16" fill="url(#bg)" stroke="#203047"/>
<text x="30" y="38" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="21" font-weight="600" fill="#F4F7FB" letter-spacing=".04em">PROFILE SNAPSHOT</text>
<text x="870" y="38" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="13" fill="#91A0B3" text-anchor="end">UPDATED {_text(generated.strftime('%d %b %Y').upper())}</text>
{''.join(cards)}
</svg>'''


def generate_languages_svg(language_bytes: dict[str, int], generated: dt.date) -> str:
    width, height = 900, 346
    total = sum(language_bytes.values())
    ranked = sorted(language_bytes.items(), key=lambda pair: pair[1], reverse=True)
    top = ranked[:5]
    if len(ranked) > 5:
        top.append(("Other", sum(size for _, size in ranked[5:])))
    if not top:
        top = [("No language data yet", 0)]
    bar_x, bar_w = 268, 525
    colors = ["#38bdf8", "#4f83ff", "#9b8cff", "#39c7a5", "#f5c86b", "#6d7e96"]
    rows = []
    for index, (name, size) in enumerate(top):
        y = 96 + index * 39
        percent = (size / total * 100) if total else 0.0
        shown = max(3, bar_w * percent / 100) if size > 0 else 0
        percent_label = "<0.1%" if 0 < percent < 0.05 else f"{percent:.1f}%"
        accent = colors[index % len(colors)]
        rows.append(f'''<text x="34" y="{y + 5}" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="14" fill="#D6DEEA">{_text(name)}</text>
<rect x="{bar_x}" y="{y - 10}" width="{bar_w}" height="12" rx="6" fill="#182333"/>
<rect x="{bar_x}" y="{y - 10}" width="{shown:.1f}" height="12" rx="6" fill="{accent}"/>
<text x="856" y="{y + 5}" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="13" font-weight="600" fill="#9AA8BB" text-anchor="end">{_text(percent_label)}</text>''')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">Most-used programming languages in public repositories</title>
<desc id="desc">Language share based on GitHub's language-byte totals for non-fork public repositories. Top languages: {_text(', '.join(name for name, _ in top))}.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0d1520"/><stop offset="1" stop-color="#080d14"/></linearGradient></defs>

<rect x="1" y="1" width="898" height="344" rx="16" fill="url(#bg)" stroke="#203047"/>
<text x="30" y="38" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="21" font-weight="600" fill="#F4F7FB" letter-spacing=".04em">LANGUAGE MIX · PUBLIC REPOSITORIES</text>
<text x="870" y="38" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="13" fill="#91A0B3" text-anchor="end">UPDATED {_text(generated.strftime('%d %b %Y').upper())}</text>
{''.join(rows)}
<text x="34" y="324" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="13" fill="#91A0B3">GitHub language-byte totals · original public repositories only</text>
</svg>'''


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate local GitHub activity SVG assets.")
    parser.add_argument("--bootstrap-html", action="store_true", help="seed a first snapshot from the public GitHub profile HTML; do not use for scheduled updates")
    args = parser.parse_args()

    token = os.environ.get("PROFILE_TOKEN")
    if not args.bootstrap_html and not token:
        print("PROFILE_TOKEN is required for scheduled updates (classic PAT with read:user scope).", file=sys.stderr)
        return 2

    try:
        calendar = fetch_public_calendar_html() if args.bootstrap_html else fetch_graphql_calendar(token or "")
        profile, repos, languages = fetch_profile_and_repositories(token)
        current_streak, best_streak = calendar_streaks(calendar)
        generated = dt.datetime.now(dt.timezone.utc).date()

        _write(os.path.join(ASSET_DIR, "contributions.svg"), generate_contribution_svg(calendar, generated))
        _write(os.path.join(ASSET_DIR, "profile-stats.svg"), generate_stats_svg(profile, repos, calendar, current_streak, best_streak, generated))
        _write(os.path.join(ASSET_DIR, "languages.svg"), generate_languages_svg(languages, generated))

        # Safe to log only public aggregate values; never print the token.
        print(f"Updated GitHub profile SVGs for {USERNAME}: {calendar['total']} contributions in the last year; {profile.get('public_repos', 0)} public repositories.")
        print("Wrote assets/contributions.svg, assets/profile-stats.svg, and assets/languages.svg")
        return 0
    except (RuntimeError, KeyError, ValueError, TypeError) as exc:
        print(f"Profile asset generation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
