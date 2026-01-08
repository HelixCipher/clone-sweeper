#!/usr/bin/env python3
"""
clone_sweeper.py

Generates REPO_CLONES.svg (full table) and stats.svg (summary card) for a GitHub owner.

Defaults / behaviour summary:
 - By default only public repositories are processed. To include private repos set:
       export INCLUDE_PRIVATE=true
   or pass CLI flag:
       python clone_sweeper.py --include-private
 - The Personal Access Token (PAT) environment variable name defaults to `TOKEN`.
   You can change that at runtime with `--token-env`.
 - The script can auto-detect the owner from:
     1) --owner CLI arg
     2) GITHUB_REPOSITORY env var (set when running in GitHub Actions)
     3) the authenticated user returned by the PAT (/user)
     4) git remote 'origin' URL when running inside a cloned repo
 - Outputs:
     - REPO_CLONES.svg -> full table with columns similar to the old markdown table
     - stats.svg        -> compact summary card with top-N repos and a small bar chart
 - When called with --push the script will `git add` + `git commit` + `git push` the generated SVGs.

This file intentionally prioritizes readability and defensive handling:
 - All external strings are escaped before embedding in XML/SVG using escape_xml()
 - The script sleeps 0.12s between per-repo API calls to avoid hitting API bursts.
 - Git commit/push uses the repo remote and temporarily rewrites the origin URL to include the PAT
   for CI environments where `persist-credentials: false` is used.
"""
import os
import sys
import argparse
import datetime
import requests
import time
import subprocess
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse
import re

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
    """
    When running inside GitHub Actions the environment variable GITHUB_REPOSITORY is available
    in the format "owner/repo". Extract and return the owner portion.
    """
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

# ---------------------------
# Outputs - summary SVG (stats.svg)
# ---------------------------
def generate_svg(owner: str, repo_rows: List[Dict[str, Any]], include_private: bool,
                 out_path="stats.svg", top_n=6):
    """
    Create a compact summary SVG (stats.svg) that shows top_n repositories by clone_count.

    The summary SVG includes:
      - title and meta line (total repos, reported clones, mode)
      - a simple horizontal bar chart for top_n repos
      - counts drawn to the right of the bars (avoids contrast issues)

    Layout decisions:
      - Column sizing is computed with conservative char->px approximations so labels don't overlap bars.
      - Colors and @media (prefers-color-scheme: dark) rules are used so text adapts to light/dark themes.
    """
    total_clones = sum((r.get("clone_count") or 0) for r in repo_rows)
    total_repos = len(repo_rows)

    # Sort repos by clone_count (descending) and take the top_n for the chart
    rows_sorted = sorted(repo_rows, key=lambda x: (x.get("clone_count") or 0), reverse=True)
    chart_rows = rows_sorted[:top_n]

    # Layout parameters (tweak these if you want different sizing)
    padding = 18
    title_h = 52
    row_h = 30

    # Approximate character width (px) used to estimate column widths
    CHAR_PX = 7.5
    min_name_col = 120
    max_name_col = 420
    min_bar_area = 220
    right_margin_for_counts = 18

    def safe_label(name: str) -> str:
        """
        Truncate long repo names for display purposes in the compact card.
        """
        return name if len(name) <= 48 else name[:45] + "…"

    # Compute the name column width based on longest label we will render
    labels = [safe_label(r.get("name") or "") for r in chart_rows]
    max_label_chars = max((len(l) for l in labels), default=0)
    name_col_width = int(max(min_name_col, min(max_label_chars * CHAR_PX + 10, max_name_col)))

    # Compute the width needed to render counts (right-hand side)
    counts = [str(r.get("clone_count") or 0) for r in chart_rows]
    max_count_chars = max((len(c) for c in counts), default=1)
    count_text_w = int(max(48, max_count_chars * CHAR_PX + 8))

    # Compute canvas width iteratively to allow a reasonable bar area
    width = max(760, padding * 3 + name_col_width + min_bar_area + count_text_w + right_margin_for_counts)
    for _ in range(3):
        bar_x = padding + name_col_width + 12
        bar_max_width = width - bar_x - padding - count_text_w - right_margin_for_counts
        if bar_max_width < 80:
            # Expand the canvas if bar area is too small
            width += (120 - bar_max_width)
            continue
        required_width = padding * 3 + name_col_width + max(min_bar_area, bar_max_width) + count_text_w + right_margin_for_counts
        if required_width > width:
            width = required_width
            continue
        break

    # Compute canvas height: vertical space for header + rows + padding
    height = title_h + padding + row_h * max(len(chart_rows), 1) + padding
    # Avoid divide-by-zero when no clone counts are present
    max_val = max((r.get("clone_count") or 0) for r in chart_rows) or 1

    # Begin building SVG as a list of strings for efficient concatenation
    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{int(width)}" height="{int(height)}" viewBox="0 0 {int(width)} {int(height)}" role="img" aria-label="GitHub repository clone statistics">')
    svg.append("""
<style>
  .card  { font-family: "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
  .title { font-weight: 700; font-size: 18px; fill: #0b1220; }
  .meta  { font-weight: 400; font-size: 12px; fill: #374151; opacity: 0.95; }
  .label { font-weight: 500; font-size: 12px; fill: #0b1220; }
  .count { font-weight: 700; font-size: 12px; fill: #0b1220; }
  @media (prefers-color-scheme: dark) {
    .title, .meta, .label, .count { fill: #ffffff; }
    .meta { opacity: 0.9; }
  }
</style>
""")
    # Transparent background: GitHub will show it against the page background
    svg.append(f'<rect x="0" y="0" width="{int(width)}" height="{int(height)}" rx="12" fill="transparent"/>')
    svg.append(f'<text x="{padding}" y="{padding + 16}" class="title card">GitHub repos — {escape_xml(owner)}</text>')
    svg.append(f'<text x="{padding}" y="{padding + 36}" class="meta card">Total repos: {total_repos} · Total reported clones: {total_clones} · {"Includes private repos" if include_private else "Public repos only"}</text>')

    # Chart drawing area origin
    y_start = padding + title_h
    bar_x = padding + name_col_width + 12
    bar_max_width = width - bar_x - padding - count_text_w - right_margin_for_counts

    # Draw each chart row: name | bar background | bar foreground | right-hand count
    for i, r in enumerate(chart_rows):
        y = y_start + i * row_h
        name = escape_xml(safe_label(r.get("name") or ""))
        count = r.get("clone_count") or 0
        bar_w = int((count / max_val) * bar_max_width) if max_val else 0

        svg.append(f'<text x="{padding}" y="{y + 18}" class="label card">{name}</text>')
        svg.append(f'<rect x="{bar_x}" y="{y + 4}" width="{int(bar_max_width)}" height="18" rx="6" fill="#e5e7eb"/>')
        svg.append(f'<rect x="{bar_x}" y="{y + 4}" width="{int(bar_w)}" height="18" rx="6" fill="#1f6feb"/>')
        count_x = bar_x + int(bar_max_width) + 10
        svg.append(f'<text x="{int(count_x)}" y="{y + 18}" class="count card">{count}</text>')

    svg.append("</svg>")

    # Persist summary SVG
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(svg))
    print(f"Wrote summary svg to {out_path}")

