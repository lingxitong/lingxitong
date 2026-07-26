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

# Tsinghua purple palette
PURPLE = "#660874"
PURPLE_MID = "#82318E"
PURPLE_SOFT = "#9B59B6"
PURPLE_PALE = "#EDE0F5"
PURPLE_INK = "#3D0A4A"
PURPLE_MUTED = "#6B4E78"


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


def count_up_steps(final: int, steps: int = 7) -> list[int]:
    if final <= 0:
        return [0]
    values = [int(final * i / steps) for i in range(1, steps)]
    values.append(final)
    # keep order, drop duplicates while preserving last
    out: list[int] = []
    for v in values:
        if not out or v != out[-1]:
            out.append(v)
    return out


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
        ("Total Forks", total_forks, "#82318E"),
        ("Public Repos", public_repos, "#660874"),
        ("Followers", followers, "#C084FC"),
        ("Pull Requests", prs, "#9B59B6"),
        ("Issues", issues, "#B57EDC"),
    ]
    row_h = 30
    width = 460
    hero_h = 96
    height = 44 + hero_h + len(rows) * row_h + 20
    max_side = max((v for _, v, _ in rows), default=1) or 1
    star_steps = count_up_steps(total_stars, steps=8)
    step_dur = 0.16
    star_settle = len(star_steps) * step_dur

    # Rolling number frames for Total Stars (opacity handoff).
    star_frames = []
    for idx, value in enumerate(star_steps):
        start = idx * step_dur
        if idx < len(star_steps) - 1:
            star_frames.append(
                f'<text class="hero-num roll" x="118" y="88" text-anchor="start" opacity="0">'
                f"{escape(compact(value))}"
                f'<animate attributeName="opacity" values="0;1;1;0" '
                f'keyTimes="0;0.15;0.85;1" dur="{step_dur:.2f}s" begin="{start:.2f}s" fill="remove"/>'
                f"</text>"
            )
        else:
            star_frames.append(
                f'<text class="hero-num" x="118" y="88" text-anchor="start" opacity="0">'
                f"{escape(compact(value))}"
                f'<animate attributeName="opacity" from="0" to="1" '
                f'dur="0.25s" begin="{start:.2f}s" fill="freeze"/>'
                f"</text>"
            )

    row_blocks = []
    for i, (label, value, color) in enumerate(rows):
        y = 44 + hero_h + 24 + i * row_h
        delay = star_settle + 0.12 + i * 0.12
        bw = bar_width(value, max_side, 150)
        row_blocks.append(
            f'<g class="row" style="animation-delay: {delay:.2f}s">'
            f'<circle cx="28" cy="{y - 4}" r="4" fill="{color}">'
            f'<animate attributeName="r" values="0;5;4" dur="0.45s" begin="{delay:.2f}s" fill="freeze"/>'
            f"</circle>"
            f'<text class="label" x="42" y="{y}">{escape(label)}</text>'
            f'<rect class="track" x="170" y="{y - 10}" width="150" height="7" rx="3.5"/>'
            f'<rect class="bar" x="170" y="{y - 10}" width="0" height="7" rx="3.5" fill="{color}">'
            f'<animate attributeName="width" from="0" to="{bw:.1f}" '
            f'dur="0.9s" begin="{delay:.2f}s" fill="freeze" '
            f'calcMode="spline" keySplines="0.22 1 0.36 1"/>'
            f"</rect>"
            f'<text class="value" x="{width - 22}" y="{y}" text-anchor="end" opacity="0">'
            f"{escape(compact(value))}"
            f'<animate attributeName="opacity" from="0" to="1" dur="0.35s" begin="{delay + 0.25:.2f}s" fill="freeze"/>'
            f"</text>"
            f"</g>"
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(USERNAME)} GitHub stats">
<defs>
  <linearGradient id="statsStroke" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0%" stop-color="{PURPLE}"/>
    <stop offset="100%" stop-color="{PURPLE_SOFT}"/>
  </linearGradient>
  <linearGradient id="heroFill" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0%" stop-color="#4A0A5C"/>
    <stop offset="55%" stop-color="{PURPLE}"/>
    <stop offset="100%" stop-color="#B8860B"/>
  </linearGradient>
  <filter id="softGlow" x="-40%" y="-40%" width="180%" height="180%">
    <feGaussianBlur stdDeviation="2.2" result="b"/>
    <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
