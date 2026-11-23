#!/usr/bin/env python3
"""Sync tech stack and featured projects SVGs plus README badges from GitHub."""

from __future__ import annotations

import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

USERNAME = "1AbidD"
# Add tools that cannot be auto-detected from public GitHub repos (kept empty by default).
MANUAL_EXTRA: list[str] = []

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets"
README_PATH = ROOT / "README.md"

LANG_COLORS: dict[str, str] = {
    "Python": "#a855f7",
    "Dart": "#22d3ee",
    "C++": "#ec4899",
    "CMake": "#818cf8",
    "HTML": "#f97316",
    "CSS": "#38bdf8",
    "JavaScript": "#facc15",
    "TypeScript": "#60a5fa",
    "Kotlin": "#c084fc",
    "Swift": "#fb7185",
    "Dockerfile": "#0ea5e9",
    "C": "#94a3b8",
    "Jupyter Notebook": "#f59e0b",
    "SQL": "#34d399",
}

SKILLICON_MAP: dict[str, str] = {
    "Python": "py",
    "Dart": "dart",
    "C++": "cpp",
    "CMake": "cmake",
    "HTML": "html",
    "CSS": "css",
    "JavaScript": "js",
    "TypeScript": "ts",
    "Flutter": "flutter",
    "Firebase": "firebase",
    "Docker": "docker",
    "Flask": "flask",
    "FastAPI": "fastapi",
    "Django": "django",
    "SQLite": "sqlite",
    "PostgreSQL": "postgres",
    "MySQL": "mysql",
    "MongoDB": "mongodb",
    "Node.js": "nodejs",
    "React": "react",
    "Next.js": "nextjs",
    "Vue": "vue",
    "Tailwind CSS": "tailwind",
    "Express": "express",
    "Vite": "vite",
    "PyTorch": "pytorch",
    "TensorFlow": "tensorflow",
    "Scikit-learn": "sklearn",
    "Linux": "linux",
}

SHIELD_BADGE_MAP: dict[str, tuple[str, str]] = {
    "Pandas": ("Pandas", "pandas"),
    "NumPy": ("NumPy", "numpy"),
    "Gradio": ("Gradio", "gradio"),
    "Pydantic": ("Pydantic", "pydantic"),
    "Hugging Face": ("Hugging_Face", "huggingface"),
    "Jupyter": ("Jupyter", "jupyter"),
    "Streamlit": ("Streamlit", "streamlit"),
    "SQLAlchemy": ("SQLAlchemy", "sqlalchemy"),
    "SQL": ("SQL", "databricks"),
}

PY_DEP_PATTERNS: list[tuple[str, str]] = [
    (r"\bflask\b", "Flask"),
    (r"\bfastapi\b", "FastAPI"),
    (r"\bdjango\b", "Django"),
    (r"\bpandas\b", "Pandas"),
    (r"\bnumpy\b", "NumPy"),
    (r"\bscikit-learn\b|\bsklearn\b", "Scikit-learn"),
    (r"\btorch\b|\bpytorch\b", "PyTorch"),
    (r"\btensorflow\b", "TensorFlow"),
    (r"\bgradio\b", "Gradio"),
    (r"\bpydantic\b", "Pydantic"),
    (r"\bhuggingface[_-]hub\b", "Hugging Face"),
    (r"\bstreamlit\b", "Streamlit"),
    (r"\bsqlalchemy\b", "SQLAlchemy"),
    (r"\bjupyter\b|\bipykernel\b", "Jupyter"),
]

NODE_DEP_MAP: dict[str, str] = {
    "react": "React",
    "next": "Next.js",
    "vue": "Vue",
    "typescript": "TypeScript",
    "tailwindcss": "Tailwind CSS",
    "express": "Express",
    "vite": "Vite",
}

WEAK_DESCRIPTIONS = {
    "tugas kuliah di upload disini",
    "a new flutter project.",
    "a new flutter project",
}

# Flutter generates platform runner C++/CMake boilerplate that is not user-authored tooling.
GENERATED_RUNNER_PREFIXES = (
    "linux/",
    "windows/",
    "macos/",
    "ios/",
    "android/",
    "web/",
    "apps/linux/",
    "apps/windows/",
    "apps/macos/",
    "apps/ios/",
    "apps/android/",
    "apps/web/",
)