# ---------------------------
# Outputs - full table SVG (REPO_CLONES.svg)
# ---------------------------
def generate_table_svg(owner: str, repo_rows: List[Dict[str, Any]], include_private: bool,
                       out_path="REPO_CLONES.svg", max_rows: Optional[int] = None):
    """
    Generate a full table as an SVG that mirrors the columns previously written to REPO_CLONES.md.

    The produced table contains columns:
      - Repo (name)
      - Description (first two lines, truncated)
      - Stars
      - Forks
      - Open issues
      - Last push (ISO->readable timestamp)
      - Clones (14d)
      - Unique clones (14d)

    Column widths are computed dynamically from the data with min/max clamping so
    the SVG remains visually stable even with unusually long names/descriptions.
    """
    # Copy rows (optionally truncate to max_rows)
    rows = repo_rows[:] if max_rows is None else repo_rows[:max_rows]
    total_repos = len(repo_rows)
    total_clones = sum((r.get("clone_count") or 0) for r in repo_rows)

    # Definition of columns: (key, header, min_px, max_px, is_numeric, wrap_chars_for_text)
    COLS = [
        ("name", "Repo", 140, 420, False, 30),
        ("description", "Description", 220, 600, False, 60),
        ("stargazers_count", "Stars", 56, 80, True, 0),
        ("forks_count", "Forks", 56, 80, True, 0),
        ("open_issues_count", "Open issues", 82, 110, True, 0),
        ("pushed_at", "Last push", 140, 200, False, 20),
        ("clone_count", "Clones (14d)", 90, 140, True, 0),
        ("clone_uniques", "Unique clones (14d)", 110, 160, True, 0),
    ]

    # Character-to-pixel heuristic used to estimate column widths
    CHAR_PX = 7.2

    def cell_text(col_key, r):
        """
        Return the appropriate display string for a given column key and repo dict.
        Handles formatting for dates and the clone columns which may be None.
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
    table_w = max(table_w, 760)  # ensure a minimum width for aesthetics

    visible_rows = rows
    table_h = header_h + row_h * len(visible_rows) + padding * 2
    svg_h = table_y + table_h + padding

    # Build SVG document
    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{int(table_w)}" height="{int(svg_h)}" viewBox="0 0 {int(table_w)} {int(svg_h)}" role="img" aria-label="GitHub repository clones table">')
    svg.append("""
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
""")

    # Header lines with owner, generation timestamp, and mode indicator
    svg.append(f'<text x="{padding}" y="{padding + 14}" class="title card">GitHub repositories — {escape_xml(owner)}</text>')
    svg.append(f'<text x="{padding}" y="{padding + 32}" class="meta card">Generated: {escape_xml(datetime.datetime.utcnow().isoformat()+"Z")} · Mode: {"Includes private repos" if include_private else "Public repos only"} · Total repos: {total_repos} · Total clones (sum of visible): {total_clones}</text>')

    # Table outer background and border
    tbl_x = table_x
    tbl_y = table_y + 28
    tbl_w = table_w - padding * 2
    tbl_h = header_h + row_h * len(visible_rows)
    svg.append(f'<rect x="{tbl_x}" y="{tbl_y}" width="{tbl_w}" height="{tbl_h}" rx="8" class="row-even"/>')
    svg.append(f'<rect x="{tbl_x}" y="{tbl_y}" width="{tbl_w}" height="{tbl_h}" class="table-border"/>')

    # Compute x positions for each column based on the column widths
    col_x = []
    cur_x = tbl_x + 12
    for key, hdr, min_px, max_px, isnumeric, wrap_chars in COLS:
        col_x.append((key, cur_x))
        cur_x += col_px[key] + gap

    # Render header row cells
    header_y = tbl_y + 20
    for key, x_pos in col_x:
        hdr_text = next(h for (k, h, *_) in COLS if k == key)
        svg.append(f'<text x="{int(x_pos)}" y="{header_y}" class="th card">{escape_xml(hdr_text)}</text>')

    # Horizontal header separator
    sep_y = tbl_y + 28
    svg.append(f'<line x1="{tbl_x}" y1="{sep_y}" x2="{tbl_x + tbl_w}" y2="{sep_y}" stroke="#e6eaf2" />')

    # Render each data row with subtle zebra striping
    for i, r in enumerate(visible_rows):
        row_y_top = tbl_y + 28 + i * row_h
        is_even = (i % 2 == 0)
        row_class = "row-even" if is_even else "row-odd"
        # Row background rectangle provides striping effect
        svg.append(f'<rect x="{tbl_x}" y="{row_y_top}" width="{tbl_w}" height="{row_h}" class="{row_class}" opacity="0.95"/>')

        # Render cells for each column in this row
        for key, x_pos in col_x:
            val = cell_text(key, r)
            if key == "name":
                # Repo name column: render the repository name (not an active hyperlink,
                # but visually looks like a link). Using escape_xml to prevent SVG breakage.
                name_display = escape_xml(val)
                svg.append(f'<text x="{int(x_pos)}" y="{row_y_top + 16}" class="td card">{name_display}</text>')
            elif key == "description":
                # Description column: naive two-line wrap/truncation to keep table compact.
                text = str(val or "")
                wrap_limit = next((w for (k, _, min_px, max_px, _, w) in COLS if k == key), 60)
                if not text:
                    svg.append(f'<text x="{int(x_pos)}" y="{row_y_top + 16}" class="muted card">-</text>')
                else:
                    # Word-splitting wrap algorithm: fill up to wrap_limit chars per line, up to 2 lines.
                    words = text.split()
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
                    # truncate if still too long
                    def trunc(s, n):
                        return (s[:n - 1] + "…") if len(s) > n else s
                    line1 = trunc(line1, wrap_limit)
                    line2 = trunc(line2, wrap_limit)
                    svg.append(f'<text x="{int(x_pos)}" y="{row_y_top + 14}" class="td card">{escape_xml(line1)}</text>')
                    if line2:
                        svg.append(f'<text x="{int(x_pos)}" y="{row_y_top + 28}" class="td card">{escape_xml(line2)}</text>')
            elif key == "pushed_at":
                # Push date rendered in human-friendly truncated ISO format
                svg.append(f'<text x="{int(x_pos)}" y="{row_y_top + 16}" class="td card">{escape_xml(val)}</text>')
            else:
                # Numeric or short text columns: render directly
                svg.append(f'<text x="{int(x_pos)}" y="{row_y_top + 16}" class="td card">{escape_xml(val)}</text>')

    # Footer note explaining the data window and permissions
    footer_y = tbl_y + tbl_h + 18
    note = ("Note: GitHub traffic/clones shows recent ~14 days and requires owner access for analytics. "
            "If you see 'N/A' clone stats, the token may not have permission.")
    svg.append(f'<text x="{padding}" y="{footer_y}" class="muted card">{escape_xml(note)}</text>')
    svg.append("</svg>")

    # Persist the table SVG to disk
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(svg))
    print(f"Wrote table svg to {out_path}")

# ---------------------------
# Git commit & push (robust)
# ---------------------------
def git_commit_and_push(files: List[str], commit_message: str = "chore: update repo stats", token_env: Optional[str] = None):
    """
    Commit and push a list of files to the current repository.

    Behavior:
      - If `git` is not available the function returns early.
      - Sets local git identity to `actions@github.com` / `github-actions[bot]` to avoid CI commit failures.
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

    # Configure local git identity (important in CI)
    try:
        subprocess.run(["git", "config", "--local", "user.email", "actions@github.com"], check=True)
        subprocess.run(["git", "config", "--local", "user.name", "github-actions[bot]"], check=True)
    except Exception:
        # If config fails silently, continue — commit might still succeed if global identity set
        pass

    # Stage the files for commit (raises on failure)
    subprocess.run(["git", "add"] + files, check=True)
    try:
        # Attempt commit; if there are no changes this raises CalledProcessError and we report no changes.
        subprocess.run(["git", "commit", "-m", commit_message], check=True)
    except subprocess.CalledProcessError:
        print("No changes to commit.")
        return

    # Push handling: if token_env is provided, use it to push over HTTPS in CI
    if token_env:
        token = os.environ.get(token_env)
        if not token:
            print(f"Token env var {token_env} not set; attempting normal push.")
            subprocess.run(["git", "push"], check=True)
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
                    subprocess.run(["git", "push"], check=True)
                finally:
                    # Restore original remote URL even if push fails
                    subprocess.run(["git", "remote", "set-url", "origin", origin_url], check=True)
            else:
                # Non-HTTPS remote (ssh) — just attempt push (CI may have SSH key)
                subprocess.run(["git", "push"], check=True)
        except Exception as e:
            print(f"Push failed: {e}")
    else:
        # No token env specified — normal push
        subprocess.run(["git", "push"], check=True)

