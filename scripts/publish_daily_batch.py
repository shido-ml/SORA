#!/usr/bin/env python3
"""Publish a reviewed daily batch into the existing static SORA site.

Put researched records in data/daily/YYYY-MM-DD.json using the fields in
data/new-articles-plan.json, plus a nonempty fact_check note for each record.
Run --check first. The date is the Japanese publication date. A second run
with the same batch is a no-op; the script never rewrites older article dates.
This script does not schedule itself or push to GitHub.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_content as site


DAILY = site.ROOT / "data" / "daily"
MAX_PER_DAY = 30
NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def jst_today() -> str:
    return datetime.now(timezone(timedelta(hours=9))).date().isoformat()


def published_date(article: site.Article) -> str | None:
    soup = site.soup_from_path(site.ROOT / article.source_file)
    for node in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(node.get_text())
        except json.JSONDecodeError:
            continue
        entries = payload.get("@graph", [payload]) if isinstance(payload, dict) else []
        for entry in entries:
            if isinstance(entry, dict) and entry.get("@type") == "Article":
                value = entry.get("datePublished", "")
                if isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}", value):
                    return value[:10]
    return None


def actual_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        site.fail(f"invalid Japanese publication date: {value}")


def update_count(html: str, total: int) -> str:
    # Only reader-facing Japanese article-count text changes, not CSS values.
    return re.sub(r"全\d+記事", f"全{total}記事", html)


def update_home(html: str, total: int, windows_count: int) -> str:
    soup = BeautifulSoup(update_count(html, total), "html.parser")
    card = soup.select_one('.device-card[href="/category/windows/"] small')
    if card:
        card.string = f"{windows_count}件のトラブル解決ガイド"
    return site.serialize_html(soup)


def add_editorial_detail(rendered: str, record: dict[str, str]) -> str:
    """Keep the article-specific diagnosis and safety context in the page."""
    soup = BeautifulSoup(rendered, "html.parser")
    scope = soup.select_one("#scope")
    caution = soup.select_one("#caution + .info-box")
    if scope is None or caution is None:
        site.fail(f"article template has changed: {record['path']}")
    paragraph = soup.new_tag("p")
    paragraph.string = record["diagnosis"]
    scope.insert_after(paragraph)
    extra = soup.new_tag("p")
    extra.string = record["caution"]
    caution.append(extra)
    return site.serialize_html(soup)


def update_sitemap_dates(xml: str, changed: set[Path], day: str) -> str:
    root = ET.fromstring(xml)
    by_url = {node.findtext(f"{{{NS}}}loc"): node for node in root.findall(f"{{{NS}}}url")}
    for path in changed:
        if path.name != "index.html" and path.suffix != ".html":
            continue
        rel = path.relative_to(site.ROOT).as_posix()
        canonical = "/" if rel == "index.html" else ("/" + rel[:-10] if rel.endswith("/index.html") else "/" + rel)
        url = site.BASE_URL + canonical
        node = by_url.get(url)
        if node is None:
            site.fail(f"changed public page is absent from sitemap: {url}")
        lastmod = node.find(f"{{{NS}}}lastmod")
        if lastmod is None:
            lastmod = ET.SubElement(node, f"{{{NS}}}lastmod")
        lastmod.text = day
    ET.register_namespace("", NS)
    ET.indent(root, space="  ")
    return "<?xml version='1.0' encoding='utf-8'?>\n" + ET.tostring(root, encoding="unicode") + "\n"


def build(day: str, check_only: bool) -> None:
    plan_file = DAILY / f"{day}.json"
    raw = site.read_json(plan_file)
    if not isinstance(raw, list) or not raw or len(raw) > MAX_PER_DAY:
        site.fail(f"daily plan must contain 1 to {MAX_PER_DAY} reviewed records")
    for i, record in enumerate(raw):
        if not isinstance(record, dict) or not isinstance(record.get("fact_check"), str) or len(record["fact_check"].strip()) < 40:
            site.fail(f"daily plan[{i}] needs a specific fact_check note of at least 40 characters")
        for field, minimum in (("diagnosis", 100), ("caution", 70)):
            if not isinstance(record.get(field), str) or len(record[field].strip()) < minimum:
                site.fail(f"daily plan[{i}].{field} needs at least {minimum} article-specific characters")

    batch_paths = {site.canonical_path(record["path"]) for record in raw}
    if len(batch_paths) != len(raw):
        site.fail("duplicate paths in daily plan")
    scanned = site.scan_article_files()
    already = {article.url for article in scanned if published_date(article) == day}
    unpublished = batch_paths - {article.url for article in scanned}
    if len(already | unpublished) > MAX_PER_DAY:
        site.fail(f"daily cap exceeded: {len(already)} published + {len(unpublished)} unposted URLs")
    other = [article for article in scanned if article.url not in batch_paths]
    site.EXPECTED_NEW_ARTICLES = len(raw)
    plan = site.validate_plan(raw, other)
    existing = {article.url: article for article in scanned}
    for record in plan:
        if record["path"] in existing and published_date(existing[record["path"]]) != day:
            site.fail(f"refusing to redate an existing article: {record['path']}")
    titles = [article.title for article in other]
    for record in plan:
        if any(difflib.SequenceMatcher(None, record["title"], title).ratio() >= .86 for title in titles):
            site.fail(f"possible duplicate title, review before publication: {record['title']}")
        titles.append(record["title"])

    new_articles = [site.generated_article(record) for record in plan]
    old_order = [item["url"] for item in site.read_json(site.SEARCH_PATH)]
    by_existing = {article.url: article for article in other}
    if set(old_order) != {article.url for article in scanned}:
        site.fail("search index and existing article files disagree; refresh before publishing")
    prior = [by_existing[url] for url in old_order if url in by_existing]
    all_articles = new_articles + prior
    total = len(all_articles)
    url_map = {article.url: article for article in all_articles}
    outputs: dict[Path, str] = {}
    raw_by_path = {record["path"]: record for record in raw}
    for record in plan:
        related = site.select_related(record, url_map, other)
        path = site.ROOT / record["category"] / record["slug"] / "index.html"
        outputs[path] = add_editorial_detail(
            site.render_article(record, related, day).replace("全400記事", "記事一覧"),
            raw_by_path[record["path"]]
        )
        site.validate_generated_html(record, outputs[path], set(url_map))

    by_category: dict[str, list[site.Article]] = defaultdict(list)
    for article in all_articles:
        if article.category_url:
            by_category[article.category_url].append(article)
    outputs[site.ROOT / "articles" / "index.html"] = update_count(site.build_master_index(all_articles), total)
    outputs[site.ROOT / "categories" / "index.html"] = update_count(site.build_categories_index(by_category), total)
    outputs[site.ROOT / "articles.html"] = update_count(site.build_legacy_index(), total)
    affected_categories = {article.category_url for article in new_articles}
    for category_file in sorted((site.ROOT / "category").glob("*/index.html")):
        category_url = f"/category/{category_file.parent.name}/"
        if category_url in affected_categories:
            outputs[category_file] = update_count(site.build_category_page(category_file, by_category[category_url]), total)
    outputs[site.ROOT / "index.html"] = update_home(
        site.build_homepage(all_articles[:8]), total, len(by_category["/category/windows/"])
    )
    outputs[site.SEARCH_PATH] = json.dumps(
        [{"title": a.title, "description": a.description, "url": a.url} for a in all_articles],
        ensure_ascii=False, indent=2
    ) + "\n"
    site.EXPECTED_SITEMAP_URLS = total + site.EXPECTED_NON_ARTICLE_URLS
    sitemap_xml, sitemap_txt, urls = site.render_sitemap(all_articles, batch_paths, day)
    if len(urls) != total + site.EXPECTED_NON_ARTICLE_URLS:
        site.fail("sitemap URL count mismatch")
    outputs[site.SITEMAP_TXT_PATH] = sitemap_txt

    changed = {path for path, content in outputs.items() if not path.exists() or path.read_text(encoding="utf-8") != content}
    derived_pages = {
        site.ROOT / "index.html", site.ROOT / "articles.html",
        site.ROOT / "articles" / "index.html", site.ROOT / "categories" / "index.html",
        *(site.ROOT / "category" / category_file.parent.name / "index.html"
          for category_file in (site.ROOT / "category").glob("*/index.html")
          if f"/category/{category_file.parent.name}/" in affected_categories),
    }
    outputs[site.SITEMAP_XML_PATH] = update_sitemap_dates(sitemap_xml, derived_pages, day)
    changed = {path for path, content in outputs.items() if not path.exists() or path.read_text(encoding="utf-8") != content}
    site.validate_listing(outputs[site.ROOT / "articles" / "index.html"], total)
    print(f"date={day} already_published={len(already)} to_add={len(unpublished)} total={total} sitemap={len(urls)} files_to_write={len(changed)}")
    if check_only:
        print("check-only: no files written")
        return
    for path in sorted(changed):
        site.atomic_write(path, outputs[path])
    print(f"written: {len(changed)} files")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=jst_today(), help="Japanese publication date, YYYY-MM-DD")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    build(actual_date(args.date), args.check)


if __name__ == "__main__":
    main()
