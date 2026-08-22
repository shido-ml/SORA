"""Verify the generated SORA site locally or through HTTP.

Usage:
    python scripts/verify_site.py
    python scripts/verify_site.py --base-url http://127.0.0.1:4173
    python scripts/verify_site.py --base-url https://sora-navi-jp.com
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://sora-navi-jp.com"
EXPECTED_ARTICLES = 400
USER_AGENT = "SORA-Site-Verification/1.0"
INLINE_AD_ID = "23a16b749b5224c46c26784399bdfcad"


@dataclass(frozen=True)
class PageResult:
    url: str
    status: int
    final_url: str
    content_type: str
    error: str = ""


def local_path(url_path: str) -> Path:
    path = urlparse(url_path).path
    if path.endswith("/"):
        return ROOT / path.lstrip("/") / "index.html"
    return ROOT / path.lstrip("/")


def canonical_path(value: str) -> str:
    parsed = urlparse(value)
    return parsed.path or "/"


def sitemap_urls() -> list[str]:
    root = ElementTree.parse(ROOT / "sitemap.xml").getroot()
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    return [node.text.strip() for node in root.findall("sm:url/sm:loc", namespace) if node.text]


def article_index() -> list[dict[str, str]]:
    return json.loads((ROOT / "data/search-index.json").read_text(encoding="utf-8"))


def article_schema_present(soup: BeautifulSoup) -> bool:
    for node in soup.select('script[type="application/ld+json"]'):
        if re.search(r'"@type"\s*:\s*"Article"', node.get_text(" ")):
            return True
    return False


def validate_articles(index: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    plan_paths = {
        item["path"]
        for item in json.loads((ROOT / "data/new-articles-plan.json").read_text(encoding="utf-8"))
    }
    urls = [item.get("url", "") for item in index]
    if len(index) != EXPECTED_ARTICLES:
        errors.append(f"search index count: expected {EXPECTED_ARTICLES}, got {len(index)}")
    if len(set(urls)) != len(urls):
        errors.append("search index contains duplicate URLs")

    values: dict[str, list[tuple[str, str]]] = {key: [] for key in ("title", "description", "canonical", "h1")}
    for item in index:
        url = item.get("url", "")
        path = local_path(url)
        if not path.is_file():
            errors.append(f"missing article file: {url} -> {path.relative_to(ROOT)}")
            continue
        html = path.read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.get_text(strip=True) if soup.title else ""
        description_node = soup.select_one('meta[name="description"]')
        description = description_node.get("content", "").strip() if description_node else ""
        canonical_node = soup.select_one('link[rel="canonical"]')
        canonical = canonical_node.get("href", "").strip() if canonical_node else ""
        h1_nodes = soup.select("h1")
        h1 = h1_nodes[0].get_text(" ", strip=True) if h1_nodes else ""
        body_text = soup.body.get_text(" ", strip=True) if soup.body else ""

        for field, value in (("title", title), ("description", description), ("canonical", canonical), ("h1", h1)):
            if not value:
                errors.append(f"{url}: missing {field}")
            else:
                values[field].append((value, url))
        if len(h1_nodes) != 1:
            errors.append(f"{url}: expected one H1, got {len(h1_nodes)}")
        if canonical != ORIGIN + url:
            errors.append(f"{url}: canonical mismatch: {canonical}")
        if item.get("title") and item["title"] != h1:
            errors.append(f"{url}: search title differs from H1")
        if item.get("description") and item["description"] != description:
            errors.append(f"{url}: search description differs from meta description")
        if len(body_text) < 350:
            errors.append(f"{url}: article body is unexpectedly short ({len(body_text)} chars)")
        legacy_without_article_wrapper = url.startswith("/articles/") and not soup.select_one(
            "article.article-body, article.article-main"
        )
        if not article_schema_present(soup) and not legacy_without_article_wrapper:
            errors.append(f"{url}: Article JSON-LD missing")
        if not soup.select_one('link[href^="/assets/css/site-v2.css"]'):
            errors.append(f"{url}: site-v2.css missing")
        site_scripts = soup.select('script[src^="/assets/js/site-v2.js"]')
        if not site_scripts:
            errors.append(f"{url}: site-v2.js missing")
        elif len(site_scripts) != 1 or not site_scripts[0].has_attr("defer"):
            errors.append(f"{url}: site-v2.js must occur once with defer")
        if not soup.select_one('script[src^="/assets/js/ad-loader.js"]'):
            errors.append(f"{url}: ad-loader.js missing")
        ad_slots = soup.select(f'.sora-mobile-inline-ad .admax-ads[data-admax-id="{INLINE_AD_ID}"]')
        if len(ad_slots) != 1:
            errors.append(f"{url}: expected one approved inline-ad marker, got {len(ad_slots)}")
        if url in plan_paths:
            if len(soup.select(".sora-guide-visual .sora-guide-visual-wide")) != 1:
                errors.append(f"{url}: generated desktop guide visual missing")
            if len(soup.select(".sora-guide-visual .sora-guide-visual-mobile")) != 1:
                errors.append(f"{url}: generated mobile guide visual missing")

    for field, pairs in values.items():
        grouped: dict[str, list[str]] = {}
        for value, url in pairs:
            grouped.setdefault(value, []).append(url)
        duplicates = {value: found for value, found in grouped.items() if len(found) > 1}
        if duplicates:
            sample = next(iter(duplicates.values()))
            errors.append(f"duplicate {field}: {sample}")
    return errors


def validate_sitemap(index: list[dict[str, str]], urls: list[str]) -> list[str]:
    errors: list[str] = []
    if len(urls) != len(set(urls)):
        errors.append("sitemap.xml contains duplicate URLs")
    text_urls = [line.strip() for line in (ROOT / "sitemap.txt").read_text(encoding="utf-8").splitlines() if line.strip()]
    if urls != text_urls:
        errors.append("sitemap.xml and sitemap.txt URL order/content differ")
    sitemap_paths = {canonical_path(url) for url in urls}
    article_paths = {item["url"] for item in index}
    missing = sorted(article_paths - sitemap_paths)
    if missing:
        errors.append(f"sitemap missing {len(missing)} articles; first: {missing[0]}")
    for url in urls:
        path = local_path(canonical_path(url))
        if not path.is_file():
            errors.append(f"sitemap target missing locally: {url}")
    robots = (ROOT / "robots.txt").read_text(encoding="utf-8")
    if f"Sitemap: {ORIGIN}/sitemap.xml" not in robots:
        errors.append("robots.txt does not advertise the canonical sitemap")
    return errors


def validate_internal_assets(urls: list[str]) -> list[str]:
    errors: list[str] = []
    checked: set[Path] = set()
    for absolute_url in urls:
        path = local_path(canonical_path(absolute_url))
        if not path.is_file() or path in checked or path.suffix.lower() != ".html":
            continue
        checked.add(path)
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        for tag, attribute in (("a", "href"), ("img", "src"), ("script", "src"), ("link", "href")):
            for node in soup.find_all(tag):
                value = (node.get(attribute) or "").strip()
                if not value.startswith("/") or value.startswith("//"):
                    continue
                target = local_path(value)
                if target.suffix == "" and not value.endswith("/"):
                    target = target / "index.html"
                if not target.exists():
                    errors.append(f"{canonical_path(absolute_url)}: broken {attribute} {value}")
    return errors


def validate_site_shell(urls: list[str]) -> list[str]:
    errors: list[str] = []
    for absolute_url in urls:
        path = local_path(canonical_path(absolute_url))
        if not path.is_file() or path.suffix.lower() != ".html":
            continue
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        url = canonical_path(absolute_url)
        if not soup.html or "sora-ui-v2" not in soup.html.get("class", []):
            errors.append(f"{url}: sora-ui-v2 root class missing")
        if len(soup.select("header.site-header.sora-v2-header")) != 1:
            errors.append(f"{url}: expected one static v2 header")
        if len(soup.select("footer.site-footer.sora-v2-footer")) != 1:
            errors.append(f"{url}: expected one static v2 footer")
        site_scripts = soup.select('script[src^="/assets/js/site-v2.js"]')
        if len(site_scripts) != 1 or not site_scripts[0].has_attr("defer"):
            errors.append(f"{url}: expected one deferred site-v2 script")
        if len(soup.select('link[href^="/assets/css/site-v2.css"]')) != 1:
            errors.append(f"{url}: expected one site-v2 stylesheet")
    return errors


def fetch(url: str) -> PageResult:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return PageResult(
                url=url,
                status=response.status,
                final_url=response.geturl(),
                content_type=response.headers.get("Content-Type", ""),
            )
    except urllib.error.HTTPError as error:
        return PageResult(url, error.code, error.geturl(), error.headers.get("Content-Type", ""), str(error))
    except Exception as error:  # network diagnostics should report every failure
        return PageResult(url, 0, "", "", str(error))


def validate_http(base_url: str, urls: list[str]) -> list[str]:
    errors: list[str] = []
    targets = [urljoin(base_url.rstrip("/") + "/", canonical_path(url).lstrip("/")) for url in urls]
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(fetch, targets))
    for result in results:
        if result.status != 200:
            errors.append(f"HTTP {result.status}: {result.url} ({result.error})")
    print(f"HTTP 200: {sum(result.status == 200 for result in results)}/{len(results)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", help="Also request every sitemap URL from this origin")
    args = parser.parse_args()

    index = article_index()
    urls = sitemap_urls()
    errors = validate_articles(index)
    errors.extend(validate_sitemap(index, urls))
    errors.extend(validate_internal_assets(urls))
    errors.extend(validate_site_shell(urls))
    if args.base_url:
        errors.extend(validate_http(args.base_url, urls))

    print(f"Articles: {len(index)}")
    print(f"Sitemap URLs: {len(urls)}")
    if errors:
        print(f"FAILED: {len(errors)} issue(s)")
        for error in errors[:100]:
            print(f"- {error}")
        if len(errors) > 100:
            print(f"... and {len(errors) - 100} more")
        return 1
    print("PASS: article, SEO, sitemap, internal asset, and optional HTTP checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
