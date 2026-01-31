#!/usr/bin/env python3
"""
Enhanced: renders SVGs using Jinja2 templates, persists per-repo history snapshots,
and produces three artifacts:

 - stats.svg        (summary card — top-N repos by clones)
 - REPO_CLONES.svg  (full tabular SVG)
 - history.svg      (trend charts derived from persisted snapshots)

Behavior notes:
 - By default only public repos are processed. Use INCLUDE_PRIVATE env or --include-private to opt-in.
 - PAT environment variable name defaults to TOKEN (override with --token-env).
 - For more information read README.md
"""
import os
import sys
import argparse
import datetime
import requests
import time
import subprocess
from typing import Optional, List, Dict, Any, Tuple
from urllib.parse import urlparse
import re
import sqlite3
from jinja2 import Template

# Base GitHub API constants
API_BASE = "https://api.github.com"
HEADERS_COMMON = {
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "clone-sweeper/1.0",
}

# ---------------------------
# Helpers
# ---------------------------
def escape_xml(s: Optional[str]) -> str:
    """
    Escape a string for safe embedding inside XML/SVG text nodes or attributes.

    Why: repository names and descriptions come from external sources and may contain
    characters that break XML (e.g. &, <, >, " and '). Always escape them before
    inserting into the generated SVG.

    Returns an empty string for None input.
    """
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
             .replace("'", "&apos;"))

def ensure_dir(path: str):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

# ---------------------------
# HTTP helpers
# ---------------------------
def request_with_auth(url: str, token: Optional[str] = None, params: dict = None) -> requests.Response:
    """
    Perform an HTTP GET to `url` using optional `token` for Authorization.

    - Adds the standard Accept and User-Agent headers.
    - Adds an Authorization header when token is provided.
    - Returns the `requests.Response` object for caller handling.

    Note: callers are responsible for checking r.status_code and parsing JSON.
    """
    headers = HEADERS_COMMON.copy()
    if token:
        headers["Authorization"] = f"token {token}"
    return requests.get(url, headers=headers, params=params or {}, timeout=30)

def paginate(url: str, token: Optional[str] = None, params: dict = None) -> List[Dict[str, Any]]:
    """
    Paginate through a GitHub API endpoint that uses Link headers for paging.

    - `url` is the initial URL (e.g. https://api.github.com/user/repos).
    - `token` passes authentication if provided.
    - `params` are query parameters for the first request only.

    Returns the concatenated list of items (each request expected to return a JSON list).
    Raises RuntimeError on HTTP >= 400 to make failures explicit.
    """
    items = []
    cur_url = url
    cur_params = params or {}
    while cur_url:
        r = request_with_auth(cur_url, token, params=cur_params)
        if r.status_code >= 400:
            # Surface the raw response for debugging (status + body)
            raise RuntimeError(f"GitHub API error {r.status_code} for {cur_url}: {r.text}")
        batch = r.json()
        if isinstance(batch, list):
            items.extend(batch)
        else:
            # Some endpoints may return an object when single resource requested; handle defensively
            items.append(batch)
        # Parse Link header for rel="next"
        link = r.headers.get("Link", "")
        next_url = None
        if link:
            parts = link.split(",")
            for p in parts:
                if 'rel="next"' in p:
                    start = p.find("<") + 1
                    end = p.find(">")
                    next_url = p[start:end]
                    break
        cur_url = next_url
        cur_params = None
    return items

# ---------------------------
# Owner detection utilities
# ---------------------------
def get_authenticated_username(token: Optional[str]) -> Optional[str]:
    """
    If a Personal Access Token (PAT) is provided, query /user to discover the authenticated username.

    Returns the login (username) on success, or None on failure / missing token.
    """
    if not token:
        return None
    try:
        r = request_with_auth(f"{API_BASE}/user", token)
        if r.status_code == 200:
            return r.json().get("login")
    except Exception:
        # Swallow network issues — caller will attempt other detection strategies
        pass
    return None

def owner_from_github_repository_env() -> Optional[str]:
    repo = os.environ.get("GITHUB_REPOSITORY")
    if repo and "/" in repo:
        return repo.split("/", 1)[0]
    return None

def owner_from_git_remote() -> Optional[str]:
    """
    Try to read the local git remote 'origin' URL and extract the owner from it.
    This works when the script runs inside a checked-out git repository.
    Returns the owner string or None if it can't be determined.
    """
    try:
        res = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, check=True)
        url = res.stdout.strip()
        if not url:
            return None
        # Match common GitHub formats: git@github.com:owner/repo.git or https://github.com/owner/repo.git
        m = re.search(r"github\.com[:/]+([^/]+)/[^/]+(?:\.git)?$", url)
        if m:
            return m.group(1)
    except Exception:
        # If git isn't present or command fails, return None and let other detection methods run
        pass
    return None

def detect_owner(provided_owner: Optional[str], token_env: str) -> str:
    """
    Determine which GitHub owner (username/organization) to operate on.

    Detection priority:
      1) CLI --owner argument (explicit)
      2) GITHUB_REPOSITORY environment variable (Actions)
      3) PAT -> /user (token-based detection)
      4) local git remote 'origin'
      5) interactive prompt (when run in a TTY)

    Raises RuntimeError if none of the methods yield a value.
    """
    if provided_owner:
        return provided_owner
    env_owner = owner_from_github_repository_env()
    if env_owner:
        print(f"Detected owner from GITHUB_REPOSITORY: {env_owner}")
        return env_owner
    token = os.environ.get(token_env)
    auth_user = get_authenticated_username(token) if token else None
    if auth_user:
        print(f"Detected owner from TOKEN (/user): {auth_user}")
        return auth_user
    git_owner = owner_from_git_remote()
    if git_owner:
        print(f"Detected owner from git remote: {git_owner}")
        return git_owner
    # If interactive tty is available, ask the user
    if sys.stdin and sys.stdin.isatty():
        o = input("Could not auto-detect GitHub owner. Enter GitHub username: ").strip()
        if o:
            return o
    raise RuntimeError("Unable to determine GitHub owner automatically. Provide --owner or set TOKEN/GITHUB_REPOSITORY or run inside a git repo.")

# ---------------------------
# Fetch repos & traffic
# ---------------------------
def fetch_all_repos(owner: str, token: Optional[str]) -> List[Dict[str, Any]]:
    """
    Retrieve the list of repositories for `owner`.

    If the provided token authenticates as the same owner, use the /user/repos endpoint
    so private repositories are visible when the token has `repo` scope.

    Otherwise, use /users/<owner>/repos which returns only public repositories.
    """
    auth_user = get_authenticated_username(token) if token else None
    if auth_user and auth_user.lower() == owner.lower():
        # Authenticated as the owner — we can request user's repos including private (if the token permits)
        url = f"{API_BASE}/user/repos"
        params = {"per_page": 100, "sort": "pushed"}
    else:
        # Unauthenticated or different user — request public repos for the owner
        url = f"{API_BASE}/users/{owner}/repos"
        params = {"per_page": 100, "type": "owner", "sort": "pushed"}
    print(f"Fetching repos from: {url} (authenticated as: {auth_user})")
    repos = paginate(url, token=token, params=params)
    print(f"Found {len(repos)} repos.")
    return repos

