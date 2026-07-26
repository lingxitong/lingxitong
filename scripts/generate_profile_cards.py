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


def fetch_language_bytes(repos: list[dict[str, Any]], top_n: int = 20) -> Counter[str]:
    """Byte-weighted languages from top starred repos (richer than primary-language only)."""
    ranked = sorted(
        repos, key=lambda r: int(r.get("stargazers_count") or 0), reverse=True
    )[:top_n]
    counter: Counter[str] = Counter()
    for repo in ranked:
        full = repo.get("full_name")
        if not full:
            continue
        try:
            data = api_get(f"{API}/repos/{full}/languages")
        except RuntimeError:
            continue
        if isinstance(data, dict):
            for lang, bytes_count in data.items():
                counter[lang] += int(bytes_count or 0)
    return counter


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
    """Dark neon dashboard — looks flashy even before animations finish."""
    width, height = 520, 300
    tiles = [
        ("Forks", total_forks, "#C084FC"),
        ("Repos", public_repos, "#E9D5FF"),
        ("Followers", followers, "#F0ABFC"),
        ("PRs", prs, "#D8B4FE"),
        ("Issues", issues, "#A78BFA"),
        ("Stars", total_stars, "#FDE68A"),
    ]
    star_steps = count_up_steps(total_stars, steps=9)
    step_dur = 0.14

    star_frames = []
    for idx, value in enumerate(star_steps):
        start = idx * step_dur
        if idx < len(star_steps) - 1:
            star_frames.append(
                f'<text text-anchor="middle" x="132" y="168" fill="#FDE68A" '
                f'font-family="Segoe UI, Ubuntu, Sans-Serif" font-size="52" font-weight="800" opacity="0">'
                f"{escape(compact(value))}"
                f'<animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.12;0.88;1" '
                f'dur="{step_dur:.2f}s" begin="{start:.2f}s" fill="remove"/>'
                f"</text>"
            )
        else:
            star_frames.append(
                f'<text text-anchor="middle" x="132" y="168" fill="#FDE68A" '
                f'font-family="Segoe UI, Ubuntu, Sans-Serif" font-size="52" font-weight="800" opacity="0" '
                f'filter="url(#goldGlow)">'
                f"{escape(compact(value))}"
                f'<animate attributeName="opacity" from="0" to="1" dur="0.3s" begin="{start:.2f}s" fill="freeze"/>'
                f"</text>"
            )

    # 2x3 metric tiles on the right (skip last Stars tile — already hero)
    side = [t for t in tiles if t[0] != "Stars"]
    tile_svg = []
    for i, (label, value, color) in enumerate(side):
        col, row = i % 2, i // 2
        x, y = 270 + col * 115, 70 + row * 70
        delay = 1.1 + i * 0.1
        tile_svg.append(
            f'<g transform="translate({x},{y})">'
            f'<rect width="105" height="58" rx="12" fill="#2A1038" stroke="{color}" stroke-width="1.2" opacity="0">'
            f'<animate attributeName="opacity" from="0" to="1" dur="0.4s" begin="{delay:.2f}s" fill="freeze"/>'
            f"</rect>"
            f'<text x="12" y="22" fill="#C4B5D4" font-family="Segoe UI, Ubuntu, Sans-Serif" '
            f'font-size="11" font-weight="600" opacity="0">{escape(label)}'
            f'<animate attributeName="opacity" from="0" to="1" dur="0.35s" begin="{delay + 0.1:.2f}s" fill="freeze"/>'
            f"</text>"
            f'<text x="12" y="44" fill="{color}" font-family="Segoe UI, Ubuntu, Sans-Serif" '
            f'font-size="20" font-weight="800" opacity="0">{escape(compact(value))}'
            f'<animate attributeName="opacity" from="0" to="1" dur="0.35s" begin="{delay + 0.18:.2f}s" fill="freeze"/>'
            f"</text>"
            f'<rect x="0" y="56" width="0" height="2" rx="1" fill="{color}">'
            f'<animate attributeName="width" from="0" to="105" dur="0.7s" begin="{delay:.2f}s" fill="freeze" '
            f'calcMode="spline" keySplines="0.22 1 0.36 1"/>'
            f"</rect>"
            f"</g>"
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(USERNAME)} GitHub stats">
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0%" stop-color="#12061A"/>
    <stop offset="50%" stop-color="#1C0A2E"/>
    <stop offset="100%" stop-color="#2A0B3D"/>
  </linearGradient>
  <linearGradient id="panel" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="#3B1058"/>
    <stop offset="100%" stop-color="#1A0826"/>
  </linearGradient>
  <radialGradient id="aura" cx="35%" cy="45%" r="55%">
    <stop offset="0%" stop-color="#82318E" stop-opacity="0.55"/>
    <stop offset="100%" stop-color="#12061A" stop-opacity="0"/>
  </radialGradient>
  <filter id="goldGlow" x="-50%" y="-50%" width="200%" height="200%">
    <feGaussianBlur stdDeviation="3" result="b"/>
    <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <filter id="neon" x="-40%" y="-40%" width="180%" height="180%">
    <feGaussianBlur stdDeviation="2.5" result="b"/>
    <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