# ---------------------------
# CLI entrypoint
# ---------------------------
def main():
    """
    Command-line entrypoint.

    Sets up argument parsing, owner detection, repo fetching, clone stats collection,
    generates the two SVG outputs, and optionally commits & pushes them when --push is provided.
    """
    parser = argparse.ArgumentParser(description="Generate GitHub repo clones summary (SVGs).")
    parser.add_argument("--owner", help="GitHub username (owner). If omitted, detect automatically.")
    parser.add_argument("--push", action="store_true", help="Commit & push generated files back to this repo")
    parser.add_argument("--include-private", action="store_true", help="Include private repositories (opt-in)")
    parser.add_argument("--token-env", default="TOKEN", help="Environment variable name for PAT (default: TOKEN)")
    parser.add_argument("--svg-out", default="stats.svg", help="Summary SVG filename")
    parser.add_argument("--table-out", default="REPO_CLONES.svg", help="Full table SVG filename")
    parser.add_argument("--top-n", default=6, type=int, help="Number of top repos to show in summary SVG")
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

    # Build the local repo_rows list with metadata + clone stats fetch
    repo_rows = []
    for r in repos:
        name = r.get("name")
        stats = fetch_clone_stats(owner, name, token)
        repo_rows.append({
            "name": name,
            "description": r.get("description"),
            "stargazers_count": r.get("stargazers_count", 0),
            "forks_count": r.get("forks_count", 0),
            "open_issues_count": r.get("open_issues_count", 0),
            "pushed_at": r.get("pushed_at"),
            "clone_count": stats.get("count"),
            "clone_uniques": stats.get("uniques"),
        })
        # small throttle between API calls to be polite to GitHub and avoid bursts
        time.sleep(0.12)

    # Generate the full table SVG (replacement for the old markdown output)
    try:
        print("Generating full table SVG ->", args.table_out)
        generate_table_svg(owner, repo_rows, include_private, out_path=args.table_out)
    except Exception as e:
        print("ERROR generating table SVG:", e)
        sys.exit(1)

    # Generate the compact summary SVG
    try:
        print("Generating summary SVG ->", args.svg_out)
        generate_svg(owner, repo_rows, include_private, out_path=args.svg_out, top_n=args.top_n)
    except Exception as e:
        print("ERROR generating summary SVG:", e)
        sys.exit(1)

    # If requested, stage/commit/push generated files back to the repository
    if args.push:
        files_to_commit = [args.table_out, args.svg_out]
        # Only include files that actually exist on disk
        files_to_commit = [f for f in files_to_commit if os.path.exists(f)]
        if not files_to_commit:
            print("Nothing to commit (no generated files found). Aborting push.")
            sys.exit(0)
        print("Committing and pushing files:", files_to_commit)
        git_commit_and_push(files_to_commit, commit_message="chore: update repo clones summary (SVGs)", token_env=args.token_env)
        print("Push complete.")
    else:
        # When not pushing, show which files were generated locally
        print("Run complete. Files generated (not pushed):", [f for f in [args.table_out, args.svg_out] if os.path.exists(f)])

if __name__ == "__main__":
    main()