def fetch_clone_stats(owner: str, repo_name: str, token: Optional[str]) -> Dict[str, Optional[int]]:
    """
    Fetch clone traffic statistics for a specific repo using:
      GET /repos/{owner}/{repo}/traffic/clones

    Returns a dict with keys:
      - "count": total clones in the last ~14 days or None if unavailable
      - "uniques": unique cloners in same window or None

    If the API returns a non-200 status the function prints a friendly message and
    returns {"count": None, "uniques": None}.
    """
    url = f"{API_BASE}/repos/{owner}/{repo_name}/traffic/clones"
    try:
        r = request_with_auth(url, token)
        if r.status_code == 200:
            d = r.json()
            return {"count": d.get("count"), "uniques": d.get("uniques")}
        else:
            # Typical cases: 401 (unauthorized) or 403 (forbidden) when token doesn't have scope
            print(f"  traffic/clones unavailable for {repo_name}: HTTP {r.status_code}")
            return {"count": None, "uniques": None}
    except Exception as e:
        # Network or unexpected JSON parse errors
        print(f"  error fetching traffic for {repo_name}: {e}")
        return {"count": None, "uniques": None}

def fetch_download_stats(owner: str, repo_name: str, token: Optional[str]) -> Optional[int]:
    """
    Fetch total download counts for all releases of a specific repo using:
      GET /repos/{owner}/{repo}/releases

    Sums download counts from all assets across all releases.
    Returns total download count or None if unavailable.

    If the API returns a non-200 status or the repo has no releases,
    the function prints a friendly message and returns None.
    
    Note: GitHub only tracks downloads for release assets, not for repo ZIP downloads.
    """
    url = f"{API_BASE}/repos/{owner}/{repo_name}/releases"
    try:
        releases = paginate(url, token)
        total_downloads = 0
        total_assets = 0
        release_count = len(releases)
        
        for release in releases:
            assets = release.get("assets", [])
            for asset in assets:
                download_count = asset.get("download_count", 0)
                total_downloads += download_count
                total_assets += 1
        
        if release_count == 0:
            print(f"  No releases found for {repo_name} - downloads require published releases with assets")
            return None
        elif total_assets == 0:
            print(f"  {repo_name} has {release_count} release(s) but no downloadable assets - downloads show N/A")
            return None
        else:
            print(f"  {repo_name}: {total_downloads} downloads from {total_assets} assets in {release_count} releases")
            return total_downloads
    except Exception as e:
        # Network or unexpected JSON parse errors
        print(f"  error fetching downloads for {repo_name}: {e}")
        return None

# ---------------------------
# History persistence (SQLite)
# ---------------------------
DB_PATH = "history.db"

def init_db():
    """
    Initialize the SQLite database and create the repo_clones table if it doesn't exist.
    The table includes columns for clone counts, unique clones, and download counts.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS repo_clones (
            repo_name TEXT NOT NULL,
            day TEXT NOT NULL,
            clone_count INTEGER,
            unique_clones INTEGER,
            download_count INTEGER DEFAULT 0,
            PRIMARY KEY (repo_name, day)
        )
    """)
    # Check if download_count column exists (for migration from older schema)
    cursor.execute("PRAGMA table_info(repo_clones)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'download_count' not in columns:
        cursor.execute("ALTER TABLE repo_clones ADD COLUMN download_count INTEGER DEFAULT 0")
        conn.commit()
    conn.close()

def upsert_clone_data(repo_name: str, day: str, clone_count: Optional[int], unique_clones: Optional[int], download_count: Optional[int] = 0):
    """
    Insert or update clone data for a specific repo and day.
    Uses INSERT OR REPLACE to handle existing records.
    Now includes download_count for release asset downloads.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO repo_clones (repo_name, day, clone_count, unique_clones, download_count)
        VALUES (?, ?, ?, ?, ?)
    """, (repo_name, day, clone_count, unique_clones, download_count or 0))
    conn.commit()
    conn.close()

def remove_missing_repos(current_repos: List[str]):
    """
    Remove data for repos that no longer exist in the current repo list.
    This handles the case where a repo is deleted or removed from the owner's account.
    """
    if not current_repos:
        return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    placeholders = ','.join('?' * len(current_repos))
    cursor.execute(f"""
        DELETE FROM repo_clones
        WHERE repo_name NOT IN ({placeholders})
    """, current_repos)
    conn.commit()
    conn.close()

def read_history_from_db(repo_name: str) -> List[Tuple[datetime.datetime, Optional[int], Optional[int], Optional[int]]]:
    """
    Read history from database for a specific repo.
    Returns list of (datetime, clone_count_or_None, unique_count_or_None, download_count_or_None) sorted ascending.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT day, clone_count, unique_clones, download_count
        FROM repo_clones
        WHERE repo_name = ?
        ORDER BY day ASC
    """, (repo_name,))
    rows = []
    for day_str, clone_count, unique_clones, download_count in cursor.fetchall():
        try:
            dt = datetime.datetime.fromisoformat(day_str)
            rows.append((dt, clone_count, unique_clones, download_count))
        except Exception:
            continue
    conn.close()
    return rows

def calculate_downloads_14d(repo_name: str, current_downloads: Optional[int]) -> Optional[int]:
    """
    Calculate the 14-day download count by comparing current downloads
    with the download count from 14 days ago.
    
    Returns the 14-day download count or None if not enough history.
    """
    if current_downloads is None:
        return None
    
    # Get history from database
    history = read_history_from_db(repo_name)
    if not history:
        return None
    
    # Find the entry from 14 days ago (or closest to it)
    today = datetime.datetime.utcnow().date()
    target_date = today - datetime.timedelta(days=14)
    
    # Look for an entry from around 14 days ago
    downloads_14d_ago = None
    for dt, _, _, download_count in history:
        entry_date = dt.date()
        # Find closest entry to 14 days ago
        if entry_date <= target_date:
            downloads_14d_ago = download_count
            break
    
    if downloads_14d_ago is None:
        # No data from 14 days ago, can't calculate 14-day count
        return None
    
    # Calculate the difference (downloads in the last 14 days)
    # Note: downloads are cumulative, so subtract older count from current
    download_14d = current_downloads - downloads_14d_ago
    return max(0, download_14d)  # Ensure non-negative