</defs>

<rect width="{width}" height="{height}" rx="18" fill="url(#bg)"/>
<rect width="{width}" height="{height}" rx="18" fill="url(#aura)"/>
<rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="17" fill="none" stroke="#A855F7" stroke-opacity="0.55">
  <animate attributeName="stroke-opacity" values="0.35;0.85;0.35" dur="2.8s" repeatCount="indefinite"/>
</rect>

<text x="22" y="34" fill="#E9D5FF" font-family="Segoe UI, Ubuntu, Sans-Serif" font-size="15" font-weight="700">
  {escape(USERNAME)} · Research Dashboard
</text>
<text x="22" y="52" fill="#A78BFA" font-family="Segoe UI, Ubuntu, Sans-Serif" font-size="11" font-weight="600">
  Tsinghua Purple · Live GitHub Metrics
</text>

<!-- STAR CORE -->
<g transform="translate(20, 68)">
  <rect width="230" height="200" rx="16" fill="url(#panel)" stroke="#C084FC" stroke-opacity="0.45"/>
  <circle cx="115" cy="100" r="78" fill="none" stroke="#FDE68A" stroke-width="2" stroke-dasharray="8 10" opacity="0.7">
    <animateTransform attributeName="transform" type="rotate" from="0 115 100" to="360 115 100" dur="14s" repeatCount="indefinite"/>
  </circle>
  <circle cx="115" cy="100" r="62" fill="none" stroke="#A855F7" stroke-width="3" stroke-linecap="round"
          stroke-dasharray="390" stroke-dashoffset="390">
    <animate attributeName="stroke-dashoffset" from="390" to="70" dur="1.6s" fill="freeze"
             calcMode="spline" keySplines="0.22 1 0.36 1"/>
    <animate attributeName="stroke-opacity" values="0.55;1;0.55" dur="2s" begin="1.6s" repeatCount="indefinite"/>
  </circle>
  <polygon points="115,48 122,72 148,72 127,88 135,114 115,98 95,114 103,88 82,72 108,72"
           fill="#FDE68A" filter="url(#goldGlow)">
    <animate attributeName="opacity" values="0.75;1;0.75" dur="1.5s" repeatCount="indefinite"/>
  </polygon>
  {"".join(star_frames)}
  <text text-anchor="middle" x="115" y="192" fill="#E9D5FF" font-family="Segoe UI, Ubuntu, Sans-Serif"
        font-size="13" font-weight="700">TOTAL STARS</text>
</g>

