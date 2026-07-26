#!/usr/bin/env python3
"""Generate profile README SVG cards from the public GitHub API.

Avoids third-party card hosts (often blocked / paused) and broken Action tokens
that write "Something went wrong" placeholders into the profile.
"""

from __future__ import annotations

import json
import os
import ssl
import sys
import textwrap
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

USERNAME = os.environ.get("GITHUB_USERNAME", "lingxitong")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
OUT_DIR = Path(os.environ.get("PROFILE_OUT_DIR", "profile"))
API = "https://api.github.com"

# Featured repos shown as pin-style cards (order preserved when found).
FEATURED_REPOS = [
    "MIL_BASELINE",
    "Awesome-AI4DigitalPathology",
    "CVPR-2025-WSI-Papers",
    "PFM_Segmentation",
]


def api_get(url: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{USERNAME}-profile-cards",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    req = urllib.request.Request(url, headers=headers)
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {exc.code} for {url}: {body[:300]}") from exc


def fetch_user() -> dict[str, Any]:
    return api_get(f"{API}/users/{USERNAME}")


def fetch_owned_repos() -> list[dict[str, Any]]:
    repos: list[dict[str, Any]] = []
    page = 1
    while page <= 20:
        batch = api_get(
            f"{API}/users/{USERNAME}/repos?per_page=100&page={page}"
            "&type=owner&sort=updated"
        )
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return [r for r in repos if not r.get("fork")]


def fetch_count(query: str) -> int:
    data = api_get(f"{API}/search/issues?q={urllib.request.quote(query)}&per_page=1")
    return int(data.get("total_count", 0))


def compact(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".rstrip("0").rstrip(".")
    if n >= 1_000:
        value = f"{n / 1_000:.1f}".rstrip("0").rstrip(".")
        return f"{value}k"
    return str(n)


def bar_width(value: int, maximum: int, max_width: float = 180.0) -> float:
    if maximum <= 0:
        return 0.0
    return max(4.0, max_width * value / maximum)


def wrap_text(text: str, width: int = 48, max_lines: int = 2) -> list[str]:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return ["No description provided."]
    lines = textwrap.wrap(cleaned, width=width) or ["No description provided."]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        if len(lines[-1]) > 3:
            lines[-1] = lines[-1][:-3].rstrip() + "..."
    return lines


def render_stats_svg(
    *,
    total_stars: int,
    total_forks: int,
    public_repos: int,
    followers: int,
    prs: int,
    issues: int,
) -> str:
    rows = [
        ("Total Stars", total_stars, "#ffcb2f"),
        ("Total Forks", total_forks, "#40c463"),
        ("Public Repos", public_repos, "#79c0ff"),
        ("Followers", followers, "#f778ba"),
        ("Pull Requests", prs, "#a371f7"),
        ("Issues", issues, "#ffa657"),
    ]
    row_h = 28
    height = 48 + len(rows) * row_h + 16
    width = 420

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{escape(USERNAME)} GitHub stats">',
        "<style>",
        "  .title { font: 600 16px 'Segoe UI', Ubuntu, Sans-Serif; fill: #2f81f7; }",
        "  .label { font: 600 13px 'Segoe UI', Ubuntu, Sans-Serif; fill: #57606a; }",
        "  .value { font: 700 13px 'Segoe UI', Ubuntu, Sans-Serif; fill: #24292f; }",
        "  .card { fill: #ffffff; stroke: #d0d7de; }",
        "</style>",
        f'<rect class="card" x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="8"/>',
        f'<text class="title" x="20" y="30">{escape(USERNAME)}\'s GitHub Stats</text>',
    ]

    for i, (label, value, color) in enumerate(rows):
        y = 58 + i * row_h
        lines.append(f'<circle cx="28" cy="{y - 4}" r="4" fill="{color}"/>')
        lines.append(f'<text class="label" x="42" y="{y}">{escape(label)}</text>')
        lines.append(
            f'<text class="value" x="{width - 24}" y="{y}" text-anchor="end">'
            f"{escape(compact(value))}</text>"
        )

    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def render_langs_svg(lang_counts: list[tuple[str, int]], limit: int = 8) -> str:
    items = lang_counts[:limit]
    if not items:
        items = [("Unknown", 1)]

    total = sum(c for _, c in items) or 1
    width = 360
    row_h = 26
    height = 52 + len(items) * row_h + 18
    palette = [
        "#2f81f7",
        "#3fb950",
        "#a371f7",
        "#f78166",
        "#d2a8ff",
        "#79c0ff",
        "#ffa657",
        "#ff7b72",
    ]

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="Top Languages">',
        "<style>",
        "  .title { font: 600 16px 'Segoe UI', Ubuntu, Sans-Serif; fill: #2f81f7; }",
        "  .label { font: 600 12px 'Segoe UI', Ubuntu, Sans-Serif; fill: #57606a; }",
        "  .pct { font: 600 12px 'Segoe UI', Ubuntu, Sans-Serif; fill: #24292f; }",
        "  .track { fill: #eaeef2; }",
        "  .card { fill: #ffffff; stroke: #d0d7de; }",
        "</style>",
        f'<rect class="card" x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="8"/>',
        '<text class="title" x="20" y="30">Most Used Languages</text>',
    ]

    max_count = max(c for _, c in items)
    for i, (lang, count) in enumerate(items):
        y = 54 + i * row_h
        color = palette[i % len(palette)]
        pct = 100.0 * count / total
        bw = bar_width(count, max_count, 160)
        lines.append(f'<text class="label" x="20" y="{y}">{escape(lang)}</text>')
        lines.append(f'<rect class="track" x="130" y="{y - 10}" width="160" height="8" rx="4"/>')
        lines.append(
            f'<rect x="130" y="{y - 10}" width="{bw:.1f}" height="8" rx="4" fill="{color}"/>'
        )
        lines.append(
            f'<text class="pct" x="{width - 20}" y="{y}" text-anchor="end">{pct:.1f}%</text>'
        )

    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def render_repo_card(repo: dict[str, Any]) -> str:
    name = repo.get("name") or "repository"
    desc_lines = wrap_text(repo.get("description") or "", width=46, max_lines=2)
    language = repo.get("language") or "Markdown"
    stars = int(repo.get("stargazers_count") or 0)
    forks = int(repo.get("forks_count") or 0)
    width, height = 400, 118

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(name)}">'
        ,
        "<style>",
        "  .name { font: 700 15px 'Segoe UI', Ubuntu, Sans-Serif; fill: #2f81f7; }",
        "  .desc { font: 400 12px 'Segoe UI', Ubuntu, Sans-Serif; fill: #57606a; }",
        "  .meta { font: 600 12px 'Segoe UI', Ubuntu, Sans-Serif; fill: #656d76; }",
        "  .card { fill: #ffffff; stroke: #d0d7de; }",
        "</style>",
        f'<rect class="card" x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="8"/>',
        f'<text class="name" x="18" y="30">{escape(name)}</text>',
    ]
    for i, line in enumerate(desc_lines):
        lines.append(f'<text class="desc" x="18" y="{54 + i * 16}">{escape(line)}</text>')

    meta_y = 100
    lines.append(f'<circle cx="24" cy="{meta_y - 4}" r="4" fill="#2f81f7"/>')
    lines.append(f'<text class="meta" x="34" y="{meta_y}">{escape(language)}</text>')
    lines.append(f'<text class="meta" x="150" y="{meta_y}">★ {escape(compact(stars))}</text>')
    lines.append(f'<text class="meta" x="230" y="{meta_y}">⑂ {escape(compact(forks))}</text>')
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def main() -> int:
    user = fetch_user()
    repos = fetch_owned_repos()
    by_name = {r.get("name"): r for r in repos}

    total_stars = sum(int(r.get("stargazers_count") or 0) for r in repos)
    total_forks = sum(int(r.get("forks_count") or 0) for r in repos)
    lang_counter: Counter[str] = Counter()
    for repo in repos:
        lang = repo.get("language")
        if lang:
            lang_counter[lang] += 1

    prs = fetch_count(f"author:{USERNAME} type:pr")
    issues = fetch_count(f"author:{USERNAME} type:issue")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stats_path = OUT_DIR / "stats.svg"
    langs_path = OUT_DIR / "top-langs.svg"

    stats_path.write_text(
        render_stats_svg(
            total_stars=total_stars,
            total_forks=total_forks,
            public_repos=int(user.get("public_repos") or len(repos)),
            followers=int(user.get("followers") or 0),
            prs=prs,
            issues=issues,
        ),
        encoding="utf-8",
    )
    langs_path.write_text(
        render_langs_svg(lang_counter.most_common(8)),
        encoding="utf-8",
    )

    featured = [by_name[name] for name in FEATURED_REPOS if name in by_name]
    if not featured:
        featured = sorted(
            repos, key=lambda r: int(r.get("stargazers_count") or 0), reverse=True
        )[:4]

    for repo in featured:
        path = OUT_DIR / f"pin-{repo['name']}.svg"
        path.write_text(render_repo_card(repo), encoding="utf-8")
        print(f"Wrote {path}")

    print(f"Wrote {stats_path} (stars={total_stars})")
    print(f"Wrote {langs_path} (langs={len(lang_counter)})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - surface clear CI failure
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