# ---------------------------
# Jinja2 templates (embedded)
# ---------------------------
SUMMARY_SVG_TEMPLATE = """
<svg xmlns="http://www.w3.org/2000/svg" width="{{ width }}" height="{{ height }}" viewBox="0 0 {{ width }} {{ height }}" role="img" aria-label="GitHub repository clone statistics">
<style>
  .card  { font-family: "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
  .title { font-weight: 700; font-size: 18px; fill: #0b1220; }
  .meta  { font-weight: 400; font-size: 12px; fill: #374151; opacity: 0.95; }
  .label { font-weight: 600; font-size: 12px; fill: #0b1220; }
  .count { font-weight: 700; font-size: 12px; fill: #0b1220; text-anchor: start; }
  .count-small { font-weight: 600; font-size: 11px; fill:#6b7280; text-anchor: start; }
  .muted { font-size:12px; fill:#6b7280; }

  .bar-clone { fill: #1f6feb; rx:6; }
  .bar-uniq  { fill: #06b6d4; rx:6; }
  .bar-comb  { fill: #16a34a; rx:6; }

  .bar-bg { fill: #e5e7eb; rx:6; }
  @media (prefers-color-scheme: dark) {
    .title, .meta, .label, .count, .count-small, .muted { fill: #ffffff; }
    .meta, .count-small { opacity: 0.9; }
  }
</style>

<rect x="0" y="0" width="{{ width }}" height="{{ height }}" rx="12" fill="transparent"/>
<text x="{{ padding }}" y="34" class="title card">GitHub repos — {{ owner|e }}</text>
<text x="{{ padding }}" y="54" class="meta card">Repos: {{ total_repos }} · Clones: {{ total_clones }} · Uniques: {{ total_uniques }} · Combined: {{ total_combined }} · Downloads (14d): {{ total_downloads_14d }} · Downloads (total): {{ total_downloads_all }} · {{ mode_note }}</text>

<!-- LEGEND: colored squares + labels -->
<g id="legend">
  <rect x="{{ padding }}" y="70" width="12" height="12" class="bar-clone"/>
  <text x="{{ padding + 18 }}" y="80" class="muted card">Clones (14d)</text>

  <rect x="{{ padding + 180 }}" y="70" width="12" height="12" class="bar-uniq"/>
  <text x="{{ padding + 198 }}" y="80" class="muted card">Unique cloners (14d)</text>

  <rect x="{{ padding + 420 }}" y="70" width="12" height="12" class="bar-comb"/>
  <text x="{{ padding + 438 }}" y="80" class="muted card">Combined</text>
</g>

{% set base_y = 102 %}
{% for row in rows %}
  {% set block_top = base_y + loop.index0 * per_block_h %}
  <!-- repository label -->
  <text x="{{ padding }}" y="{{ block_top }}" class="label card">{{ row.name|e }}</text>

  <!-- CLONES bar (top) -->
  <rect x="{{ bar_x }}" y="{{ block_top + 14 }}" width="{{ bar_max_width }}" height="{{ bar_h }}" class="bar-bg"/>
  <rect x="{{ bar_x }}" y="{{ block_top + 14 }}" width="{{ row.bar_w_clone }}" height="{{ bar_h }}" class="bar-clone"/>
  <text x="{{ bar_x + bar_max_width + 12 }}" y="{{ block_top + 14 + 12 }}" class="count card">{{ row.clone_label|e }}</text>

  <!-- UNIQUES bar (middle) -->
  <rect x="{{ bar_x }}" y="{{ block_top + 14 + (bar_h + bar_gap) }}" width="{{ bar_max_width }}" height="{{ bar_h }}" class="bar-bg"/>
  <rect x="{{ bar_x }}" y="{{ block_top + 14 + (bar_h + bar_gap) }}" width="{{ row.bar_w_uniq }}" height="{{ bar_h }}" class="bar-uniq"/>
  <text x="{{ bar_x + bar_max_width + 12 }}" y="{{ block_top + 14 + (bar_h + bar_gap) + 12 }}" class="count-small card">{{ row.uniq_label|e }}</text>

  <!-- COMBINED bar (bottom) -->
  <rect x="{{ bar_x }}" y="{{ block_top + 14 + 2*(bar_h + bar_gap) }}" width="{{ bar_max_width }}" height="{{ bar_h }}" class="bar-bg"/>
  <rect x="{{ bar_x }}" y="{{ block_top + 14 + 2*(bar_h + bar_gap) }}" width="{{ row.bar_w_comb }}" height="{{ bar_h }}" class="bar-comb"/>
  <text x="{{ bar_x + bar_max_width + 12 }}" y="{{ block_top + 14 + 2*(bar_h + bar_gap) + 12 }}" class="count card">{{ row.comb_label|e }}</text>
{% endfor %}

</svg>
"""

TABLE_SVG_TEMPLATE = """
<svg xmlns="http://www.w3.org/2000/svg" width="{{ table_w }}" height="{{ svg_h }}" viewBox="0 0 {{ table_w }} {{ svg_h }}" role="img" aria-label="GitHub repository clones table">
<style>
  .card { font-family: "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
  .title { font-weight:700; font-size:16px; fill: #0b1220; }
  .meta  { font-size:12px; fill:#374151; opacity:0.9; }
  .th    { font-size:12px; font-weight:700; fill:#0b1220; }
  .td    { font-size:12px; fill:#0b1220; }
  .muted { font-size:11px; fill:#6b7280; }
  .row-even { fill: #ffffff; }
  .row-odd  { fill: #f8fafc; }
  .table-border { stroke: #e6eaf2; stroke-width: 1; fill: none; }
  @media (prefers-color-scheme: dark) {
    .title, .meta, .th, .td, .muted { fill: #ffffff; }
    .row-even { fill: #0b1220; }
    .row-odd  { fill: #071026; }
    .table-border { stroke: #0f172a; }
  }
</style>
<text x="{{ padding }}" y="{{ padding + 14 }}" class="title card">GitHub repositories — {{ owner|e }}</text>
<text x="{{ padding }}" y="{{ padding + 32 }}" class="meta card">Generated: {{ generated_at }} · Mode: {{ mode_note }} · Repos: {{ total_repos }} · Clones: {{ total_clones }} · Downloads: {{ total_downloads }}</text>
<rect x="{{ tbl_x }}" y="{{ tbl_y }}" width="{{ tbl_w }}" height="{{ tbl_h }}" rx="8" class="row-even"/>
<rect x="{{ tbl_x }}" y="{{ tbl_y }}" width="{{ tbl_w }}" height="{{ tbl_h }}" class="table-border"/>
{% for col in cols %}
  <text x="{{ col.x }}" y="{{ header_y }}" class="th card">{{ col.hdr }}</text>
{% endfor %}
<line x1="{{ tbl_x }}" y1="{{ sep_y }}" x2="{{ tbl_x + tbl_w }}" y2="{{ sep_y }}" stroke="#e6eaf2" />
{% for r in rows %}
  {% set i = loop.index0 %}
  <rect x="{{ tbl_x }}" y="{{ tbl_y + row_top_offset + i*row_h }}" width="{{ tbl_w }}" height="{{ row_h }}" class="{{ 'row-even' if (i%2==0) else 'row-odd' }}" opacity="0.95"/>
  {% for col in cols %}
    {% set val = r[col.key] %}
    {% if col.key == 'name' %}
      <text x="{{ col.x }}" y="{{ tbl_y + row_top_offset + i*row_h + 16 }}" class="td card">{{ val|e }}</text>
    {% elif col.key == 'description' %}
      {% set lines = r['_desc_lines'] %}
      {% if lines|length == 0 %}
        <text x="{{ col.x }}" y="{{ tbl_y + row_top_offset + i*row_h + 16 }}" class="muted card">-</text>
      {% else %}
        <text x="{{ col.x }}" y="{{ tbl_y + row_top_offset + i*row_h + 14 }}" class="td card">{{ lines[0]|e }}</text>
        {% if lines|length > 1 %}
          <text x="{{ col.x }}" y="{{ tbl_y + row_top_offset + i*row_h + 28 }}" class="td card">{{ lines[1]|e }}</text>
        {% endif %}
      {% endif %}
    {% else %}
      <text x="{{ col.x }}" y="{{ tbl_y + row_top_offset + i*row_h + 16 }}" class="td card">{{ val|e }}</text>
    {% endif %}
  {% endfor %}
{% endfor %}
<text x="{{ padding }}" y="{{ footer_y }}" class="muted card">{{ footer_note }}</text>
</svg>
"""

