"""Confirm that the 323 pre-existing articles kept their SEO and article copy."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
BASELINE = "origin/main"


def git_text(path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{BASELINE}:{path}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return result.stdout.decode("utf-8")


def file_for_url(url: str) -> str:
    path = urlparse(url).path.lstrip("/")
    return f"{path}index.html" if path.endswith("/") else path


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def field(soup: BeautifulSoup, name: str) -> str:
    if name == "title":
        return clean(soup.title.get_text(" ")) if soup.title else ""
    if name == "description":
        node = soup.select_one('meta[name="description"]')
        return clean(node.get("content", "")) if node else ""
    if name == "canonical":
        node = soup.select_one('link[rel="canonical"]')
        return clean(node.get("href", "")) if node else ""
    if name == "h1":
        node = soup.select_one("h1")
        return clean(node.get_text(" ")) if node else ""
    raise ValueError(name)


def content_signature(soup: BeautifulSoup) -> list[tuple[str, str]]:
    for node in soup.select(
        "header, footer, nav, script, style, noscript, .sora-guide-visual, "
        ".sora-reading-progress, .sora-back-to-top"
    ):
        node.decompose()
    return [
        (node.name, clean(node.get_text(" ")))
        for node in soup.select("h1, h2, h3, h4, p, li, th, td, blockquote, figcaption")
        if clean(node.get_text(" "))
    ]


def main() -> int:
    baseline_index = json.loads(git_text("data/search-index.json"))
    errors: list[str] = []
    for record in baseline_index:
        relative = file_for_url(record["url"])
        current_path = ROOT / relative
        if not current_path.is_file():
            errors.append(f"missing: {relative}")
            continue
        old = BeautifulSoup(git_text(relative), "html.parser")
        current = BeautifulSoup(current_path.read_text(encoding="utf-8"), "html.parser")
        for name in ("title", "description", "canonical", "h1"):
            if field(old, name) != field(current, name):
                errors.append(f"{relative}: changed {name}")
        if content_signature(old) != content_signature(current):
            errors.append(f"{relative}: changed article text")

    print(f"Existing articles checked: {len(baseline_index)}")
    if errors:
        print(f"FAIL: {len(errors)} preservation issue(s)")
        for error in errors[:50]:
            print(f"- {error}")
        return 1
    print("PASS: title, description, canonical, H1, and article text are unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