</defs>
<style>
  .title {{ font: 600 15px 'Segoe UI', Ubuntu, Sans-Serif; fill: {PURPLE}; }}
  .label {{ font: 600 12px 'Segoe UI', Ubuntu, Sans-Serif; fill: {PURPLE_MUTED}; }}
  .value {{ font: 700 12px 'Segoe UI', Ubuntu, Sans-Serif; fill: {PURPLE_INK}; }}
  .hero-label {{ font: 600 12px 'Segoe UI', Ubuntu, Sans-Serif; fill: #F3E8FF; }}
  .hero-num {{ font: 800 34px 'Segoe UI', Ubuntu, Sans-Serif; fill: #FFE08A; }}
  .hero-sub {{ font: 600 11px 'Segoe UI', Ubuntu, Sans-Serif; fill: #EDE0F5; }}
  .card {{ fill: #FCF8FF; stroke: url(#statsStroke); }}
  .track {{ fill: {PURPLE_PALE}; }}
  .row {{ opacity: 0; animation: rowIn 0.55s ease forwards; }}
  .star {{ transform-origin: 48px 70px; animation: starPulse 1.6s ease-in-out infinite; }}
  @keyframes rowIn {{
    from {{ opacity: 0; transform: translateX(-8px); }}
    to {{ opacity: 1; transform: translateX(0); }}
  }}
  @keyframes starPulse {{
    0%, 100% {{ transform: scale(1); }}
    50% {{ transform: scale(1.12); }}
  }}
  @keyframes sheen {{
    0% {{ transform: translateX(-120px); opacity: 0; }}
    35% {{ opacity: 0.35; }}
    100% {{ transform: translateX(420px); opacity: 0; }}
  }}
  .sheen {{ animation: sheen 2.8s ease-in-out infinite; }}
</style>
<rect class="card" x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="10"/>
<text class="title" x="18" y="28">{escape(USERNAME)}'s GitHub Stats</text>

<g transform="translate(14, 40)">
  <rect x="0" y="0" width="432" height="84" rx="12" fill="url(#heroFill)"/>
  <rect class="sheen" x="0" y="0" width="70" height="84" fill="#ffffff" opacity="0.18"/>
  <g class="star" filter="url(#softGlow)">
    <polygon points="48,18 53,36 72,36 57,48 63,66 48,54 33,66 39,48 24,36 43,36" fill="#FFD54A">
      <animate attributeName="opacity" values="0.85;1;0.85" dur="1.6s" repeatCount="indefinite"/>
    </polygon>
  </g>
  <text class="hero-label" x="118" y="28">Total Stars</text>
  {"".join(star_frames)}
  <text class="hero-sub" x="118" y="70">across public repositories</text>
  <circle cx="400" cy="42" r="18" fill="none" stroke="#FFE08A" stroke-width="3" stroke-linecap="round"
          stroke-dasharray="113" stroke-dashoffset="113">
    <animate attributeName="stroke-dashoffset" from="113" to="18" dur="1.4s" fill="freeze"
             calcMode="spline" keySplines="0.22 1 0.36 1"/>
  </circle>
</g>

{"".join(row_blocks)}
</svg>
"""


def render_langs_svg(lang_counts: list[tuple[str, int]], limit: int = 8) -> str:
    items = lang_counts[:limit]
    if not items:
        items = [("Unknown", 1)]

    total = sum(c for _, c in items) or 1
    width = 360
    row_h = 26
    height = 52 + len(items) * row_h + 18
    palette = [
        PURPLE,
        PURPLE_MID,
        PURPLE_SOFT,
        "#B57EDC",
        "#C084FC",
        "#D8B4FE",
        "#A855F7",
        "#7E22CE",
    ]

    max_count = max(c for _, c in items)
    blocks = []
    for i, (lang, count) in enumerate(items):
        y = 54 + i * row_h
        color = palette[i % len(palette)]
        pct = 100.0 * count / total
        bw = bar_width(count, max_count, 160)
        delay = 0.15 + i * 0.14
        blocks.append(
            f'<g class="lang-row" style="animation-delay:{delay:.2f}s">'
            f'<text class="label" x="20" y="{y}">{escape(lang)}</text>'
            f'<rect class="track" x="130" y="{y - 10}" width="160" height="8" rx="4"/>'
            f'<rect x="130" y="{y - 10}" width="0" height="8" rx="4" fill="{color}">'
            f'<animate attributeName="width" from="0" to="{bw:.1f}" dur="1s" begin="{delay:.2f}s" '
            f'fill="freeze" calcMode="spline" keySplines="0.22 1 0.36 1"/>'
            f"</rect>"
            f'<text class="pct" x="{width - 20}" y="{y}" text-anchor="end" opacity="0">'
            f"{pct:.1f}%"
            f'<animate attributeName="opacity" from="0" to="1" dur="0.35s" begin="{delay + 0.35:.2f}s" fill="freeze"/>'
            f"</text>"
            f"</g>"
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Top Languages">
<defs>
  <linearGradient id="langStroke" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0%" stop-color="{PURPLE}"/>
    <stop offset="100%" stop-color="{PURPLE_SOFT}"/>
  </linearGradient>
</defs>
<style>
  .title {{ font: 600 16px 'Segoe UI', Ubuntu, Sans-Serif; fill: {PURPLE}; }}
  .label {{ font: 600 12px 'Segoe UI', Ubuntu, Sans-Serif; fill: {PURPLE_MUTED}; }}
  .pct {{ font: 600 12px 'Segoe UI', Ubuntu, Sans-Serif; fill: {PURPLE_INK}; }}
  .track {{ fill: {PURPLE_PALE}; }}
  .card {{ fill: #FCF8FF; stroke: url(#langStroke); }}
  .lang-row {{ opacity: 0; animation: fadeUp 0.5s ease forwards; }}
  @keyframes fadeUp {{
    from {{ opacity: 0; transform: translateY(6px); }}
    to {{ opacity: 1; transform: translateY(0); }}
  }}
</style>
<rect class="card" x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="8"/>
<text class="title" x="20" y="30">Most Used Languages</text>
{"".join(blocks)}
</svg>
"""


def render_repo_card(repo: dict[str, Any]) -> str:
    name = repo.get("name") or "repository"
    desc_lines = wrap_text(repo.get("description") or "", width=46, max_lines=2)
    language = repo.get("language") or "Markdown"
    stars = int(repo.get("stargazers_count") or 0)
    forks = int(repo.get("forks_count") or 0)
    width, height = 400, 118

    desc_svg = "".join(
        f'<text class="desc" x="18" y="{54 + i * 16}">{escape(line)}</text>'
        for i, line in enumerate(desc_lines)
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(name)}">
<defs>
  <linearGradient id="pinStroke" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0%" stop-color="{PURPLE}"/>
    <stop offset="100%" stop-color="{PURPLE_SOFT}"/>
  </linearGradient>
</defs>
<style>
  .name {{ font: 700 15px 'Segoe UI', Ubuntu, Sans-Serif; fill: {PURPLE}; }}
  .desc {{ font: 400 12px 'Segoe UI', Ubuntu, Sans-Serif; fill: {PURPLE_MUTED}; }}
  .meta {{ font: 600 12px 'Segoe UI', Ubuntu, Sans-Serif; fill: {PURPLE_INK}; }}
  .star-meta {{ font: 700 12px 'Segoe UI', Ubuntu, Sans-Serif; fill: #B8860B; }}
  .card {{ fill: #FCF8FF; stroke: url(#pinStroke); }}
  .card-body {{ animation: pinIn 0.7s ease both; }}
  .twinkle {{ animation: twinkle 1.4s ease-in-out infinite; transform-origin: 156px 96px; }}
  @keyframes pinIn {{
    from {{ opacity: 0; transform: translateY(8px); }}
    to {{ opacity: 1; transform: translateY(0); }}
  }}
  @keyframes twinkle {{
    0%, 100% {{ opacity: 0.75; transform: scale(1); }}
    50% {{ opacity: 1; transform: scale(1.15); }}
  }}
</style>
<g class="card-body">
  <rect class="card" x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="8"/>
  <text class="name" x="18" y="30">{escape(name)}</text>
  {desc_svg}
  <circle cx="24" cy="96" r="4" fill="{PURPLE_MID}"/>
  <text class="meta" x="34" y="100">{escape(language)}</text>
  <g class="twinkle">
    <text class="star-meta" x="150" y="100">★ {escape(compact(stars))}</text>
  </g>
  <text class="meta" x="230" y="100">fork {escape(compact(forks))}</text>
</g>
</svg>
"""


def render_about_card() -> str:
    """Identity card (replaces the old Python dict code block)."""
    width, height = 720, 230
    chips = [
        ("PhD Student", 18, 168, 118),
        ("Representation Learning", 148, 168, 188),
        ("AI4Healthcare", 348, 168, 128),
    ]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="About Xitong Ling">
<defs>
  <linearGradient id="aboutBg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0%" stop-color="#4A0A5C"/>
    <stop offset="45%" stop-color="{PURPLE}"/>
    <stop offset="100%" stop-color="{PURPLE_MID}"/>
  </linearGradient>
  <linearGradient id="aboutSheen" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0%" stop-color="#ffffff" stop-opacity="0.12"/>
    <stop offset="100%" stop-color="#ffffff" stop-opacity="0"/>
  </linearGradient>
</defs>
<style>
  .name {{ font: 700 28px 'Segoe UI', Ubuntu, Sans-Serif; fill: #ffffff; animation: fadeDown 0.7s ease both; }}
  .role {{ font: 600 14px 'Segoe UI', Ubuntu, Sans-Serif; fill: #F3E8FF; animation: fadeDown 0.7s ease both 0.1s; }}
  .row {{ font: 500 13px 'Segoe UI', Ubuntu, Sans-Serif; fill: #EDE0F5; animation: fadeDown 0.7s ease both 0.2s; }}
  .chip {{ font: 700 12px 'Segoe UI', Ubuntu, Sans-Serif; fill: {PURPLE_INK}; }}
  .orb {{ animation: float 4.5s ease-in-out infinite; }}
  .orb2 {{ animation: float 5.5s ease-in-out infinite reverse; }}
  .chip-g {{ opacity: 0; animation: chipIn 0.55s ease forwards; }}
  @keyframes fadeDown {{
    from {{ opacity: 0; transform: translateY(-8px); }}
    to {{ opacity: 1; transform: translateY(0); }}
  }}
  @keyframes float {{
    0%, 100% {{ transform: translateY(0); }}
    50% {{ transform: translateY(-10px); }}
  }}
  @keyframes chipIn {{
    from {{ opacity: 0; transform: translateY(8px); }}
    to {{ opacity: 1; transform: translateY(0); }}
  }}
  @keyframes sweep {{
    0% {{ transform: translateX(-180px); opacity: 0; }}
    30% {{ opacity: 0.25; }}
    100% {{ transform: translateX(760px); opacity: 0; }}
  }}
  .sweep {{ animation: sweep 3.2s ease-in-out infinite; }}
</style>
<rect x="0" y="0" width="{width}" height="{height}" rx="16" fill="url(#aboutBg)"/>
<rect class="sweep" x="0" y="0" width="120" height="{height}" fill="#ffffff" opacity="0.2"/>
<circle class="orb" cx="640" cy="36" r="70" fill="#ffffff" fill-opacity="0.06"/>
<circle class="orb2" cx="680" cy="180" r="90" fill="#ffffff" fill-opacity="0.05"/>
<text class="name" x="28" y="48">Xitong Ling</text>
<text class="role" x="28" y="76">PhD Student | Tsinghua University (SIGS)</text>
<text class="row" x="28" y="112">Beihang University  -&gt;  Tsinghua University</text>
<text class="row" x="28" y="134" style="animation-delay:0.28s">Homepage: lingxitong.github.io</text>
{"".join(
    f'<g class="chip-g" style="animation-delay:{0.35 + i * 0.12:.2f}s">'
    f'<rect x="{x}" y="{y}" width="{w}" height="28" rx="14" fill="#F8F0FF"/>'
    f'<text class="chip" x="{x + 14}" y="{y + 18}">{label}</text>'
    f"</g>"
    for i, (label, x, y, w) in enumerate(chips)
)}
</svg>
"""


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
    about_path = OUT_DIR / "about.svg"
    stats_path = OUT_DIR / "stats.svg"
    langs_path = OUT_DIR / "top-langs.svg"

    about_path.write_text(render_about_card(), encoding="utf-8")
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

    print(f"Wrote {about_path}")
    print(f"Wrote {stats_path} (stars={total_stars})")
    print(f"Wrote {langs_path} (langs={len(lang_counter)})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - surface clear CI failure
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