HISTORY_SVG_TEMPLATE = """
<svg xmlns="http://www.w3.org/2000/svg" width="{{ width }}" height="{{ height }}" viewBox="0 0 {{ width }} {{ height }}" role="img" aria-label="GitHub repositories clone history">
<style>
  .card { font-family: "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
  .title { font-weight:700; font-size:16px; fill:#0b1220; }
  .muted { font-size:12px; fill:#6b7280; }
  .axis { font-size:11px; fill:#6b7280; }
  .line { fill:none; stroke-width:2; }
  @media (prefers-color-scheme: dark) {
    .title, .muted, .axis { fill: #ffffff; }
  }
</style>

<rect x="0" y="0" width="{{ width }}" height="{{ height }}" fill="transparent" />

<text x="18" y="28" class="title card">
  Clone history (snapshots): {{ owner|e }}
</text>
<text x="18" y="46" class="muted card">
  Monthly and yearly aggregates derived from daily snapshots (per repo).
</text>

<!-- Top: Monthly chart -->
<g transform="translate(0,96)">
  <text x="18" y="14" class="muted card">
    Monthly aggregates · months: {{ months_count }} ({{ months_start }} → {{ months_end }})
  </text>

  <!-- axes -->
  <line x1="{{ margin_left }}" y1="{{ margin_top }}"
        x2="{{ margin_left }}" y2="{{ margin_top + monthly_plot_h }}"
        stroke="#e6eaf2"/>
  <line x1="{{ margin_left }}" y1="{{ margin_top + monthly_plot_h }}"
        x2="{{ margin_left + plot_w }}" y2="{{ margin_top + monthly_plot_h }}"
        stroke="#e6eaf2"/>

  {% for s in monthly_series %}
    <polyline points="{{ s.points }}" class="line" style="stroke:{{ s.color }}"/>
    <text x="{{ margin_left + 6 }}"
          y="{{ margin_top + 14 + loop.index0 * 14 }}"
          class="axis"
          style="fill:{{ s.color }}">
      {{ s.label|e }}
    </text>
  {% endfor %}

  <text x="{{ margin_left }}"
        y="{{ margin_top + monthly_plot_h + 20 }}"
        class="axis card">{{ months_start }}</text>
  <text x="{{ margin_left + plot_w }}"
        y="{{ margin_top + monthly_plot_h + 20 }}"
        class="axis card"
        text-anchor="end">{{ months_end }}</text>
</g>

<!-- Bottom: Yearly chart -->
<g transform="translate(0,{{ 96 + monthly_plot_h + 64 }})">
  <text x="18" y="14" class="muted card">
    Yearly aggregates · years: {{ years_count }} ({{ years_start }} → {{ years_end }})
  </text>

  <!-- axes -->
  <line x1="{{ margin_left }}" y1="{{ margin_top }}"
        x2="{{ margin_left }}" y2="{{ margin_top + yearly_plot_h }}"
        stroke="#e6eaf2"/>
  <line x1="{{ margin_left }}" y1="{{ margin_top + yearly_plot_h }}"
        x2="{{ margin_left + plot_w }}" y2="{{ margin_top + yearly_plot_h }}"
        stroke="#e6eaf2"/>

  {% for s in yearly_series %}
    <polyline points="{{ s.points }}" class="line" style="stroke:{{ s.color }}"/>
    <text x="{{ margin_left + 6 }}"
          y="{{ margin_top + 14 + loop.index0 * 14 }}"
          class="axis"
          style="fill:{{ s.color }}">
      {{ s.label|e }}
    </text>
  {% endfor %}

  <text x="{{ margin_left }}"
        y="{{ margin_top + yearly_plot_h + 20 }}"
        class="axis card">{{ years_start }}</text>
  <text x="{{ margin_left + plot_w }}"
        y="{{ margin_top + yearly_plot_h + 20 }}"
        class="axis card"
        text-anchor="end">{{ years_end }}</text>
</g>

</svg>
"""



# ---------------------------
# Rendering helpers
# ---------------------------
def render_template(template_str: str, ctx: dict) -> str:
    tpl = Template(template_str)
    return tpl.render(**ctx)

# ---------------------------
# Aggregate history helpers
# ---------------------------
def month_key(dt: datetime.datetime) -> Tuple[int, int]:
    return (dt.year, dt.month)

def aggregate_history_by_month(hist: List[Tuple[datetime.datetime, Optional[int], Optional[int], Optional[int]]]) -> List[Tuple[datetime.datetime, int, int, int]]:
    """
    Aggregate daily snapshots into monthly sums.
    Returns list of tuples: (month_dt (first-of-month), sum_clones, sum_uniques, sum_downloads) sorted ascending.
    """
    buckets = {}
    for dt, clones, uniques, downloads in hist:
        k = month_key(dt)
        if k not in buckets:
            buckets[k] = [0, 0, 0]
        buckets[k][0] += (clones or 0)
        buckets[k][1] += (uniques or 0)
        buckets[k][2] += (downloads or 0)
    # convert to sorted list of datetimes
    out = []
    for (y, m) in sorted(buckets.keys()):
        out.append((datetime.datetime(y, m, 1), buckets[(y, m)][0], buckets[(y, m)][1], buckets[(y, m)][2]))
    return out

def aggregate_history_by_year(hist: List[Tuple[datetime.datetime, Optional[int], Optional[int], Optional[int]]]) -> List[Tuple[datetime.datetime, int, int, int]]:
    """
    Aggregate daily snapshots into yearly sums.
    Returns list: (year_dt (first-of-year), sum_clones, sum_uniques, sum_downloads) sorted ascending.
    """
    buckets = {}
    for dt, clones, uniques, downloads in hist:
        y = dt.year
        if y not in buckets:
            buckets[y] = [0, 0, 0]
        buckets[y][0] += (clones or 0)
        buckets[y][1] += (uniques or 0)
        buckets[y][2] += (downloads or 0)
    out = []
    for y in sorted(buckets.keys()):
        out.append((datetime.datetime(y, 1, 1), buckets[y][0], buckets[y][1], buckets[y][2]))
    return out