def _headers(accept: str = "application/vnd.github+json") -> dict[str, str]:
    headers = {"User-Agent": "1AbidD-profile-sync", "Accept": accept}
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def api_get_json(url: str) -> Any:
    req = urllib.request.Request(url, headers=_headers())
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_raw_text(owner: str, repo: str, branch: str, path: str) -> str | None:
    quoted = urllib.parse.quote(path, safe="/")
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{quoted}"
    req = urllib.request.Request(url, headers={"User-Agent": "1AbidD-profile-sync"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError):
        return None


def fetch_non_fork_repos() -> list[dict[str, Any]]:
    url = f"https://api.github.com/users/{USERNAME}/repos?per_page=100&type=owner&sort=pushed"
    repos = api_get_json(url)
    # Exclude forks and the special profile repository itself so automation scripts do not skew stats.
    return [
        r
        for r in repos
        if not r.get("fork") and r.get("name", "").lower() != USERNAME.lower()
    ]


def collect_stack(repos: list[dict[str, Any]]) -> tuple[list[tuple[str, int, float]], list[str]]:
    lang_totals: dict[str, int] = {}
    detected_tools: list[str] = []

    def add_tool(name: str) -> None:
        if all(existing.lower() != name.lower() for existing in detected_tools):
            detected_tools.append(name)

    for repo in repos:
        name = repo["name"]
        branch = repo.get("default_branch") or "main"

        langs = api_get_json(f"https://api.github.com/repos/{USERNAME}/{name}/languages")
        for lang, size in langs.items():
            lang_totals[lang] = lang_totals.get(lang, 0) + int(size)

        try:
            tree_data = api_get_json(
                f"https://api.github.com/repos/{USERNAME}/{name}/git/trees/{branch}?recursive=1"
            )
            paths = [
                item["path"]
                for item in tree_data.get("tree", [])
                if item.get("type") == "blob"
            ]
        except (urllib.error.URLError, TimeoutError):
            paths = []

        checked_requirements: set[str] = set()
        for path in paths:
            lower = path.lower()
            base = lower.split("/")[-1]
            is_runner = lower.startswith(GENERATED_RUNNER_PREFIXES)

            if base == "pubspec.yaml":
                content = fetch_raw_text(USERNAME, name, branch, path) or ""
                if re.search(r"^\s*flutter\s*:", content, re.M):
                    add_tool("Flutter")
                add_tool("Dart")
                if re.search(r"firebase_core|cloud_firestore|firebase_auth", content):
                    add_tool("Firebase")
                if re.search(r"\bsqflite\b", content):
                    add_tool("SQLite")

            elif base in ("requirements.txt", "pyproject.toml"):
                if path not in checked_requirements:
                    checked_requirements.add(path)
                    content = (fetch_raw_text(USERNAME, name, branch, path) or "").lower()
                    add_tool("Python")
                    for pattern, label in PY_DEP_PATTERNS:
                        if re.search(pattern, content):
                            add_tool(label)

            elif base in ("dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
                add_tool("Docker")

            elif base == "package.json" and not is_runner:
                raw_pkg = fetch_raw_text(USERNAME, name, branch, path)
                add_tool("Node.js")
                if raw_pkg:
                    try:
                        pkg = json.loads(raw_pkg)
                        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                        for dep_key, label in NODE_DEP_MAP.items():
                            if dep_key in deps:
                                add_tool(label)
                    except json.JSONDecodeError:
                        pass

            elif base.endswith((".cpp", ".cc", ".cxx")) and not is_runner:
                add_tool("C++")

            elif base == "cmakelists.txt" and not is_runner:
                add_tool("CMake")

            elif base.endswith(".ipynb"):
                add_tool("Jupyter")

            elif base.endswith(".sql"):
                add_tool("SQL")

            elif base.endswith(".html") and not is_runner:
                add_tool("HTML")

            elif base in ("database.py", "db.py"):
                content = fetch_raw_text(USERNAME, name, branch, path) or ""
                if "sqlite3" in content:
                    add_tool("SQLite")

        primary_lang = repo.get("language")
        if primary_lang in ("Python", "Dart", "C++", "JavaScript", "TypeScript"):
            add_tool(primary_lang)

    for manual_item in MANUAL_EXTRA:
        if manual_item.strip():
            add_tool(manual_item.strip())

    total_bytes = sum(lang_totals.values()) or 1
    ranked_langs = sorted(lang_totals.items(), key=lambda kv: kv[1], reverse=True)
    lang_rows = [
        (lang, size, (size / total_bytes) * 100.0)
        for lang, size in ranked_langs
        if (size / total_bytes) * 100.0 >= 0.3
    ][:6]

    return lang_rows, detected_tools


def fetch_featured_projects(fallback_repos: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        query = """
        query($login: String!) {
          user(login: $login) {
            pinnedItems(first: 6, types: REPOSITORY) {
              nodes {
                ... on Repository {
                  name
                  description
                  url
                  stargazerCount
                  pushedAt
                  isFork
                  primaryLanguage {
                    name
                    color
                  }
                }
              }
            }
          }
        }
        """
        payload = json.dumps({"query": query, "variables": {"login": USERNAME}}).encode("utf-8")
        req = urllib.request.Request(
            "https://api.github.com/graphql",
            data=payload,
            headers={**_headers("application/json"), "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            nodes = (
                data.get("data", {})
                .get("user", {})
                .get("pinnedItems", {})
                .get("nodes", [])
            )
            pinned = [
                {
                    "name": n["name"],
                    "description": n.get("description"),
                    "url": n["url"],
                    "stars": int(n.get("stargazerCount", 0)),
                    "pushed_at": (n.get("pushedAt") or "")[:10],
                    "language": (n.get("primaryLanguage") or {}).get("name") or "Unknown",
                    "color": (n.get("primaryLanguage") or {}).get("color"),
                }
                for n in nodes
                if n and not n.get("isFork")
            ]
            if pinned:
                return pinned[:4], "PINNED"
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError):
            pass

    recent = sorted(fallback_repos, key=lambda r: r.get("pushed_at", ""), reverse=True)[:4]
    projects = [
        {
            "name": r["name"],
            "description": r.get("description"),
            "url": r["html_url"],
            "stars": int(r.get("stargazers_count", 0)),
            "pushed_at": (r.get("pushed_at") or "")[:10],
            "language": r.get("language") or "Unknown",
            "color": LANG_COLORS.get(r.get("language") or ""),
        }
        for r in recent
    ]
    return projects, "RECENT"


def clean_description(desc: str | None) -> str | None:
    if not desc:
        return None
    text = " ".join(desc.strip().split())
    if len(text) < 6 or text.lower() in WEAK_DESCRIPTIONS:
        return None
    return text


def truncate(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else text[: max_len - 3].rstrip() + "..."


def render_tech_stack_svg(
    lang_rows: list[tuple[str, int, float]],
    tools: list[str],
    repo_count: int,
) -> str:
    bar_start_y = 66
    bar_gap = 34
    bars_svg: list[str] = []
    bar_max_w = 576

    for idx, (lang, _size, pct) in enumerate(lang_rows):
        y = bar_start_y + idx * bar_gap
        color = LANG_COLORS.get(lang, "#a020f0")
        fill_w = max(8.0, (pct / 100.0) * bar_max_w)
        delay = round(idx * 0.12, 2)
        bars_svg.append(
            f'    <text x="34" y="{y + 13}" font-family="ui-monospace, \'SFMono-Regular\', Consolas, monospace" '
            f'font-size="12.5" font-weight="600" fill="#e2e8f0">{html.escape(lang)}</text>\n'
            f'    <rect x="196" y="{y + 2}" width="{bar_max_w}" height="12" rx="2" fill="#11172e" stroke="#2e1f5e" stroke-width="1"/>\n'
            f'    <rect class="bar" x="196" y="{y + 2}" width="{fill_w:.1f}" height="12" rx="2" fill="{color}" style="animation-delay:{delay}s"/>\n'
            f'    <text x="846" y="{y + 13}" text-anchor="end" font-family="ui-monospace, \'SFMono-Regular\', Consolas, monospace" '
            f'font-size="12" fill="#cbd5e1">{pct:.1f}%</text>'
        )

    if not lang_rows:
        bars_svg.append(
            f'    <text x="34" y="{bar_start_y + 13}" font-family="ui-monospace, \'SFMono-Regular\', Consolas, monospace" '
            f'font-size="12" fill="#94a3b8">No public repository languages detected yet.</text>'
        )

    chips_header_y = bar_start_y + max(1, len(lang_rows)) * bar_gap + 18
    chips_svg: list[str] = []
    cursor_x = 34
    cursor_y = chips_header_y + 16
    max_x = 846

    for tool in tools:
        chip_w = max(72, len(tool) * 8 + 26)
        if cursor_x + chip_w > max_x:
            cursor_x = 34
            cursor_y += 34
        pts = (
            f"{cursor_x + 6},{cursor_y} {cursor_x + chip_w},{cursor_y} "
            f"{cursor_x + chip_w},{cursor_y + 20} {cursor_x + chip_w - 6},{cursor_y + 26} "
            f"{cursor_x},{cursor_y + 26} {cursor_x},{cursor_y + 6}"
        )
        chips_svg.append(
            f'    <polygon points="{pts}" fill="#10162c" stroke="#7c3aed" stroke-width="1"/>\n'
            f'    <rect x="{cursor_x + 8}" y="{cursor_y + 10}" width="5" height="5" fill="#22d3ee"/>\n'
            f'    <text x="{cursor_x + 19}" y="{cursor_y + 17}" font-family="ui-monospace, \'SFMono-Regular\', Consolas, monospace" '
            f'font-size="11.5" fill="#e2e8f0">{html.escape(tool)}</text>'
        )
        cursor_x += chip_w + 10

    height = cursor_y + 52
    synced = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    frame_pts = f"16,4 864,4 876,16 876,{height - 16} 864,{height - 4} 16,{height - 4} 4,{height - 16} 4,16"

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 880 {height}" width="880" height="{height}" role="img" aria-label="Auto-synced GitHub tech stack for 1AbidD">
  <defs>
    <linearGradient id="tsBg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#060914"/>
      <stop offset="100%" stop-color="#0f1229"/>
    </linearGradient>
    <linearGradient id="tsBorder" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#7c3aed"/>
      <stop offset="50%" stop-color="#22d3ee" stop-opacity="0.7"/>
      <stop offset="100%" stop-color="#a020f0"/>
    </linearGradient>
  </defs>
  <style>
    .bar {{
      transform-box: fill-box;
      transform-origin: left center;
      animation: grow 1.1s cubic-bezier(0.22, 1, 0.36, 1) both;
    }}
    @keyframes grow {{
      from {{ transform: scaleX(0); opacity: 0.4; }}
      to {{ transform: scaleX(1); opacity: 1; }}
    }}
    @media (prefers-reduced-motion: reduce) {{
      .bar {{ animation: none; }}
    }}
  </style>

  <polygon points="{frame_pts}" fill="url(#tsBg)" stroke="url(#tsBorder)" stroke-width="1.4"/>
  <polyline points="4,36 4,16 16,4 42,4" fill="none" stroke="#22d3ee" stroke-width="2"/>
  <polyline points="838,{height - 4} 864,{height - 4} 876,{height - 16} 876,{height - 36}" fill="none" stroke="#a020f0" stroke-width="2"/>

  <g font-family="ui-monospace, 'SFMono-Regular', Consolas, monospace">
    <rect x="34" y="24" width="6" height="6" fill="#a020f0"/>
    <text x="48" y="31" font-size="12" font-weight="700" fill="#c4b5fd" letter-spacing="1.2">TELEMETRY // LANGUAGE DISTRIBUTION</text>
    <text x="846" y="31" text-anchor="end" font-size="10.5" fill="#94a3b8">{repo_count} PUBLIC REPOS (NO FORKS) | SYNC {synced}</text>
    <line x1="34" y1="44" x2="846" y2="44" stroke="#312e81" stroke-width="1"/>
  </g>

  <g>
{chr(10).join(bars_svg)}
  </g>

  <g font-family="ui-monospace, 'SFMono-Regular', Consolas, monospace">
    <line x1="34" y1="{chips_header_y - 16}" x2="846" y2="{chips_header_y - 16}" stroke="#312e81" stroke-width="1"/>
    <text x="34" y="{chips_header_y + 2}" font-size="11" font-weight="700" fill="#67e8f9" letter-spacing="1">DETECTED FRAMEWORKS &amp; TOOLING (FROM REPO FILES)</text>
  </g>

  <g>
{chr(10).join(chips_svg)}
  </g>
</svg>
"""


def render_projects_svg(projects: list[dict[str, Any]], source_tag: str) -> str:
    card_w = 408
    card_h = 122
    gap_x = 24
    gap_y = 20
    start_x = 20
    start_y = 54

    rows = max(1, (len(projects) + 1) // 2)
    height = start_y + rows * card_h + (rows - 1) * gap_y + 22
    cards_svg: list[str] = []

    for idx, proj in enumerate(projects):
        col = idx % 2
        row = idx // 2
        x = start_x + col * (card_w + gap_x)
        y = start_y + row * (card_h + gap_y)
        cut = 12
        pts = (
            f"{x + cut},{y} {x + card_w - cut},{y} {x + card_w},{y + cut} "
            f"{x + card_w},{y + card_h - cut} {x + card_w - cut},{y + card_h} "
            f"{x + cut},{y + card_h} {x},{y + card_h - cut} {x},{y + cut}"
        )

        title = html.escape(truncate(proj["name"], 32))
        desc = clean_description(proj.get("description"))
        lang = proj.get("language") or "Unknown"
        dot_color = proj.get("color") or LANG_COLORS.get(lang, "#a020f0")
        stars = proj.get("stars", 0)
        pushed = proj.get("pushed_at", "")

        desc_el = ""
        if desc:
            desc_el = (
                f'    <text x="{x + 18}" y="{y + 64}" font-family="\'Segoe UI\', system-ui, sans-serif" '
                f'font-size="12.5" fill="#cbd5e1">{html.escape(truncate(desc, 50))}</text>\n'
            )

        meta_right = f"★ {stars}" if stars > 0 else (f"PUSHED {pushed}" if pushed else "")
        cards_svg.append(
            f'  <g>\n'
            f'    <polygon points="{pts}" fill="none" stroke="#a020f0" stroke-width="2.4" opacity="0.28" filter="url(#cardGlow)"/>\n'
            f'    <polygon points="{pts}" fill="#0a0f22" stroke="#7c3aed" stroke-width="1.35"/>\n'
            f'    <polyline points="{x},{y + 24} {x},{y + cut} {x + cut},{y} {x + 30},{y}" fill="none" stroke="#22d3ee" stroke-width="1.8"/>\n'
            f'    <text x="{x + 18}" y="{y + 34}" font-family="ui-monospace, \'SFMono-Regular\', Consolas, monospace" '
            f'font-size="14" font-weight="700" fill="#f8fafc">{title}</text>\n'
            f'{desc_el}'
            f'    <line x1="{x + 18}" y1="{y + 84}" x2="{x + card_w - 18}" y2="{y + 84}" stroke="#1e293b" stroke-width="1"/>\n'
            f'    <circle cx="{x + 24}" cy="{y + 102}" r="4.5" fill="{dot_color}"/>\n'
            f'    <text x="{x + 35}" y="{y + 106}" font-family="ui-monospace, \'SFMono-Regular\', Consolas, monospace" '
            f'font-size="11.5" fill="#e2e8f0">{html.escape(lang)}</text>\n'
            f'    <text x="{x + card_w - 18}" y="{y + 106}" text-anchor="end" font-family="ui-monospace, \'SFMono-Regular\', Consolas, monospace" '
            f'font-size="10.5" fill="#94a3b8">{html.escape(meta_right)}</text>\n'
            f'  </g>'
        )

    outer_pts = f"16,4 864,4 876,16 876,{height - 16} 864,{height - 4} 16,{height - 4} 4,{height - 16} 4,16"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 880 {height}" width="880" height="{height}" role="img" aria-label="Featured GitHub projects for 1AbidD">
  <defs>
    <linearGradient id="prBg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#060914"/>
      <stop offset="100%" stop-color="#0e1227"/>
    </linearGradient>
    <linearGradient id="prBorder" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#a020f0" stop-opacity="0.85"/>
      <stop offset="50%" stop-color="#7c3aed" stop-opacity="0.7"/>
      <stop offset="100%" stop-color="#22d3ee" stop-opacity="0.8"/>
    </linearGradient>
    <filter id="cardGlow" x="-8%" y="-15%" width="116%" height="130%">
      <feGaussianBlur stdDeviation="3.2"/>
    </filter>
  </defs>

  <polygon points="{outer_pts}" fill="url(#prBg)" stroke="url(#prBorder)" stroke-width="1.4"/>
  <g font-family="ui-monospace, 'SFMono-Regular', Consolas, monospace">
    <rect x="22" y="22" width="6" height="6" fill="#22d3ee"/>
    <text x="36" y="29" font-size="12" font-weight="700" fill="#c4b5fd" letter-spacing="1.2">MISSION LOG // FEATURED REPOSITORIES</text>
    <text x="858" y="29" text-anchor="end" font-size="10.5" fill="#94a3b8">SOURCE: {source_tag}</text>
  </g>

{chr(10).join(cards_svg)}
</svg>
"""


def build_stack_icons_markdown(tools: list[str]) -> str:
    skill_ids: list[str] = []
    extra_shields: list[str] = []

    for tool in tools:
        if tool in SKILLICON_MAP:
            icon_id = SKILLICON_MAP[tool]
            if icon_id not in skill_ids:
                skill_ids.append(icon_id)
        elif tool in SHIELD_BADGE_MAP:
            label, logo = SHIELD_BADGE_MAP[tool]
            badge_url = (
                f"https://img.shields.io/badge/{label}-0b0f1e"
                f"?style=for-the-badge&amp;logo={logo}&amp;logoColor=c4b5fd&amp;labelColor=7c3aed"
            )
            extra_shields.append(f'<img src="{badge_url}" alt="{html.escape(tool)}" height="28" />')

    blocks: list[str] = []
    if skill_ids:
        joined = ",".join(skill_ids)
        blocks.append(
            f'<p align="center">\n'
            f'  <img src="https://skillicons.dev/icons?i={joined}&amp;theme=dark" alt="Detected tech stack icons" height="48" />\n'
            f'</p>'
        )
    if extra_shields:
        blocks.append(
            '<p align="center">\n  ' + "\n  ".join(extra_shields) + "\n</p>"
        )
    return "\n".join(blocks)


def build_project_links_markdown(projects: list[dict[str, Any]]) -> str:
    links = [
        f'<a href="{p["url"]}">{html.escape(p["name"])}</a>'
        for p in projects
    ]
    return '<p align="center">\n  ' + " &nbsp;&middot;&nbsp; ".join(links) + "\n</p>"


def replace_marker_block(text: str, marker: str, replacement: str) -> str:
    start = f"<!-- {marker}:START -->"
    end = f"<!-- {marker}:END -->"
    pattern = re.compile(rf"({re.escape(start)})(.*?)({re.escape(end)})", re.S)
    if not pattern.search(text):
        return text
    return pattern.sub(rf"\1\n{replacement}\n\3", text, count=1)


def main() -> None:
    repos = fetch_non_fork_repos()
    lang_rows, tools = collect_stack(repos)
    projects, source_tag = fetch_featured_projects(repos)

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    tech_svg = render_tech_stack_svg(lang_rows, tools, len(repos))
    tech_path = ASSETS_DIR / "tech-stack.svg"
    tech_path.write_text(tech_svg, encoding="utf-8")

    proj_svg = render_projects_svg(projects, source_tag)
    proj_path = ASSETS_DIR / "projects.svg"
    proj_path.write_text(proj_svg, encoding="utf-8")

    if README_PATH.is_file():
        readme = README_PATH.read_text(encoding="utf-8")
        updated = replace_marker_block(readme, "STACK_ICONS", build_stack_icons_markdown(tools))
        updated = replace_marker_block(updated, "PROJECTS_LINKS", build_project_links_markdown(projects))
        if updated != readme:
            README_PATH.write_text(updated, encoding="utf-8")

    print(f"Detected languages: {[r[0] for r in lang_rows]}")
    print(f"Detected tools: {tools}")
    print(f"Featured projects ({source_tag}): {[p['name'] for p in projects]}")
    print(f"Wrote {tech_path} ({len(tech_svg.encode('utf-8'))} bytes)")
    print(f"Wrote {proj_path} ({len(proj_svg.encode('utf-8'))} bytes)")


if __name__ == "__main__":
    main()
