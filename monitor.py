#!/usr/bin/env python3
"""
Kinetica Docs Change Monitor

Fetches a watchlist of documentation URLs, extracts clean text, compares each
page against its last stored snapshot, and reports line-level diffs.

Outputs:
  - snapshots/<hash>.txt        : latest clean text per URL (committed = baseline)
  - snapshots/<hash>.meta.json  : url + last-checked metadata
  - changes/<timestamp>-<slug>.md : a diff file per changed page (this run)
  - changes/_run_summary.json   : machine-readable summary for the workflow

Run: python monitor.py
"""

import hashlib
import json
import re
import sys
import difflib
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent
SNAP_DIR = ROOT / "snapshots"
CHANGE_DIR = ROOT / "changes"
URLS_FILE = ROOT / "urls.txt"

REQUEST_TIMEOUT = 30
USER_AGENT = "KineticaDocsMonitor/1.0 (+https://github.com/your-org/kinetica-docs-monitor)"

# Lines matching these patterns are stripped before diffing, to avoid
# false positives from dynamic boilerplate (timestamps, build banners, etc.).
# Add your own per-page noise patterns here.
IGNORE_PATTERNS = [
    re.compile(r"^\s*last (updated|modified|edited)\b", re.I),
    re.compile(r"^\s*©\s*\d{4}", re.I),
    re.compile(r"\bversion\s+\d+\.\d+(\.\d+)?\b", re.I),
    re.compile(r"^\s*build\s+[\w.-]+\s*$", re.I),
    re.compile(r"^\s*\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}", re.I),
]


def url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:16]


def slugify(url: str) -> str:
    s = re.sub(r"^https?://", "", url.strip())
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-")
    return s[:60] or "page"


def load_urls() -> list[str]:
    if not URLS_FILE.exists():
        print(f"ERROR: {URLS_FILE} not found.", file=sys.stderr)
        sys.exit(1)
    urls = []
    for line in URLS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls


def fetch(url: str) -> str | None:
    try:
        resp = requests.get(
            url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT}
        )
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        print(f"WARN: failed to fetch {url}: {e}", file=sys.stderr)
        return None


def extract_text(html: str) -> str:
    """Extract meaningful text, stripping nav/script/style/footer noise."""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()

    # Prefer the main content region if the docs use one.
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find(attrs={"role": "main"})
        or soup.body
        or soup
    )

    text = main.get_text(separator="\n")
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if any(p.search(line) for p in IGNORE_PATTERNS):
            continue
        lines.append(line)
    return "\n".join(lines)


def read_snapshot(h: str) -> str | None:
    f = SNAP_DIR / f"{h}.txt"
    return f.read_text(encoding="utf-8") if f.exists() else None


def write_snapshot(h: str, url: str, text: str) -> None:
    SNAP_DIR.mkdir(exist_ok=True)
    (SNAP_DIR / f"{h}.txt").write_text(text, encoding="utf-8")
    (SNAP_DIR / f"{h}.meta.json").write_text(
        json.dumps(
            {
                "url": url,
                "last_checked": datetime.now(timezone.utc).isoformat(),
                "chars": len(text),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def make_diff(old: str, new: str, url: str) -> str:
    diff = difflib.unified_diff(
        old.splitlines(),
        new.splitlines(),
        fromfile="previous",
        tofile="current",
        lineterm="",
        n=2,
    )
    return "\n".join(diff)


def write_change_file(url: str, diff: str, ts: str) -> Path:
    CHANGE_DIR.mkdir(exist_ok=True)
    slug = slugify(url)
    path = CHANGE_DIR / f"{ts}-{slug}.md"
    body = (
        f"# Change detected\n\n"
        f"- **URL:** {url}\n"
        f"- **Detected:** {ts} UTC\n\n"
        f"```diff\n{diff}\n```\n"
    )
    path.write_text(body, encoding="utf-8")
    return path


def main() -> int:
    urls = load_urls()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")

    checked = 0
    changed = []
    new_pages = []
    errors = []

    for url in urls:
        h = url_hash(url)
        html = fetch(url)
        if html is None:
            errors.append(url)
            continue

        new_text = extract_text(html)
        checked += 1
        old_text = read_snapshot(h)

        if old_text is None:
            # First time seeing this URL -> establish baseline, no diff.
            write_snapshot(h, url, new_text)
            new_pages.append(url)
            print(f"NEW baseline: {url}")
            continue

        if old_text == new_text:
            # No change: refresh last_checked timestamp only.
            write_snapshot(h, url, new_text)
            print(f"unchanged: {url}")
            continue

        # Changed -> record diff, then update baseline.
        diff = make_diff(old_text, new_text, url)
        cf = write_change_file(url, diff, ts)
        write_snapshot(h, url, new_text)
        changed.append({"url": url, "change_file": str(cf.relative_to(ROOT))})
        print(f"CHANGED: {url} -> {cf.name}")

    summary = {
        "run": ts,
        "checked": checked,
        "changed": changed,
        "new_pages": new_pages,
        "errors": errors,
    }
    CHANGE_DIR.mkdir(exist_ok=True)
    (CHANGE_DIR / "_run_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    print(
        f"\nDone. {checked} checked, {len(changed)} changed, "
        f"{len(new_pages)} new, {len(errors)} errors."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