# ---------------------------
# Outputs - summary SVG (stats.svg)
# ---------------------------
def generate_summary_svg_jinja(owner: str, repo_rows: List[Dict[str, Any]],
                               include_private: bool, out_path="stats.svg", top_n=6):
    """
    Render summary card with three stacked bar metrics per repo:
      - top bar: total clones (clone_count)
      - middle bar: unique cloners (clone_uniques)
      - bottom bar: combined (clone_count + clone_uniques)

    Each metric uses its own scale (max per metric) so short/long metrics are visible.
    Counts are rendered to the right of each bar. Missing values (None) are shown as 'N/A'.
    """
    # totals for header
    total_clones = sum((r.get("clone_count") or 0) for r in repo_rows)
    total_uniques = sum((r.get("clone_uniques") or 0) for r in repo_rows)
    total_combined = sum(((r.get("clone_count") or 0) + (r.get("clone_uniques") or 0)) for r in repo_rows)
    total_downloads_14d = sum((r.get("download_14d") or 0) for r in repo_rows)
    total_downloads_all = sum((r.get("download_total") or 0) for r in repo_rows)
    total_repos = len(repo_rows)

    # Sort repos by clone_count (descending) and take the top_n for the chart
    rows_sorted = sorted(repo_rows, key=lambda x: (x.get("clone_count") or 0), reverse=True)
    chart_rows = rows_sorted[:top_n]

    # sizing heuristics
    padding = 18
    CHAR_PX = 7.5
    bar_h = 18
    bar_gap = 8

    # compute label width requirement
    labels = [r.get("name") or "" for r in chart_rows]
    max_label_chars = max((len(l) for l in labels), default=0)
    name_col_width = int(max(120, min(max_label_chars * CHAR_PX + 10, 420)))

    # Build textual labels for counts (for sizing)
    clone_labels = []
    uniq_labels = []
    comb_labels = []
    for r in chart_rows:
        c = r.get("clone_count")
        u = r.get("clone_uniques")
        cstr = "N/A" if c is None else str(c)
        ustr = "N/A" if u is None else str(u)
        comb = None
        if c is None and u is None:
            comb_label = "N/A"
        else:
            # treat missing as 0 for combined label if one present
            comb_val = (c or 0) + (u or 0)
            comb_label = str(comb_val)
        clone_labels.append(cstr)
        uniq_labels.append(ustr)
        comb_labels.append(comb_label)

    all_count_labels = clone_labels + uniq_labels + comb_labels
    max_count_chars = max((len(s) for s in all_count_labels), default=1)
    count_text_w = int(max(64, max_count_chars * CHAR_PX + 12))

    # canvas width computation
    width = max(820, padding * 3 + name_col_width + 220 + count_text_w + 18)
    bar_x = padding + name_col_width + 12
    bar_max_width = int(width - bar_x - padding - count_text_w - 18)

    # per-repo block height and total height
    per_block_h = int(12 + 3*bar_h + 2*bar_gap)  # label + three bars + gaps
    height = 120 + len(chart_rows) * per_block_h

    # compute per-metric maxima (avoid zero)
    max_clones = max((r.get("clone_count") or 0) for r in chart_rows) or 1
    max_uniques = max((r.get("clone_uniques") or 0) for r in chart_rows) or 1
    max_comb = max(((r.get("clone_count") or 0) + (r.get("clone_uniques") or 0)) for r in chart_rows) or 1

    # build rows with scaled bar widths and labels
    rows_for_template = []
    for r, clab, ulab, comblab in zip(chart_rows, clone_labels, uniq_labels, comb_labels):
        c = r.get("clone_count")
        u = r.get("clone_uniques")
        cval = 0 if c is None else int(c)
        uval = 0 if u is None else int(u)
        comb_val = cval + uval

        bar_w_clone = int((cval / max_clones) * bar_max_width) if max_clones else 0
        bar_w_uniq  = int((uval / max_uniques) * bar_max_width) if max_uniques else 0
        bar_w_comb  = int((comb_val / max_comb) * bar_max_width) if max_comb else 0

        rows_for_template.append({
            "name": r.get("name") or "",
            "clone_label": clab,
            "uniq_label": ulab,
            "comb_label": comblab,
            "bar_w_clone": bar_w_clone,
            "bar_w_uniq": bar_w_uniq,
            "bar_w_comb": bar_w_comb,
        })

    ctx = {
        "owner": owner,
        "total_repos": total_repos,
        "total_clones": total_clones,
        "total_uniques": total_uniques,
        "total_combined": total_combined,
        "total_downloads_14d": total_downloads_14d,
        "total_downloads_all": total_downloads_all,
        "mode_note": "Includes private repos" if include_private else "Public repos only",
        "rows": rows_for_template,
        "width": width,
        "height": height,
        "bar_x": bar_x,
        "bar_max_width": bar_max_width,
        "bar_h": bar_h,
        "bar_gap": bar_gap,
        "per_block_h": per_block_h,
        "padding": padding,  # exposed for legend/template placement
    }

    svg = render_template(SUMMARY_SVG_TEMPLATE, ctx)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"Wrote summary svg to {out_path}")