{"".join(tile_svg)}
</svg>
"""


def render_langs_svg(lang_counts: list[tuple[str, int]], limit: int = 8) -> str:
    items = lang_counts[:limit]
    if not items:
        items = [("Unknown", 1)]

    total = sum(c for _, c in items) or 1
    width, height = 420, 300
    palette = [
        "#A855F7",
        "#C084FC",
        "#E879F9",
        "#F0ABFC",
        "#D8B4FE",
        "#7C3AED",
        "#FDE68A",
        "#F5D0FE",
    ]

    # Donut segments via stroke-dasharray on circles (SMIL draw-in).
    circumference = 2 * 3.1415926 * 68
    offset = 0.0
    arcs = []
    for i, (lang, count) in enumerate(items):
        color = palette[i % len(palette)]
        frac = count / total
        seg = circumference * frac
        gap = circumference - seg
        # rotate so segments accumulate
        rotation = -90 + (offset / circumference) * 360
        delay = 0.2 + i * 0.18
        arcs.append(
            f'<circle cx="120" cy="150" r="68" fill="none" stroke="{color}" stroke-width="18" '
            f'stroke-dasharray="0 {circumference:.2f}" stroke-linecap="butt" '
            f'transform="rotate({rotation:.2f} 120 150)" filter="url(#arcGlow)">'
            f'<animate attributeName="stroke-dasharray" '
            f'from="0 {circumference:.2f}" to="{seg:.2f} {gap:.2f}" '
            f'dur="1.1s" begin="{delay:.2f}s" fill="freeze" '
            f'calcMode="spline" keySplines="0.22 1 0.36 1"/>'
            f"</circle>"
        )
        offset += seg

    legend = []
    for i, (lang, count) in enumerate(items):
        color = palette[i % len(palette)]
        pct = 100.0 * count / total
        y = 78 + i * 36
        delay = 0.35 + i * 0.12
        bw = bar_width(count, max(c for _, c in items), 120)
        legend.append(
            f'<g opacity="0">'
            f'<animate attributeName="opacity" from="0" to="1" dur="0.4s" begin="{delay:.2f}s" fill="freeze"/>'
            f'<circle cx="250" cy="{y - 4}" r="5" fill="{color}"/>'
            f'<text x="264" y="{y}" fill="#E9D5FF" font-family="Segoe UI, Ubuntu, Sans-Serif" '
            f'font-size="13" font-weight="700">{escape(lang)}</text>'
            f'<text x="390" y="{y}" text-anchor="end" fill="{color}" font-family="Segoe UI, Ubuntu, Sans-Serif" '
            f'font-size="13" font-weight="800">{pct:.1f}%</text>'
            f'<rect x="250" y="{y + 8}" width="140" height="5" rx="2.5" fill="#3B1058"/>'
            f'<rect x="250" y="{y + 8}" width="0" height="5" rx="2.5" fill="{color}">'
            f'<animate attributeName="width" from="0" to="{bw:.1f}" dur="0.9s" begin="{delay:.2f}s" fill="freeze" '
            f'calcMode="spline" keySplines="0.22 1 0.36 1"/>'
            f"</rect>"
            f"</g>"
        )

    top_name, top_count = items[0]
    top_pct = 100.0 * top_count / total

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Top Languages">
<defs>
  <linearGradient id="langBg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0%" stop-color="#12061A"/>
    <stop offset="100%" stop-color="#2A0B3D"/>
  </linearGradient>
  <filter id="arcGlow" x="-30%" y="-30%" width="160%" height="160%">
    <feGaussianBlur stdDeviation="1.6" result="b"/>
    <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
</defs>
<rect width="{width}" height="{height}" rx="18" fill="url(#langBg)"/>
<rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="17" fill="none" stroke="#C084FC" stroke-opacity="0.5">
  <animate attributeName="stroke-opacity" values="0.3;0.8;0.3" dur="3s" repeatCount="indefinite"/>
</rect>
<text x="22" y="34" fill="#E9D5FF" font-family="Segoe UI, Ubuntu, Sans-Serif" font-size="15" font-weight="700">
  Language Spectrum
</text>
<text x="22" y="52" fill="#A78BFA" font-family="Segoe UI, Ubuntu, Sans-Serif" font-size="11" font-weight="600">
  Byte-weighted stack signal
</text>

{"".join(arcs)}
<circle cx="120" cy="150" r="46" fill="#1A0826"/>
<text text-anchor="middle" x="120" y="144" fill="#E9D5FF" font-family="Segoe UI, Ubuntu, Sans-Serif"
      font-size="12" font-weight="700">{escape(top_name)}</text>
<text text-anchor="middle" x="120" y="168" fill="#FDE68A" font-family="Segoe UI, Ubuntu, Sans-Serif"
      font-size="18" font-weight="800">{top_pct:.0f}%</text>

{"".join(legend)}
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


def render_header_svg() -> str:
    """Full-bleed hero banner (avoids narrow third-party capsule widgets)."""
    width, height = 1100, 200
    lines = [
        "PhD Student @ Tsinghua University",
        "Representation Learning",
        "AI4Healthcare",
        "Computational Pathology & Medical AI",
    ]
    frames = []
    n = len(lines)
    for i, line in enumerate(lines):
        # Full-period loop so lines take turns without overlapping forever.
        a = i / n
        b = (i + 0.08) / n
        c = (i + 0.92) / n
        d = (i + 1) / n
        frames.append(
            f'<text text-anchor="middle" x="{width / 2:.0f}" y="118" fill="#F3E8FF" '
            f'font-family="Segoe UI, Ubuntu, Sans-Serif" font-size="20" font-weight="600" opacity="0">'
            f"{escape(line)}"
            f'<animate attributeName="opacity" values="0;0;1;1;0;0" '
            f'keyTimes="0;{a:.3f};{b:.3f};{c:.3f};{d:.3f};1" '
            f'dur="12.8s" repeatCount="indefinite"/>'
            f"</text>"
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid slice" role="img" aria-label="Xitong Ling">
<defs>
  <linearGradient id="heroBg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0%" stop-color="#2A0840"/>
    <stop offset="45%" stop-color="{PURPLE}"/>
    <stop offset="100%" stop-color="#9B59B6"/>
  </linearGradient>
  <linearGradient id="waveFill" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="#12061A" stop-opacity="0.15"/>
    <stop offset="100%" stop-color="#12061A" stop-opacity="0.55"/>
  </linearGradient>
</defs>
<rect width="{width}" height="{height}" fill="url(#heroBg)"/>
<circle cx="980" cy="30" r="120" fill="#ffffff" fill-opacity="0.06">
  <animate attributeName="cy" values="30;48;30" dur="5s" repeatCount="indefinite"/>
</circle>
<circle cx="80" cy="160" r="90" fill="#ffffff" fill-opacity="0.05">
  <animate attributeName="cx" values="80;110;80" dur="6s" repeatCount="indefinite"/>
</circle>
<path d="M0,155 C180,130 320,185 520,160 C740,130 900,175 1100,150 L1100,200 L0,200 Z" fill="url(#waveFill)">
  <animateTransform attributeName="transform" type="translate" values="0 0; -40 0; 0 0" dur="8s" repeatCount="indefinite"/>
</path>
<text text-anchor="middle" x="{width / 2:.0f}" y="72" fill="#FFFFFF"
      font-family="Segoe UI, Ubuntu, Sans-Serif" font-size="44" font-weight="800">Xitong Ling</text>
{"".join(frames)}
<text text-anchor="middle" x="{width / 2:.0f}" y="168" fill="#E9D5FF"
      font-family="Segoe UI, Ubuntu, Sans-Serif" font-size="14" font-weight="600">
  PhD Student · Representation Learning · AI4Healthcare
</text>
</svg>
"""


