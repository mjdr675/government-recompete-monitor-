"""
GitHub Issues Sync — imports open GitHub issues into ai_agent/queue/.

Fetches open issues from GitHub (via gh CLI or GITHUB_TOKEN + requests),
converts each issue to a queue task file, and prevents duplicates.

Filename format:  issue-{number:04d}-{slug}.md
Ordering:         issue numbers preserve GitHub order; existing queue
                  files are never renumbered.
Deduplication:    any file matching issue-{number:04d}-*.md in queue/,
                  done/, or failed/ is treated as already imported.

Usage:
  from ai_agent.github_issues import sync_issues
  result = sync_issues()                      # auto-detects repo from git remote
  result = sync_issues(repo="owner/repo")

CLI:
  python -m ai_agent.github_issues
  python -m ai_agent.github_issues --repo owner/repo --dry-run
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).parent.parent
_AGENT_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class SyncResult:
    repo: str
    imported: list[str] = field(default_factory=list)   # filenames created
    skipped: list[str] = field(default_factory=list)    # issue refs already present
    errors: list[str] = field(default_factory=list)     # error messages


# ---------------------------------------------------------------------------
# Repo detection
# ---------------------------------------------------------------------------

def _detect_repo(repo_root: Path = REPO_ROOT) -> Optional[str]:
    """Detect the GitHub owner/repo from git remote origin."""
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    url = result.stdout.strip()
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Issue fetching
# ---------------------------------------------------------------------------

def _gh_available() -> bool:
    """Return True if the gh CLI is installed and authenticated."""
    result = subprocess.run(
        ["gh", "auth", "status"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _fetch_via_gh(repo: str, limit: int = 100) -> list[dict]:
    """Fetch open issues using the gh CLI. Raises RuntimeError on failure."""
    result = subprocess.run(
        [
            "gh", "issue", "list",
            "--repo", repo,
            "--state", "open",
            "--limit", str(limit),
            "--json", "number,title,body,labels,state,url",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh issue list failed: {result.stderr.strip()}")
    return json.loads(result.stdout or "[]")


def _fetch_via_api(repo: str, token: str, limit: int = 100) -> list[dict]:
    """Fetch open issues via the GitHub REST API. Raises on HTTP errors."""
    try:
        import requests as req
    except ImportError:
        raise RuntimeError("requests package not installed. Run: pip install requests")

    owner, name = repo.split("/", 1)
    url = f"https://api.github.com/repos/{owner}/{name}/issues"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    resp = req.get(url, headers=headers, params={"state": "open", "per_page": limit})
    resp.raise_for_status()
    issues = resp.json()
    # GitHub API returns PRs in the issues list; exclude them
    return [i for i in issues if "pull_request" not in i]


def fetch_issues(repo: str, limit: int = 100) -> list[dict]:
    """
    Fetch open issues for *repo* (``owner/name``).

    Tries gh CLI first; falls back to GITHUB_TOKEN + requests.
    Raises RuntimeError when neither source is available or authentication fails.
    """
    if _gh_available():
        return _fetch_via_gh(repo, limit=limit)

    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        return _fetch_via_api(repo, token, limit=limit)

    raise RuntimeError(
        "No GitHub credentials found.\n"
        "Either authenticate with: gh auth login\n"
        "Or set: export GITHUB_TOKEN=<your-token>"
    )


# ---------------------------------------------------------------------------
# Issue → task file conversion
# ---------------------------------------------------------------------------

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower())[:40].strip("_")


def issue_to_filename(number: int, title: str) -> str:
    """Return the queue filename for an issue."""
    return f"issue-{number:04d}-{_slug(title)}.md"


def issue_to_content(issue: dict) -> str:
    """Render an issue dict as queue task Markdown."""
    number = issue.get("number", 0)
    title = issue.get("title") or f"Issue {number}"
    body = (issue.get("body") or "").strip()
    labels = [
        lbl["name"] if isinstance(lbl, dict) else str(lbl)
        for lbl in issue.get("labels", [])
    ]
    url = issue.get("url") or issue.get("html_url") or ""

    lines = [f"# Issue #{number}: {title}", ""]
    if labels:
        lines += [f"**Labels:** {', '.join(labels)}", ""]
    if url:
        lines += [f"**URL:** {url}", ""]
    if body:
        lines += [body, ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

def _already_imported(number: int, search_dirs: list[Path]) -> bool:
    """True if any file matching issue-{number:04d}-*.md exists in any dir."""
    pattern = f"issue-{number:04d}-*.md"
    return any(
        bool(list(d.glob(pattern)))
        for d in search_dirs
        if d.exists()
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def sync_issues(
    repo: Optional[str] = None,
    queue_dir: Optional[Path] = None,
    done_dir: Optional[Path] = None,
    failed_dir: Optional[Path] = None,
    repo_root: Path = REPO_ROOT,
    dry_run: bool = False,
    issues: Optional[list[dict]] = None,
) -> SyncResult:
    """
    Sync open GitHub issues into the ai_agent queue.

    Args:
        repo:      GitHub ``owner/name`` (auto-detected from git remote if omitted).
        queue_dir: Where to write task files (default: ``ai_agent/queue/``).
        done_dir:  Completed tasks dir — used for dedup (default: ``ai_agent/done/``).
        failed_dir: Failed tasks dir — used for dedup (default: ``ai_agent/failed/``).
        repo_root: Repository root path.
        dry_run:   If True, report what would be imported without writing files.
        issues:    Pre-fetched issue list (skips GitHub fetch; useful for tests).

    Returns:
        :class:`SyncResult` with ``imported``, ``skipped``, and ``errors`` lists.
    """
    if queue_dir is None:
        queue_dir = _AGENT_DIR / "queue"
    if done_dir is None:
        done_dir = _AGENT_DIR / "done"
    if failed_dir is None:
        failed_dir = _AGENT_DIR / "failed"

    # Resolve repo
    resolved_repo = repo or _detect_repo(repo_root) or ""
    result = SyncResult(repo=resolved_repo)

    if not resolved_repo:
        result.errors.append(
            "Could not determine GitHub repo. "
            "Pass repo='owner/name' or set a git remote named 'origin'."
        )
        return result

    # Fetch issues
    if issues is None:
        try:
            issues = fetch_issues(resolved_repo)
        except Exception as exc:
            result.errors.append(f"fetch failed: {exc}")
            return result

    search_dirs = [queue_dir, done_dir, failed_dir]
    queue_dir.mkdir(parents=True, exist_ok=True)

    # Sort by issue number to preserve ordering
    sorted_issues = sorted(issues, key=lambda i: i.get("number", 0))

    for issue in sorted_issues:
        number = issue.get("number")
        if number is None:
            result.errors.append(f"issue missing number field: {issue!r:.80}")
            continue

        title = issue.get("title") or f"Issue {number}"
        ref = f"#{number} {title}"

        if _already_imported(number, search_dirs):
            result.skipped.append(ref)
            continue

        filename = issue_to_filename(number, title)
        content = issue_to_content(issue)

        if not dry_run:
            (queue_dir / filename).write_text(content, encoding="utf-8")

        result.imported.append(filename)

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main(argv=None) -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m ai_agent.github_issues",
        description="Sync open GitHub issues into ai_agent/queue/",
    )
    parser.add_argument(
        "--repo", default=None, metavar="OWNER/NAME",
        help="GitHub repo (default: auto-detect from git remote)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what would be imported without writing files",
    )
    parser.add_argument(
        "--limit", type=int, default=100, metavar="N",
        help="Max issues to fetch (default: 100)",
    )
    args = parser.parse_args(argv)

    result = sync_issues(repo=args.repo, dry_run=args.dry_run)
    print(f"[GITHUB_ISSUES] Repo:     {result.repo}")
    print(f"[GITHUB_ISSUES] Imported: {len(result.imported)}")
    print(f"[GITHUB_ISSUES] Skipped:  {len(result.skipped)}")
    print(f"[GITHUB_ISSUES] Errors:   {len(result.errors)}")
    for name in result.imported:
        prefix = "(dry-run) " if args.dry_run else ""
        print(f"  + {prefix}{name}")
    for ref in result.skipped:
        print(f"  ~ already queued: {ref}")
    for err in result.errors:
        print(f"  ! {err}")


if __name__ == "__main__":
    _main()