# ---------------------------
# Outputs - full table SVG (REPO_CLONES.svg)
# ---------------------------
def generate_table_svg_jinja(owner: str, repo_rows: List[Dict[str, Any]], include_private: bool,
                             out_path="REPO_CLONES.svg", max_rows: Optional[int] = None):
    """
    Generate a full table as an SVG.

    The produced table contains columns:
      - Repo (name)
      - Description (first two lines, truncated)
      - Stars
      - Forks
      - Open issues
      - Last push (ISO->readable timestamp)
      - Clones (14d)
      - Unique clones (14d)
      - Downloads (all releases)

    Column widths are computed dynamically from the data with min/max clamping so
    the SVG remains visually stable even with unusually long names/descriptions.
    """

    # Copy rows (optionally truncate to max_rows)
    rows = repo_rows[:] if max_rows is None else repo_rows[:max_rows]
    total_repos = len(repo_rows)
    total_clones = sum((r.get("clone_count") or 0) for r in repo_rows)
    total_downloads = sum((r.get("download_count") or 0) for r in repo_rows)

    # Definition of columns: (key, header, min_px, max_px, is_numeric, wrap_chars_for_text)
    COLS = [
        ("name", "Repo", 140, 420, False, 30),
        ("description", "Description", 220, 600, False, 60),
        ("language", "Language", 80, 140, False, 20),
        ("stargazers_count", "Stars", 56, 80, True, 0),
        ("forks_count", "Forks", 56, 80, True, 0),
        ("watchers_count", "Watchers", 56, 80, True, 0),
        ("open_issues_count", "Open issues", 82, 110, True, 0),
        ("pushed_at", "Last push", 140, 200, False, 20),
        ("clone_count", "Clones (14d)", 90, 140, True, 0),
        ("clone_uniques", "Unique clones (14d)", 110, 160, True, 0),
        ("download_14d", "Downloads (14d)", 110, 160, True, 0),
        ("download_total", "Downloads (total)", 110, 160, True, 0),
    ]

    CHAR_PX = 7.2

    def cell_text(col_key, r):
        """
        Return the appropriate display string for a given column key and repo dict.
        Handles formatting for dates and the clone/download columns which may be None.
        """
        if col_key == "name":
            return r.get("name") or ""
        if col_key == "description":
            return r.get("description") or ""
        if col_key == "pushed_at":
            s = r.get("pushed_at") or ""
            return s[:19].replace("T", " ") if s else ""
        if col_key == "clone_count":
            v = r.get("clone_count")
            return str(v) if v is not None else "N/A"
        if col_key == "clone_uniques":
            v = r.get("clone_uniques")
            return str(v) if v is not None else "N/A"
        if col_key == "download_14d":
            v = r.get("download_14d")
            return str(v) if v is not None else "N/A"
        if col_key == "download_total":
            v = r.get("download_total")
            return str(v) if v is not None else "N/A"
        return str(r.get(col_key) or "")

    # Measure the character requirements for each column from the data, capped by wrap heuristics
    col_char_max = {}
    for key, hdr, min_px, max_px, isnumeric, wrap_chars in COLS:
        if isnumeric:
            # For numeric columns base sizing on the max number of digits observed
            col_char_max[key] = max(len(str(cell_text(key, r))) for r in rows) if rows else len(hdr)
        else:
            # For text columns, estimate using header length and data samples; cap by wrap_chars
            maxchars = len(hdr)
            for r in rows:
                c = cell_text(key, r)
                if not c:
                    continue
                # Limit extremely long strings to a conservative multiplier to avoid huge widths
                maxchars = max(maxchars, min(len(c), wrap_chars * 2))
            col_char_max[key] = maxchars

    # Convert char counts to pixel widths respecting each column's min/max constraints
    col_px = {}
    for key, hdr, min_px, max_px, isnumeric, wrap_chars in COLS:
        if isnumeric:
            chars = col_char_max[key] + 1
            estimated = int(chars * CHAR_PX + 10)
            col_px[key] = max(min_px, min(estimated, max_px))
        else:
            chars = col_char_max[key]
            estimated = int(chars * CHAR_PX + 18)
            col_px[key] = max(min_px, min(estimated, max_px))

    # Table layout parameters
    padding = 18
    header_h = 48
    row_h = 26
    gap = 8
    table_x = padding
    table_y = padding + 12

    # Compute overall table width and height
    table_w = sum(col_px[k] for k, *_ in [(c[0],) for c in COLS]) + gap * (len(COLS) - 1) + padding * 2
    table_w = max(table_w, 760)

    visible_rows = rows
    table_h = header_h + row_h * len(visible_rows) + padding * 2
    svg_h = table_y + table_h + padding

    # Build column metadata for template
    col_positions = []
    cur_x = table_x + 12
    for key, hdr, min_px, max_px, isnumeric, wrap_chars in COLS:
        col_positions.append({"key": key, "hdr": hdr, "x": int(cur_x), "px": col_px[key]})
        cur_x += col_px[key] + gap

    # Build row display data (including description wrap)
    rows_display = []
    for r in visible_rows:
        desc = (r.get("description") or "").strip()
        wrap_limit = next((w for (k,_,_,_,_,w) in COLS if k == "description"), 60)
        if not desc:
            desc_lines = []
        else:
            words = desc.split()
            line1 = ""
            line2 = ""
            cur = ""
            for w in words:
                if len(cur) + len(w) + 1 <= wrap_limit:
                    cur = (cur + " " + w).strip()
                else:
                    if not line1:
                        line1 = cur or w
                        cur = w
                    else:
                        line2 = cur + " " + w if cur else w
                        cur = ""
                        break
            if not line1 and cur:
                line1 = cur
            if not line2 and cur and len(line1) + len(cur) <= wrap_limit * 2:
                if not line2:
                    line2 = cur
            def trunc(s, n):
                return (s[:n - 1] + "…") if len(s) > n else s
            line1 = trunc(line1, wrap_limit)
            line2 = trunc(line2, wrap_limit)
            desc_lines = [line1] if line1 else []
            if line2:
                desc_lines.append(line2)
        # Prepare numeric/text fields for template (use humanized values)
        rows_display.append({
            "name": r.get("name") or "",
            "description": r.get("description") or "",
            "_desc_lines": desc_lines,
            "language": r.get("language") or "",
            "stargazers_count": r.get("stargazers_count", 0),
            "forks_count": r.get("forks_count", 0),
            "watchers_count": r.get("watchers_count", r.get("watchers", 0)),
            "open_issues_count": r.get("open_issues_count", 0),
            "pushed_at": (r.get("pushed_at") or "")[:19].replace("T", " "),
            "clone_count": r.get("clone_count") if r.get("clone_count") is not None else "N/A",
            "clone_uniques": r.get("clone_uniques") if r.get("clone_uniques") is not None else "N/A",
            "download_14d": r.get("download_14d") if r.get("download_14d") is not None else "N/A",
            "download_total": r.get("download_total") if r.get("download_total") is not None else "N/A",
        })

    ctx = {
        "owner": owner,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "mode_note": "Includes private repos" if include_private else "Public repos only",
        "total_repos": total_repos,
        "total_clones": total_clones,
        "total_downloads": total_downloads,
        "cols": col_positions,
        "rows": rows_display,
        "padding": padding,
        "tbl_x": table_x,
        "tbl_y": table_y,
        "tbl_w": table_w - padding*2,
        "tbl_h": table_h,
        "table_w": table_w,
        "svg_h": svg_h,
        "header_y": table_y + 28,
        "sep_y": table_y + 28,
        "row_top_offset": 28,
        "row_h": row_h,
        "footer_note": "Note: GitHub traffic/clones shows recent ~14 days and requires owner access. Downloads require published releases with assets - ZIP downloads from the repo page are not tracked. 'N/A' indicates missing data or insufficient permissions.",
    }
    svg = render_template(TABLE_SVG_TEMPLATE, ctx)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"Wrote table svg to {out_path}")