def render_about_card() -> str:
    """Wide identity strip — fills README content width."""
    width, height = 1100, 168
    chips = [
        ("PhD Student", 36, 118, 120),
        ("Representation Learning", 172, 118, 200),
        ("AI4Healthcare", 388, 118, 130),
        ("Tsinghua SIGS", 534, 118, 120),
        ("Beihang -> Tsinghua", 670, 118, 160),
    ]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="About Xitong Ling">
<defs>
  <linearGradient id="aboutBg" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0%" stop-color="#2A0840"/>
    <stop offset="50%" stop-color="{PURPLE}"/>
    <stop offset="100%" stop-color="{PURPLE_MID}"/>
  </linearGradient>
</defs>
<rect width="{width}" height="{height}" rx="14" fill="url(#aboutBg)"/>
<rect x="0" y="0" width="8" height="{height}" fill="#FDE68A">
  <animate attributeName="opacity" values="0.55;1;0.55" dur="2s" repeatCount="indefinite"/>
</rect>
<text x="36" y="42" fill="#FFFFFF" font-family="Segoe UI, Ubuntu, Sans-Serif" font-size="26" font-weight="800">Xitong Ling</text>
<text x="36" y="72" fill="#F3E8FF" font-family="Segoe UI, Ubuntu, Sans-Serif" font-size="15" font-weight="600">PhD Student | Tsinghua University (SIGS)</text>
<text x="36" y="96" fill="#EDE0F5" font-family="Segoe UI, Ubuntu, Sans-Serif" font-size="13" font-weight="500">Research: Representation Learning / AI4Healthcare · Homepage: lingxitong.github.io · Email: lingxt23@mails.tsinghua.edu.cn</text>
{"".join(
    f'<g>'
    f'<rect x="{x}" y="{y}" width="{w}" height="28" rx="14" fill="#F8F0FF"/>'
    f'<text x="{x + 12}" y="{y + 18}" fill="{PURPLE_INK}" font-family="Segoe UI, Ubuntu, Sans-Serif" font-size="12" font-weight="700">{label}</text>'
    f"</g>"
    for label, x, y, w in chips
)}
</svg>
"""


def main() -> int:
    user = fetch_user()
    repos = fetch_owned_repos()
    by_name = {r.get("name"): r for r in repos}

    total_stars = sum(int(r.get("stargazers_count") or 0) for r in repos)
    total_forks = sum(int(r.get("forks_count") or 0) for r in repos)
    lang_counter = fetch_language_bytes(repos, top_n=25)
    if not lang_counter:
        for repo in repos:
            lang = repo.get("language")
            if lang:
                lang_counter[lang] += 1

    prs = fetch_count(f"author:{USERNAME} type:pr")
    issues = fetch_count(f"author:{USERNAME} type:issue")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    header_path = OUT_DIR / "header.svg"
    about_path = OUT_DIR / "about.svg"
    stats_path = OUT_DIR / "stats.svg"
    langs_path = OUT_DIR / "top-langs.svg"
    # Versioned filenames bust GitHub/camo image cache after redesigns.
    stats_v_path = OUT_DIR / "stats-neon.svg"
    langs_v_path = OUT_DIR / "langs-neon.svg"

    header_path.write_text(render_header_svg(), encoding="utf-8")
    about_path.write_text(render_about_card(), encoding="utf-8")
    stats_svg = render_stats_svg(
        total_stars=total_stars,
        total_forks=total_forks,
        public_repos=int(user.get("public_repos") or len(repos)),
        followers=int(user.get("followers") or 0),
        prs=prs,
        issues=issues,
    )
    langs_svg = render_langs_svg(lang_counter.most_common(6))
    stats_path.write_text(stats_svg, encoding="utf-8")
    langs_path.write_text(langs_svg, encoding="utf-8")
    stats_v_path.write_text(stats_svg, encoding="utf-8")
    langs_v_path.write_text(langs_svg, encoding="utf-8")

    featured = [by_name[name] for name in FEATURED_REPOS if name in by_name]
    if not featured:
        featured = sorted(
            repos, key=lambda r: int(r.get("stargazers_count") or 0), reverse=True
        )[:4]

    for repo in featured:
        path = OUT_DIR / f"pin-{repo['name']}.svg"
        path.write_text(render_repo_card(repo), encoding="utf-8")
        print(f"Wrote {path}")

    print(f"Wrote {header_path}")
    print(f"Wrote {about_path}")
    print(f"Wrote {stats_path} / {stats_v_path} (stars={total_stars})")
    print(f"Wrote {langs_path} / {langs_v_path} (langs={len(lang_counter)})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - surface clear CI failure
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