def generate_history_svg(owner: str, repo_rows: List[Dict[str, Any]], out_path="history.svg", top_n=6):
    """
    Builds monthly and yearly aggregated series from the stored DB snapshots and
    renders two stacked SVG charts: monthly (top) and yearly (bottom).
    """
    # choose top_n repos by latest clone_count
    rows_sorted = sorted(repo_rows, key=lambda x: (x.get("clone_count") or 0), reverse=True)
    chart_repos = rows_sorted[:top_n]

    colors = ["#1f6feb", "#16a34a", "#f97316", "#e11d48", "#a78bfa", "#06b6d4"]
    alt = ["#60a5fa", "#34d399", "#fb923c", "#fb7185", "#c4b5fd", "#67e8f9"]

    def color_for(idx, kind="clones"):
        if kind == "clones":
            return colors[idx % len(colors)]
        return alt[idx % len(alt)]

    monthly_series = []  # each entry: {'label':..., 'points':..., 'color':...}
    yearly_series = []

    # collect all monthly/yearly x-keys to compute shared ranges
    all_month_keys = []
    all_year_keys = []

    per_repo_monthly = {}
    per_repo_yearly = {}

    for idx, r in enumerate(chart_repos):
        name = r.get("name") or ""
        hist = read_history_from_db(name)
        if not hist:
            continue
        monthly = aggregate_history_by_month(hist)
        yearly = aggregate_history_by_year(hist)
        if monthly:
            per_repo_monthly[name] = monthly
            all_month_keys.extend([dt for dt,_,_,_ in monthly])
        if yearly:
            per_repo_yearly[name] = yearly
            all_year_keys.extend([dt for dt,_,_,_ in yearly])

    # Sort and deduplicate keys
    all_month_keys = sorted(list(dict.fromkeys(all_month_keys)))
    all_year_keys = sorted(list(dict.fromkeys(all_year_keys)))

    # mapping functions for monthly (discrete x positions)
    width = 900
    margin_left = 80
    margin_top = 24
    plot_w = width - margin_left - 40

    monthly_plot_h = 180
    yearly_plot_h = 120

    months_count = len(all_month_keys) or 0
    years_count = len(all_year_keys) or 0

    def month_tx(dt):
        if months_count <= 1:
            return margin_left + plot_w / 2
        idx = all_month_keys.index(dt)
        return margin_left + (idx / (months_count - 1)) * plot_w

    def year_tx(dt):
        if years_count <= 1:
            return margin_left + plot_w / 2
        idx = all_year_keys.index(dt)
        return margin_left + (idx / (years_count - 1)) * plot_w

    # value ranges: compute global vmin/vmax for monthly and yearly separately
    monthly_vals = []
    yearly_vals = []
    for monthly in per_repo_monthly.values():
        for dt, c, u, d in monthly:
            monthly_vals.append(c or 0)
            monthly_vals.append(u or 0)
            monthly_vals.append(d or 0)
    for yearly in per_repo_yearly.values():
        for dt, c, u, d in yearly:
            yearly_vals.append(c or 0)
            yearly_vals.append(u or 0)
            yearly_vals.append(d or 0)

    m_vmin = min(monthly_vals) if monthly_vals else 0
    m_vmax = max(monthly_vals) if monthly_vals and max(monthly_vals) > 0 else 1
    y_vmin = min(yearly_vals) if yearly_vals else 0
    y_vmax = max(yearly_vals) if yearly_vals and max(yearly_vals) > 0 else 1

    def map_y(v, vmin, vmax, plot_h):
        if vmax == vmin:
            return margin_top + plot_h / 2
        return margin_top + plot_h - ((v - vmin) / (vmax - vmin)) * plot_h

    # build monthly series (three lines per repo: clones, uniques & downloads)
    for idx, (name, monthly) in enumerate(per_repo_monthly.items()):
        # clones
        pts_sorted = sorted(monthly, key=lambda x: x[0])
        points_clone = " ".join(f"{int(month_tx(dt))},{int(map_y(c or 0, m_vmin, m_vmax, monthly_plot_h))}" for dt, c, u, d in pts_sorted)
        monthly_series.append({
            "label": f"{name} — clones (latest {pts_sorted[-1][1]})",
            "points": points_clone,
            "color": color_for(idx, "clones")
        })
        # uniques
        points_uniq = " ".join(f"{int(month_tx(dt))},{int(map_y(u or 0, m_vmin, m_vmax, monthly_plot_h))}" for dt, c, u, d in pts_sorted)
        monthly_series.append({
            "label": f"{name} — uniques (latest {pts_sorted[-1][2]})",
            "points": points_uniq,
            "color": color_for(idx, "uniques")
        })
        # downloads
        points_dl = " ".join(f"{int(month_tx(dt))},{int(map_y(d or 0, m_vmin, m_vmax, monthly_plot_h))}" for dt, c, u, d in pts_sorted)
        monthly_series.append({
            "label": f"{name} — downloads (latest {pts_sorted[-1][3]})",
            "points": points_dl,
            "color": "#f59e0b"  # amber/orange color for downloads
        })

    # build yearly series (three lines per repo: clones, uniques & downloads)
    for idx, (name, yearly) in enumerate(per_repo_yearly.items()):
        pts_sorted = sorted(yearly, key=lambda x: x[0])
        points_clone = " ".join(f"{int(year_tx(dt))},{int(map_y(c or 0, y_vmin, y_vmax, yearly_plot_h))}" for dt, c, u, d in pts_sorted)
        yearly_series.append({
            "label": f"{name} — clones (latest {pts_sorted[-1][1]})",
            "points": points_clone,
            "color": color_for(idx, "clones")
        })
        points_uniq = " ".join(f"{int(year_tx(dt))},{int(map_y(u or 0, y_vmin, y_vmax, yearly_plot_h))}" for dt, c, u, d in pts_sorted)
        yearly_series.append({
            "label": f"{name} — uniques (latest {pts_sorted[-1][2]})",
            "points": points_uniq,
            "color": color_for(idx, "uniques")
        })
        points_dl = " ".join(f"{int(year_tx(dt))},{int(map_y(d or 0, y_vmin, y_vmax, yearly_plot_h))}" for dt, c, u, d in pts_sorted)
        yearly_series.append({
            "label": f"{name} — downloads (latest {pts_sorted[-1][3]})",
            "points": points_dl,
            "color": "#f59e0b"  # amber/orange color for downloads
        })

    # Prepare human-friendly labels for start/end
    months_start = all_month_keys[0].strftime("%Y-%m") if all_month_keys else "-"
    months_end = all_month_keys[-1].strftime("%Y-%m") if all_month_keys else "-"
    years_start = all_year_keys[0].strftime("%Y") if all_year_keys else "-"
    years_end = all_year_keys[-1].strftime("%Y") if all_year_keys else "-"

    ctx = {
        "owner": owner,
        "monthly_series": monthly_series,
        "yearly_series": yearly_series,
        "width": width,
        "height": 96 + monthly_plot_h + 64 + yearly_plot_h + 40,
        "margin_left": margin_left,
        "margin_top": margin_top,
        "plot_w": plot_w,
        "monthly_plot_h": monthly_plot_h,
        "yearly_plot_h": yearly_plot_h,
        "months_count": months_count,
        "years_count": years_count,
        "months_start": months_start,
        "months_end": months_end,
        "years_start": years_start,
        "years_end": years_end,
    }

    svg = render_template(HISTORY_SVG_TEMPLATE, ctx)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"Wrote history svg to {out_path}")


# ---------------------------
# Git commit & push
# ---------------------------
def git_commit_and_push(files: List[str], commit_message: str = "chore: update repo stats", token_env: Optional[str] = None, branch: Optional[str] = None, force_push: bool = False):
    """
    Commit and push a list of files to the repository.

    Behavior:
      - If `git` is not available the function returns early.
      - Sets local git identity to `actions@github.com` / `github-actions[bot]` to avoid CI commit failures.
      - If `branch` is specified, switches to that branch (creating it if needed), commits files, and pushes.
        After push, returns to the original branch.
      - If `force_push` is True, uses --force-with-lease for the push.
      - Adds the files, attempts to commit; if there's nothing to commit the function returns.
      - If token_env is provided and a token exists in that environment variable, the remote origin URL
        is temporarily rewritten to include the token in the URL (https://<token>@github.com/owner/repo.git)
        so the push succeeds in CI environments where credentials are not persisted.
      - The original origin URL is restored afterwards.
    """
    try:
        subprocess.run(["git", "--version"], check=True, stdout=subprocess.DEVNULL)
    except Exception:
        print("git not found; skipping push.")
        return
    
    # Check if we are inside a git repository
    try:
        subprocess.run(["git", "rev-parse", "--git-dir"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        print("Not inside a git repository; skipping commit and push.")
        return
    
    # Configure local git identity (important in CI)
    try:
        subprocess.run(["git", "config", "--local", "user.email", "actions@github.com"], check=True)
        subprocess.run(["git", "config", "--local", "user.name", "github-actions[bot]"], check=True)
    except Exception:
        # If config fails silently, continue — commit might still succeed if global identity set
        pass

    # Handle branch switching if requested
    original_branch = None
    if branch:
        try:
            # Get current branch name
            res = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True, check=True)
            original_branch = res.stdout.strip()
            
            # Check if target branch exists
            res = subprocess.run(["git", "rev-parse", "--verify", branch], capture_output=True, stderr=subprocess.DEVNULL)
            branch_exists = res.returncode == 0
            
            if branch_exists:
                # Branch exists, check it out
                subprocess.run(["git", "checkout", branch], check=True)
            else:
                # Create new orphan branch (no history)
                subprocess.run(["git", "checkout", "--orphan", branch], check=True)
                # Remove all files from staging (orphan branch starts with all files staged)
                subprocess.run(["git", "rm", "-rf", "."], check=True, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"Failed to switch to branch {branch}: {e}")
            return

    # Stage the files for commit (raises on failure)
    subprocess.run(["git", "add"] + files, check=True)
    try:
        # Attempt commit; if there are no changes this raises CalledProcessError and we report no changes.
        subprocess.run(["git", "commit", "-m", commit_message], check=True)
    except subprocess.CalledProcessError:
        print("No changes to commit.")
        # Return to original branch if we switched
        if original_branch:
            subprocess.run(["git", "checkout", original_branch], check=True)
        return
    
    # Build push command
    push_cmd = ["git", "push"]
    if force_push:
        push_cmd.append("--force-with-lease")
    if branch:
        push_cmd.extend(["origin", branch])
    
    # Push handling: if token_env is provided, use it to push over HTTPS in CI
    if token_env:
        token = os.environ.get(token_env)
        if not token:
            print(f"Token env var {token_env} not set; attempting normal push.")
            subprocess.run(push_cmd, check=True)
            # Return to original branch if we switched
            if original_branch:
                subprocess.run(["git", "checkout", original_branch], check=True)
            return
        try:
            res = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, check=True)
            origin_url = res.stdout.strip()
            if origin_url.startswith("https://"):
                # Insert token into URL: https://<token>@github.com/owner/repo.git
                parsed = urlparse(origin_url)
                token_url = f"https://{token}@{parsed.netloc}{parsed.path}"
                subprocess.run(["git", "remote", "set-url", "origin", token_url], check=True)
                try:
                    subprocess.run(push_cmd, check=True)
                finally:
                    # Restore original remote URL even if push fails
                    subprocess.run(["git", "remote", "set-url", "origin", origin_url], check=True)
            else:
                # Non-HTTPS remote (ssh) — just attempt push (CI may have SSH key)
                subprocess.run(push_cmd, check=True)
        except Exception as e:
            print(f"Push failed: {e}")
        finally:
            # Return to original branch if we switched
            if original_branch:
                subprocess.run(["git", "checkout", original_branch], check=True)
    else:
        # No token env specified — normal push
        try:
            subprocess.run(push_cmd, check=True)
        finally:
            # Return to original branch if we switched
            if original_branch:
                subprocess.run(["git", "checkout", original_branch], check=True)

# ---------------------------
# CLI entrypoint
# ---------------------------
def main():
    """
    Command-line entrypoint.

    Sets up argument parsing, owner detection, repo fetching, clone stats collection,
    generates the two SVG outputs, and optionally commits & pushes them when --push is provided.
    """
    parser = argparse.ArgumentParser(description="Generate GitHub repo clones summary (SVGs) with history.")
    parser.add_argument("--owner", help="GitHub username (owner). If omitted, detect automatically.")
    parser.add_argument("--push", action="store_true", help="Commit & push generated files back to this repo")
    parser.add_argument("--include-private", action="store_true", help="Include private repositories (opt-in)")
    parser.add_argument("--token-env", default="TOKEN", help="Environment variable name for PAT (default: TOKEN)")
    parser.add_argument("--svg-out", default="stats.svg", help="Summary SVG filename")
    parser.add_argument("--table-out", default="REPO_CLONES.svg", help="Full table SVG filename")
    parser.add_argument("--history-out", default="history.svg", help="History SVG filename")
    parser.add_argument("--top-n", default=6, type=int, help="Number of top repos to show in summary & history SVGs")
    args = parser.parse_args()

    # Determine whether to include private repos: CLI flag overrides environment variable
    env_include = os.environ.get("INCLUDE_PRIVATE", "").lower() == "true"
    include_private = args.include_private or env_include

    token = os.environ.get(args.token_env)
    try:
        owner = detect_owner(args.owner, args.token_env)
    except Exception as e:
        print("Owner detection failed:", e)
        sys.exit(1)

    # Fetch repository list for the owner
    try:
        repos = fetch_all_repos(owner, token)
    except Exception as e:
        print("Failed to fetch repos:", e)
        sys.exit(1)

    # Filter out private repos by default (safe public-facing default)
    if not include_private:
        repos = [r for r in repos if not r.get("private")]
        print(f"Filtering to public repos only — {len(repos)} repos will be processed.")
    else:
        print(f"Including private repos — {len(repos)} repos will be processed (ensure TOKEN has repo scope).")

    # Initialize database
    init_db()

    # Build the local repo_rows list with metadata + clone stats + download stats fetch
    repo_rows = []
    today = datetime.datetime.utcnow().date().isoformat()
    current_repo_names = []
    for r in repos:
        name = r.get("name")
        current_repo_names.append(name)
        # Fetch clone stats (14-day window)
        stats = fetch_clone_stats(owner, name, token)
        # Fetch download stats (all releases)
        downloads_total = fetch_download_stats(owner, name, token)
        # Calculate 14-day downloads (requires historical data)
        downloads_14d = calculate_downloads_14d(name, downloads_total)
        row = {
            "name": name,
            "description": r.get("description"),
            "language": r.get("language"),
            "stargazers_count": r.get("stargazers_count", 0),
            "forks_count": r.get("forks_count", 0),
            "watchers_count": r.get("watchers_count", r.get("watchers", 0)),
            "open_issues_count": r.get("open_issues_count", 0),
            "pushed_at": r.get("pushed_at"),
            "clone_count": stats.get("count"),
            "clone_uniques": stats.get("uniques"),
            "download_14d": downloads_14d,
            "download_total": downloads_total,
        }
        repo_rows.append(row)
        # persist snapshot to database (using day as key)
        upsert_clone_data(name, today, row["clone_count"], row["clone_uniques"], row["download_total"])
        # small throttle between API calls to be polite to GitHub and avoid bursts
        time.sleep(0.12)

    # Remove repos that no longer exist
    remove_missing_repos(current_repo_names)

    # Generate the full table SVG
    try:
        print("Generating full table SVG ->", args.table_out)
        generate_table_svg_jinja(owner, repo_rows, include_private, out_path=args.table_out)
    except Exception as e:
        print("ERROR generating table SVG:", e)
        sys.exit(1)

    # Generate the compact summary SVG
    try:
        print("Generating summary SVG ->", args.svg_out)
        generate_summary_svg_jinja(owner, repo_rows, include_private, out_path=args.svg_out, top_n=args.top_n)
    except Exception as e:
        print("ERROR generating summary SVG:", e)
        sys.exit(1)

    try:
        print("Generating history SVG ->", args.history_out)
        generate_history_svg(owner, repo_rows, out_path=args.history_out, top_n=args.top_n)
    except Exception as e:
        print("ERROR generating history SVG:", e)
        sys.exit(1)

    # If requested, stage/commit/push generated files back to the repository
    if args.push:
        # SVG files go to main branch
        svg_files = [args.table_out, args.svg_out, args.history_out]
        svg_files = [f for f in svg_files if os.path.exists(f)]
        
        # Database goes to history-db branch
        if os.path.exists(DB_PATH):
            print(f"Committing {DB_PATH} to history-db branch")
            git_commit_and_push([DB_PATH], commit_message="chore: update clone history database", token_env=args.token_env, branch="history-db", force_push=True)
        
        # Commit SVG files to main/current branch
        if svg_files:
            print("Committing and pushing SVG files:", svg_files)
            git_commit_and_push(svg_files, commit_message="chore: update repo clones summary (SVGs)", token_env=args.token_env)
            print("Push complete.")
        else:
            print("No SVG files to commit.")
    else:
        # When not pushing, show which files were generated locally
        generated = [f for f in [args.table_out, args.svg_out, args.history_out] if os.path.exists(f)]
        print("Run complete. Files generated (not pushed):", generated)

if __name__ == "__main__":
    main()
