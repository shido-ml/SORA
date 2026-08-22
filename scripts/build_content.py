#!/usr/bin/env python3
"""Build the 77-article expansion and every derived public index.

The script deliberately treats ``data/new-articles-plan.json`` as the single
source of truth for the new articles.  It validates the entire build in memory
before it writes anything, which keeps a bad or half-finished plan from
partially updating the public site.

Usage::

    python scripts/build_content.py --check
    python scripts/build_content.py

The default publication date is intentionally pinned to this release so that
rerunning the build is idempotent.  A later release can pass ``--date``.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from bs4 import BeautifulSoup, NavigableString, Tag


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://sora-navi-jp.com"
PLAN_PATH = ROOT / "data" / "new-articles-plan.json"
SEARCH_PATH = ROOT / "data" / "search-index.json"
SITEMAP_XML_PATH = ROOT / "sitemap.xml"
SITEMAP_TXT_PATH = ROOT / "sitemap.txt"
DEFAULT_PUBLISH_DATE = "2026-08-23"
ASSET_VERSION = "20260823"

EXPECTED_BASE_ARTICLES = 323
EXPECTED_LEGACY_ARTICLES = 153
EXPECTED_MODERN_ARTICLES = 170
EXPECTED_NEW_ARTICLES = 77
EXPECTED_TOTAL_ARTICLES = 400
EXPECTED_NON_ARTICLE_URLS = 32
EXPECTED_SITEMAP_URLS = 432

GENERATOR_NAME = "sora-build-content-v1"
NEW_ARTICLE_ROOTS = (
    "windows",
    "android",
    "mac",
    "internet",
    "peripherals",
    "browser",
    "google",
    "sns",
)
ALL_MODERN_ROOTS = ("iphone",) + NEW_ARTICLE_ROOTS


CATEGORY_CONFIG: dict[str, dict[str, Any]] = {
    "windows": {
        "label": "Windows",
        "category_url": "/category/windows/",
        "checks": [
            "別のユーザーアカウントでも同じ症状が起きるか",
            "Windows Updateや設定変更の直後から始まったか",
            "接続機器や常駐アプリを外すと変化するか",
        ],
        "safety": "回復、リセット、ドライバー削除を行う前に、BitLocker回復キーと必要なファイルのバックアップを確認してください。",
    },
    "android": {
        "label": "Android",
        "category_url": "/category/android/",
        "checks": [
            "特定のアプリだけか、端末全体で起きるか",
            "Wi-Fiとモバイル通信を切り替えると変化するか",
            "OS更新、アプリ更新、設定変更の直後から始まったか",
        ],
        "safety": "端末の初期化、アプリのデータ消去、アカウント削除は保存内容に影響します。同期とバックアップを確認してから行ってください。",
    },
    "mac": {
        "label": "Mac",
        "category_url": "/category/mac/",
        "checks": [
            "別のユーザー、別の接続先、セーフモードでも再現するか",
            "macOS更新や周辺機器の接続後から始まったか",
            "電源、空き容量、ネットワークのどこに変化があるか",
        ],
        "safety": "ディスク消去、macOS再インストール、アカウント削除は最後の手段です。Time Machineなどのバックアップを先に確認してください。",
    },
    "internet": {
        "label": "インターネット・Wi-Fi",
        "category_url": "/category/internet-wifi/",
        "checks": [
            "1台だけか、同じ回線の全端末で起きるか",
            "有線とWi-Fi、2.4GHzと5GHzで結果が変わるか",
            "ONU・ルーターのランプと回線事業者の障害情報に異常がないか",
        ],
        "safety": "ルーターの初期化ボタンは押さないでください。接続ID、電話、IPv6などの再設定が必要になる場合があります。",
    },
    "peripherals": {
        "label": "周辺機器",
        "category_url": "/category/peripherals/",
        "checks": [
            "別の端子、ケーブル、PCでも同じ症状が起きるか",
            "本体の電源・表示・物理スイッチに異常がないか",
            "OS標準機能とメーカーアプリのどちらでも再現するか",
        ],
        "safety": "フォーマット、ファームウェア更新、ドライバー削除の前に、機器内のデータとメーカーの注意事項を確認してください。",
    },
    "browser": {
        "label": "ブラウザ",
        "category_url": "/category/browser/",
        "checks": [
            "シークレットウィンドウや別ブラウザでは開けるか",
            "特定サイトだけか、すべてのサイトで起きるか",
            "拡張機能、VPN、セキュリティソフトを止めると変化するか",
        ],
        "safety": "同期解除、閲覧データ削除、ブラウザのリセットでは保存済み情報が消える場合があります。削除対象を確認してください。",
    },
    "google": {
        "label": "Googleサービス",
        "category_url": "/category/google-services/",
        "checks": [
            "ブラウザ版とアプリ版の両方で起きるか",
            "別アカウントや別端末では正常に利用できるか",
            "保存容量、同期状態、Google側の障害情報に異常がないか",
        ],
        "safety": "アカウント削除やデータ削除の前に、同期先、ゴミ箱、バックアップ、復元期限を確認してください。",
    },
    "sns": {
        "label": "SNS・通話サービス",
        "category_url": "/category/social-communication/",
        "checks": [
            "ブラウザ版、アプリ版、別端末で結果が変わるか",
            "特定の相手や機能だけか、サービス全体で起きるか",
            "通信、権限、アカウント制限、サービス障害のどれに当てはまるか",
        ],
        "safety": "ログアウト、再インストール、アカウント削除の前に、引き継ぎ情報、下書き、トーク履歴、二段階認証を確認してください。",
    },
}


# The plan must cite a first-party support or standards body.  This list is
# intentionally explicit: a typo or an SEO summary site must stop the build.
OFFICIAL_SOURCE_HOSTS = {
    "account.microsoft.com",
    "canon.jp",
    "flets.com",
    "help.instagram.com",
    "help.line.me",
    "support.apple.com",
    "support.discord.com",
    "support.google.com",
    "support.microsoft.com",
    "support.tiktok.com",
    "support.zoom.com",
    "www.aterm.jp",
    "www.buffalo.jp",
    "www.epson.jp",
    "www.sdcard.org",
}


@dataclass(frozen=True)
class Article:
    url: str
    title: str
    description: str
    summary: str
    label: str
    category_url: str | None
    source_file: Path
    is_new: bool = False


def fail(message: str) -> None:
    raise SystemExit(f"build_content.py: {message}")


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def canonical_path(value: str) -> str:
    """Return one normalized, site-relative canonical path."""
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        if parsed.scheme != "https" or parsed.netloc != "sora-navi-jp.com":
            fail(f"unexpected canonical host: {value}")
        value = parsed.path
    if not value.startswith("/"):
        value = "/" + value
    if value != "/" and not value.endswith("/") and not value.endswith(".html"):
        value += "/"
    return value


def absolute_url(path: str) -> str:
    return BASE_URL + canonical_path(path)


def parse_iso_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        fail(f"--date must be YYYY-MM-DD, got {value!r}")
    raise AssertionError("unreachable")


def text(value: Any, field: str, *, minimum: int = 1) -> str:
    if not isinstance(value, str):
        fail(f"{field} must be a string")
    value = value.strip()
    if len(value) < minimum:
        fail(f"{field} is too short")
    if "\ufffd" in value:
        fail(f"{field} contains a Unicode replacement character")
    return value


def string_list(value: Any, field: str, *, minimum: int) -> list[str]:
    if not isinstance(value, list) or len(value) < minimum:
        fail(f"{field} must contain at least {minimum} entries")
    result = [text(item, f"{field}[{index}]", minimum=2) for index, item in enumerate(value)]
    if len(result) != len(set(result)):
        fail(f"{field} contains duplicate entries")
    return result


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(f"cannot read valid UTF-8 JSON from {path.relative_to(ROOT)}: {exc}")


def soup_from_path(path: Path) -> BeautifulSoup:
    try:
        return BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    except (OSError, UnicodeError) as exc:
        fail(f"cannot read {path.relative_to(ROOT)}: {exc}")


def serialize_html(soup: BeautifulSoup) -> str:
    rendered = soup.decode(formatter="minimal")
    rendered = rendered.replace(' defer=""', " defer")
    # BeautifulSoup's html.parser can alternate between ``<meta>`` and a
    # synthetic trailing ``</meta>`` across parse/serialize passes.  Normalize
    # HTML void elements so repeated builds are byte-for-byte stable.
    void_names = "area|base|br|col|embed|hr|img|input|link|meta|param|source|track|wbr"
    rendered = re.sub(rf"</(?:{void_names})\s*>", "", rendered, flags=re.IGNORECASE)
    rendered = re.sub(
        rf"<({void_names})(\b[^<>]*?)(?<!/)>",
        lambda match: f"<{match.group(1)}{match.group(2)}/>",
        rendered,
        flags=re.IGNORECASE,
    )
    if not rendered.lstrip().lower().startswith("<!doctype"):
        rendered = "<!doctype html>\n" + rendered
    return rendered.rstrip() + "\n"


def article_from_file(path: Path) -> Article:
    soup = soup_from_path(path)
    canonical = soup.select_one('link[rel="canonical"]')
    h1 = soup.find("h1")
    description = soup.select_one('meta[name="description"]')
    if not canonical or not canonical.get("href") or not h1 or not description or not description.get("content"):
        fail(f"article is missing canonical, H1, or description: {path.relative_to(ROOT)}")

    url = canonical_path(str(canonical["href"]))
    title_value = h1.get_text(" ", strip=True)
    description_value = str(description["content"]).strip()
    answer = soup.select_one(".answer-box p, article .lead")
    summary = answer.get_text(" ", strip=True) if answer else description_value

    category_link = soup.select_one('.breadcrumbs a[href^="/category/"]')
    category_url = canonical_path(str(category_link["href"])) if category_link else None
    eyebrow = soup.select_one(".page-hero .eyebrow")
    label = eyebrow.get_text(" ", strip=True) if eyebrow else "SNS・AIガイド"

    marker = soup.select_one('meta[name="sora-content-generator"]')
    is_new = bool(marker and marker.get("content") == GENERATOR_NAME)
    return Article(
        url=url,
        title=title_value,
        description=description_value,
        summary=summary,
        label=label,
        category_url=category_url,
        source_file=path.relative_to(ROOT),
        is_new=is_new,
    )


def scan_article_files() -> list[Article]:
    files: list[Path] = []
    for root_name in ALL_MODERN_ROOTS:
        root = ROOT / root_name
        if root.exists():
            files.extend(sorted(root.glob("*/index.html")))
    files.extend(sorted(path for path in (ROOT / "articles").glob("*.html") if path.name != "index.html"))
    articles = [article_from_file(path) for path in files]
    urls = [article.url for article in articles]
    if len(urls) != len(set(urls)):
        duplicates = sorted(url for url, count in Counter(urls).items() if count > 1)
        fail(f"duplicate existing canonicals: {duplicates}")
    return articles


def validate_base_articles(scanned: list[Article], plan_paths: set[str]) -> list[Article]:
    generated = [article for article in scanned if article.is_new]
    stale = sorted(article.url for article in generated if article.url not in plan_paths)
    if stale:
        fail(f"stale generated articles are not present in the plan: {stale}")

    base = [article for article in scanned if not article.is_new]
    legacy_count = sum(article.source_file.parent == Path("articles") for article in base)
    modern_count = len(base) - legacy_count
    if len(base) != EXPECTED_BASE_ARTICLES:
        fail(f"expected {EXPECTED_BASE_ARTICLES} base articles, found {len(base)}")
    if legacy_count != EXPECTED_LEGACY_ARTICLES or modern_count != EXPECTED_MODERN_ARTICLES:
        fail(
            "base article split changed: "
            f"legacy={legacy_count} (expected {EXPECTED_LEGACY_ARTICLES}), "
            f"modern={modern_count} (expected {EXPECTED_MODERN_ARTICLES})"
        )
    return base


def validate_plan(raw: Any, base_articles: list[Article]) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or len(raw) != EXPECTED_NEW_ARTICLES:
        fail(f"plan must contain exactly {EXPECTED_NEW_ARTICLES} records")

    base_urls = {article.url for article in base_articles}
    base_titles = {article.title for article in base_articles}
    normalized: list[dict[str, Any]] = []
    required = {
        "topic",
        "category",
        "path",
        "slug",
        "title",
        "answer",
        "steps",
        "causes",
        "escalation",
        "source_label",
        "source_url",
        "related_existing",
    }

    for index, raw_record in enumerate(raw):
        prefix = f"plan[{index}]"
        if not isinstance(raw_record, dict):
            fail(f"{prefix} must be an object")
        missing = sorted(required - raw_record.keys())
        if missing:
            fail(f"{prefix} is missing fields: {missing}")

        category = text(raw_record["category"], f"{prefix}.category")
        if category not in CATEGORY_CONFIG:
            fail(f"{prefix}.category is unsupported: {category}")
        slug = text(raw_record["slug"], f"{prefix}.slug")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            fail(f"{prefix}.slug is not a safe URL slug: {slug}")
        path = canonical_path(text(raw_record["path"], f"{prefix}.path"))
        expected_path = f"/{category}/{slug}/"
        if path != expected_path:
            fail(f"{prefix}.path must be {expected_path}, got {path}")
        if path in base_urls:
            fail(f"{prefix}.path collides with a base article: {path}")

        title_value = text(raw_record["title"], f"{prefix}.title", minimum=8)
        if title_value in base_titles:
            fail(f"{prefix}.title duplicates a base article: {title_value}")
        answer = text(raw_record["answer"], f"{prefix}.answer", minimum=28)
        topic = text(raw_record["topic"], f"{prefix}.topic", minimum=4)
        steps = string_list(raw_record["steps"], f"{prefix}.steps", minimum=4)
        causes = string_list(raw_record["causes"], f"{prefix}.causes", minimum=3)
        escalation = text(raw_record["escalation"], f"{prefix}.escalation", minimum=18)
        source_label = text(raw_record["source_label"], f"{prefix}.source_label", minimum=3)
        source_url = text(raw_record["source_url"], f"{prefix}.source_url")
        parsed_source = urlparse(source_url)
        if parsed_source.scheme != "https" or parsed_source.hostname not in OFFICIAL_SOURCE_HOSTS:
            fail(f"{prefix}.source_url is not an approved first-party HTTPS source: {source_url}")
        related = [canonical_path(item) for item in string_list(
            raw_record["related_existing"], f"{prefix}.related_existing", minimum=3
        )]
        if path in related:
            fail(f"{prefix}.related_existing links to itself")

        description = raw_record.get("description")
        if description is None:
            if title_value.endswith("方法"):
                description = f"{title_value}を、原因の切り分けからデータを消さずに試せる対処まで順番に解説します。"
            else:
                description = f"{title_value}ときに、原因を切り分け、データを消さずに試せる対処手順を解説します。"
        description = text(description, f"{prefix}.description", minimum=30)
        if len(description) > 180:
            fail(f"{prefix}.description exceeds 180 characters")

        normalized.append({
            "topic": topic,
            "category": category,
            "path": path,
            "slug": slug,
            "title": title_value,
            "description": description,
            "answer": answer,
            "steps": steps,
            "causes": causes,
            "escalation": escalation,
            "source_label": source_label,
            "source_url": source_url,
            "related_existing": related,
        })

    for key in ("path", "slug", "title", "topic"):
        values = [record[key] for record in normalized]
        duplicates = sorted(value for value, count in Counter(values).items() if count > 1)
        if duplicates:
            fail(f"plan contains duplicate {key} values: {duplicates}")

    planned_urls = {record["path"] for record in normalized}
    valid_related = base_urls | planned_urls
    broken_related = sorted({
        related
        for record in normalized
        for related in record["related_existing"]
        if related not in valid_related
    })
    if broken_related:
        fail(f"plan has related links that are not public articles: {broken_related}")

    # Existing generated files are allowed only when they carry our marker.
    for record in normalized:
        target = ROOT / record["category"] / record["slug"] / "index.html"
        if target.exists():
            marker = soup_from_path(target).select_one('meta[name="sora-content-generator"]')
            if not marker or marker.get("content") != GENERATOR_NAME:
                fail(f"refusing to overwrite an unmarked file: {target.relative_to(ROOT)}")
    return normalized


def json_for_script(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def display_date(value: str) -> str:
    year, month, day = value.split("-")
    return f"{int(year)}年{int(month)}月{int(day)}日"


def estimate_minutes(record: dict[str, Any]) -> int:
    length = sum(len(str(item)) for item in (
        [record["answer"], record["escalation"]] + record["steps"] + record["causes"]
    ))
    return max(4, min(7, round(length / 220) + 3))


def generated_article(record: dict[str, Any]) -> Article:
    config = CATEGORY_CONFIG[record["category"]]
    return Article(
        url=record["path"],
        title=record["title"],
        description=record["description"],
        summary=record["answer"],
        label=config["label"],
        category_url=config["category_url"],
        source_file=Path(record["category"]) / record["slug"] / "index.html",
        is_new=True,
    )


def select_related(
    record: dict[str, Any],
    article_by_url: dict[str, Article],
    base_articles: list[Article],
) -> list[Article]:
    selected_urls: list[str] = []
    for url in record["related_existing"]:
        if url != record["path"] and url not in selected_urls:
            selected_urls.append(url)

    category_url = CATEGORY_CONFIG[record["category"]]["category_url"]
    for article in base_articles:
        if article.category_url == category_url and article.url not in selected_urls:
            selected_urls.append(article.url)
        if len(selected_urls) >= 4:
            break
    if len(selected_urls) < 4:
        for article in base_articles:
            if article.url not in selected_urls:
                selected_urls.append(article.url)
            if len(selected_urls) >= 4:
                break
    selected_urls = selected_urls[:4]
    if len(selected_urls) != 4 or any(url not in article_by_url for url in selected_urls):
        fail(f"could not resolve four related articles for {record['path']}")
    return [article_by_url[url] for url in selected_urls]


def render_visual(record: dict[str, Any]) -> str:
    slug = html.escape(record["slug"], quote=True)
    title_value = html.escape(record["title"])
    return f'''<figure class="sora-guide-visual">
<svg class="sora-guide-visual-wide" role="img" aria-labelledby="flow-title-{slug}" aria-describedby="flow-desc-{slug}" viewBox="0 0 960 250" xmlns="http://www.w3.org/2000/svg">
<title id="flow-title-{slug}">{title_value}を安全に切り分ける3段階</title>
<desc id="flow-desc-{slug}">症状の範囲を確認し、データを消さない対処から試し、結果に応じて相談先を判断する流れです。</desc>
<defs><linearGradient id="flow-{slug}" x1="0" x2="1"><stop stop-color="#1749d5"/><stop offset="1" stop-color="#08a8dc"/></linearGradient></defs>
<path d="M255 116h65M640 116h65" stroke="#9fb5d8" stroke-width="7" stroke-linecap="round"/>
<path d="M307 101l18 15-18 15M692 101l18 15-18 15" fill="none" stroke="#9fb5d8" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>
<g><rect x="18" y="25" width="235" height="182" rx="28" fill="#fff" stroke="#c8d7ed" stroke-width="2"/><circle cx="71" cy="78" r="30" fill="url(#flow-{slug})"/><path d="M57 78l9 9 20-22" fill="none" stroke="#fff" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/><text x="119" y="70" fill="#1749d5" font-size="20" font-weight="800">STEP 1</text><text x="119" y="101" fill="#10233f" font-size="25" font-weight="800">範囲を確認</text><text x="43" y="157" fill="#60718a" font-size="18">どこで起きるかを</text><text x="43" y="183" fill="#60718a" font-size="18">比較して分ける</text></g>
<g><rect x="362" y="25" width="235" height="182" rx="28" fill="#fff" stroke="#9fb9ef" stroke-width="3"/><circle cx="415" cy="78" r="30" fill="url(#flow-{slug})"/><path d="M403 78h24M415 66v24" stroke="#fff" stroke-width="7" stroke-linecap="round"/><text x="463" y="70" fill="#1749d5" font-size="20" font-weight="800">STEP 2</text><text x="463" y="101" fill="#10233f" font-size="25" font-weight="800">安全に試す</text><text x="387" y="157" fill="#60718a" font-size="18">削除や初期化を</text><text x="387" y="183" fill="#60718a" font-size="18">避けて順に確認</text></g>
<g><rect x="706" y="25" width="235" height="182" rx="28" fill="#fff" stroke="#c8d7ed" stroke-width="2"/><circle cx="759" cy="78" r="30" fill="#0c9b7b"/><path d="M746 79l9 9 19-23" fill="none" stroke="#fff" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/><text x="807" y="70" fill="#0c8268" font-size="20" font-weight="800">STEP 3</text><text x="807" y="101" fill="#10233f" font-size="25" font-weight="800">結果で判断</text><text x="731" y="157" fill="#60718a" font-size="18">直らない条件を</text><text x="731" y="183" fill="#60718a" font-size="18">記録して相談</text></g>
</svg>
<svg class="sora-guide-visual-mobile" role="img" aria-labelledby="flow-mobile-title-{slug}" aria-describedby="flow-mobile-desc-{slug}" viewBox="0 0 320 570" xmlns="http://www.w3.org/2000/svg">
<title id="flow-mobile-title-{slug}">{title_value}を安全に切り分ける3段階</title>
<desc id="flow-mobile-desc-{slug}">症状の範囲を確認し、データを消さない対処から試し、結果に応じて相談先を判断する流れです。</desc>
<defs><linearGradient id="flow-mobile-{slug}" x1="0" x2="1"><stop stop-color="#1749d5"/><stop offset="1" stop-color="#08a8dc"/></linearGradient></defs>
<path d="M160 166v34M160 356v34" stroke="#9fb5d8" stroke-width="6" stroke-linecap="round"/><path d="M146 188l14 16 14-16M146 378l14 16 14-16" fill="none" stroke="#9fb5d8" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>
<g><rect x="12" y="10" width="296" height="156" rx="24" fill="#fff" stroke="#c8d7ed" stroke-width="2"/><circle cx="56" cy="55" r="25" fill="url(#flow-mobile-{slug})"/><path d="M45 55l8 8 17-19" fill="none" stroke="#fff" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/><text x="92" y="49" fill="#1749d5" font-size="16" font-weight="800">STEP 1</text><text x="92" y="75" fill="#10233f" font-size="23" font-weight="800">範囲を確認</text><text x="35" y="119" fill="#60718a" font-size="16">どこで起きるかを比較して分ける</text></g>
<g><rect x="12" y="200" width="296" height="156" rx="24" fill="#fff" stroke="#9fb9ef" stroke-width="3"/><circle cx="56" cy="245" r="25" fill="url(#flow-mobile-{slug})"/><path d="M46 245h20M56 235v20" stroke="#fff" stroke-width="6" stroke-linecap="round"/><text x="92" y="239" fill="#1749d5" font-size="16" font-weight="800">STEP 2</text><text x="92" y="265" fill="#10233f" font-size="23" font-weight="800">安全に試す</text><text x="35" y="309" fill="#60718a" font-size="16">削除や初期化を避けて順に確認する</text></g>
<g><rect x="12" y="390" width="296" height="156" rx="24" fill="#fff" stroke="#c8d7ed" stroke-width="2"/><circle cx="56" cy="435" r="25" fill="#0c9b7b"/><path d="M45 435l8 8 17-19" fill="none" stroke="#fff" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/><text x="92" y="429" fill="#0c8268" font-size="16" font-weight="800">STEP 3</text><text x="92" y="455" fill="#10233f" font-size="23" font-weight="800">結果で判断</text><text x="35" y="499" fill="#60718a" font-size="16">直らない条件を記録して相談する</text></g>
</svg>
<figcaption>初期化や削除を急がず、各手順の結果を確認しながら次へ進みます。</figcaption></figure>'''


def render_article(
    record: dict[str, Any],
    related: list[Article],
    publish_date: str,
) -> str:
    config = CATEGORY_CONFIG[record["category"]]
    canonical = absolute_url(record["path"])
    title_value = record["title"]
    description = record["description"]
    label = config["label"]
    category_url = config["category_url"]

    website_schema = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "@id": f"{BASE_URL}/#website",
                "url": f"{BASE_URL}/",
                "name": "直るナビ",
                "description": "スマートフォン、PC、ブラウザ、Webサービス、SNS、周辺機器の不調を自分で切り分けるためのデジタルトラブル解決ガイドです。",
                "inLanguage": "ja-JP",
                "publisher": {"@id": f"{BASE_URL}/#organization"},
            },
            {
                "@type": "Organization",
                "@id": f"{BASE_URL}/#organization",
                "name": "直るナビ編集部",
                "url": f"{BASE_URL}/",
            },
        ],
    }
    page_schema = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Article",
                "@id": canonical + "#article",
                "headline": title_value,
                "description": description,
                "datePublished": publish_date,
                "dateModified": publish_date,
                "inLanguage": "ja-JP",
                "mainEntityOfPage": canonical,
                "author": {"@type": "Organization", "name": "直るナビ編集部"},
                "publisher": {"@id": f"{BASE_URL}/#organization"},
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "トップ", "item": f"{BASE_URL}/"},
                    {"@type": "ListItem", "position": 2, "name": label, "item": absolute_url(category_url)},
                    {"@type": "ListItem", "position": 3, "name": title_value, "item": canonical},
                ],
            },
        ],
    }

    esc = html.escape
    first_steps = "".join(f"<li>{esc(step)}</li>" for step in record["steps"][:3])
    all_steps = "".join(f"<li>{esc(step)}</li>" for step in record["steps"])
    causes = "".join(f"<li>{esc(cause)}</li>" for cause in record["causes"])
    checks = "".join(f"<li>{esc(check)}</li>" for check in config["checks"])
    related_cards = "".join(
        f'''<a class="static-card" href="{esc(article.url, quote=True)}" target="_top"><h3>{esc(article.title)}</h3><p>{esc(article.summary)}</p><span class="text-link">対処手順を見る →</span></a>'''
        for article in related
    )
    minutes = estimate_minutes(record)
    display_published = display_date(publish_date)
    visual = render_visual(record)

    return f'''<!doctype html>
<html class="sora-ui-v2" lang="ja"><head>
<meta name="google-adsense-account" content="ca-pub-9899251547801313"/>
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-9899251547801313" crossorigin="anonymous"></script>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta name="sora-content-generator" content="{GENERATOR_NAME}"/>
<link href="/assets/css/naoru-navi.css" rel="stylesheet"/><link href="/assets/css/site-v2.css?v={ASSET_VERSION}" rel="stylesheet"/>
<link href="/assets/img/favicon.svg" rel="icon" type="image/svg+xml"/><meta name="theme-color" content="#1646d8"/>
<title>{esc(title_value)}｜直るナビ</title><meta name="description" content="{esc(description, quote=True)}"/>
<link href="{esc(canonical, quote=True)}" rel="canonical"/>
<meta property="og:title" content="{esc(title_value, quote=True)}"/><meta property="og:description" content="{esc(description, quote=True)}"/>
<meta property="og:type" content="article"/><meta property="og:url" content="{esc(canonical, quote=True)}"/><meta property="og:image" content="{BASE_URL}/og.png"/>
<meta name="twitter:card" content="summary"/><meta name="twitter:title" content="{esc(title_value, quote=True)}"/>
<meta name="twitter:description" content="{esc(description, quote=True)}"/><meta name="twitter:image" content="{BASE_URL}/og.png"/>
<script type="application/ld+json">{json_for_script(website_schema)}</script></head><body class="sora-article-page">
<header class="site-header sora-v2-header"><div class="sora-v2-header-inner"><a aria-label="直るナビ トップページ" class="sora-v2-brand" href="/"><span aria-hidden="true" class="sora-v2-brand-mark">✓</span><span><strong>直るナビ</strong><small>困ったを、安全な順番で解決。</small></span></a><button aria-controls="sora-v2-nav" aria-expanded="false" aria-label="メニューを開く" class="sora-v2-menu" type="button">☰</button><nav aria-label="メインナビゲーション" class="sora-v2-nav" id="sora-v2-nav"><a href="/">トップ</a><a href="/categories/">カテゴリ</a><a href="/articles/">全400記事</a><a href="/articles.html">SNS・AI</a><a href="/about/">このサイトについて</a></nav></div></header>
<main><script type="application/ld+json">{json_for_script(page_schema)}</script>
<section class="page-hero"><div class="wrap"><nav aria-label="パンくずリスト" class="breadcrumbs"><ol><li><a href="/">トップ</a></li><li><a href="{esc(category_url, quote=True)}">{esc(label)}</a></li><li><span aria-current="page">{esc(title_value)}</span></li></ol></nav><span class="eyebrow">{esc(label)}</span><h1 class="article-title">{esc(title_value)}</h1><p class="article-lead">{esc(description)}</p><div class="article-meta"><span>公開・更新：{display_published}</span><span>読了目安：{minutes}分</span><span>確認済み：{esc(record['source_label'])}</span></div></div></section>
<div class="wrap article-layout content-section"><article class="article-body"><div class="answer-box"><span class="eyebrow">結論</span><p>{esc(record['answer'])}</p></div>
{visual}
<h2 id="first">まず試すこと</h2><p>設定をまとめて変えず、次の操作を1つずつ試してください。各手順のあとに症状を確認すると、原因を絞りやすくなります。</p><ol class="step-list">{first_steps}</ol>
<h2 id="scope">症状を切り分ける</h2><p>「{esc(record['topic'])}」の範囲を先に確認します。端末、接続先、アカウントなど条件を1つだけ変えて比べると、不要な削除や初期化を避けられます。</p><ul class="check-list">{checks}</ul>
<h2 id="causes">考えられる原因</h2><p>表示や発生条件が次のどれに近いかを確認してください。複数が重なる場合もあるため、決めつけず上から順に切り分けます。</p><ul>{causes}</ul>
<h2 id="steps">解決手順</h2><p>途中で改善したら残りの操作は不要です。改善しなかった手順と画面表示をメモしておくと、次の判断や相談がしやすくなります。</p><ol class="step-list">{all_steps}</ol>
<h2 id="help">解決しない場合</h2><p>{esc(record['escalation'])}</p><p>相談時は、症状が始まった日時、再現条件、表示された文言、試した手順と結果を伝えてください。</p>
<h2 id="caution">注意点</h2><div class="info-box"><strong>削除や初期化は最後に行います</strong>{esc(config['safety'])}</div>
<aside aria-label="広告" class="admax-slot sora-ad-slot sora-mobile-inline-ad"><span class="admax-label">広告</span><div class="admax-content"><div class="admax-ads" data-admax-id="23a16b749b5224c46c26784399bdfcad" style="display:inline-block"></div></div></aside>
<h2 id="related">関連するトラブル</h2><div class="static-grid">{related_cards}</div>
<div class="source-note"><strong>参考にした一次情報</strong><br/><a href="{esc(record['source_url'], quote=True)}" rel="noopener noreferrer" target="_blank">{esc(record['source_label'])}</a><p>画面名や利用条件はOS・機種・地域・アプリのバージョンで異なる場合があります。実際の画面と公式案内を優先してください。</p></div>
</article><aside aria-label="記事ナビゲーション" class="article-sidebar"><div class="side-card"><strong>このページの順番</strong><a href="#first">1. まず試す</a><a href="#scope">2. 範囲を確認</a><a href="#causes">3. 原因を確認</a><a href="#steps">4. 解決手順</a><a href="#help">5. 解決しない場合</a></div><div class="side-card"><strong>{esc(label)}の記事</strong><a href="{esc(category_url, quote=True)}">カテゴリ一覧を見る →</a><a href="/articles/">全400記事を見る →</a></div></aside></div></main>
<footer class="site-footer sora-v2-footer"><div class="sora-v2-footer-grid"><div><a aria-label="直るナビ トップページ" class="sora-v2-brand" href="/"><span aria-hidden="true" class="sora-v2-brand-mark">✓</span><span><strong>直るナビ</strong><small>困ったを、安全な順番で解決。</small></span></a><p>スマホ、PC、ブラウザ、Webサービスの不調を、危険の少ない確認から順番に切り分ける実用ガイドです。</p></div><nav aria-label="フッターのガイド"><strong>ガイド</strong><a href="/articles/">全400記事</a><a href="/categories/">カテゴリ一覧</a><a href="/iphone/">iPhone</a><a href="/articles.html">SNS・AI</a></nav><nav aria-label="運営情報"><strong>運営情報</strong><a href="/about/">このサイトについて</a><a href="/contact/">お問い合わせ</a><a href="/privacy/">プライバシー</a><a href="/disclaimer/">免責事項</a></nav></div><div class="sora-v2-footer-bottom">© 2026 直るナビ　重要な操作は各サービスの公式情報もご確認ください。</div></footer>
<script src="/assets/js/ad-loader.js?v={ASSET_VERSION}"></script><script defer src="/assets/js/site-v2.js?v={ASSET_VERSION}"></script></body></html>
'''


def article_card(article: Article, *, include_description: bool = True) -> str:
    description = f"<p>{html.escape(article.summary)}</p>" if include_description else ""
    return (
        f'<a class="article-card" href="{html.escape(article.url, quote=True)}" target="_top">'
        f'<span class="eyebrow">{html.escape(article.label)}</span>'
        f'<h3>{html.escape(article.title)}</h3>{description}'
        '<span class="text-link">対処手順を見る <span aria-hidden="true">→</span></span></a>'
    )


def replace_children_with_html(container: Tag, fragments: Iterable[str]) -> None:
    container.clear()
    for fragment in fragments:
        parsed = BeautifulSoup(fragment, "html.parser")
        node = parsed.find()
        if node is None:
            fail("internal error: empty HTML fragment")
        container.append(node)


def set_meta_content(soup: BeautifulSoup, selector: str, value: str) -> None:
    node = soup.select_one(selector)
    if node:
        node["content"] = value


def replace_visible_count(node: Tag, count: int, unit: str = "件") -> None:
    value = node.get_text(" ", strip=True)
    replacement = f"{count}{unit}"
    updated, substitutions = re.subn(r"\d+\s*" + re.escape(unit), replacement, value, count=1)
    if substitutions == 0:
        updated = f"{value}（{replacement}）"
    node.clear()
    node.append(NavigableString(updated))


def build_master_index(articles: list[Article]) -> str:
    path = ROOT / "articles" / "index.html"
    soup = soup_from_path(path)
    listing = soup.select_one(".article-list")
    hero_text = soup.select_one(".page-hero p")
    if not listing or not hero_text:
        fail("articles/index.html no longer has the expected hero and article list")

    h1 = soup.find("h1")
    if not h1:
        fail("articles/index.html has no H1")
    h1.string = "全400記事から探す"
    if soup.title:
        soup.title.string = "全400記事一覧｜直るナビ"
    hero_text.string = "現在公開しているスマホ・PC・ブラウザ・Webサービス・SNS・AIのトラブル解決ガイド全400記事です。"
    listing["data-article-count"] = str(len(articles))
    replace_children_with_html(listing, (article_card(article) for article in articles))
    description = "直るナビで公開中の全400記事を、スマホ・PC・ブラウザ・Webサービス・SNS・AIなどの悩みから検索できます。"
    set_meta_content(soup, 'meta[name="description"]', description)
    set_meta_content(soup, 'meta[property="og:description"]', description)
    set_meta_content(soup, 'meta[name="twitter:description"]', description)
    set_meta_content(soup, 'meta[property="og:title"]', "全400記事一覧｜直るナビ")
    set_meta_content(soup, 'meta[name="twitter:title"]', "全400記事一覧｜直るナビ")
    return serialize_html(soup)


def build_category_page(category_file: Path, articles: list[Article]) -> str:
    soup = soup_from_path(category_file)
    listing = soup.select_one(".article-list")
    hero_text = soup.select_one(".page-hero p")
    if not listing or not hero_text:
        fail(f"category page structure changed: {category_file.relative_to(ROOT)}")
    replace_visible_count(hero_text, len(articles), "件")
    for selector in ('meta[name="description"]', 'meta[property="og:description"]', 'meta[name="twitter:description"]'):
        node = soup.select_one(selector)
        if node and node.get("content"):
            node["content"] = re.sub(r"\d+\s*件", f"{len(articles)}件", str(node["content"]), count=1)
    listing["data-article-count"] = str(len(articles))
    replace_children_with_html(listing, (article_card(article) for article in articles))
    return serialize_html(soup)


def build_categories_index(by_category: dict[str, list[Article]]) -> str:
    path = ROOT / "categories" / "index.html"
    soup = soup_from_path(path)
    cards = soup.select('.category-card[href^="/category/"]')
    if len(cards) != 19:
        fail(f"expected 19 category cards, found {len(cards)}")
    for card in cards:
        category_url = canonical_path(str(card.get("href", "")))
        if category_url not in by_category:
            fail(f"category card has no articles: {category_url}")
        small = card.find("small")
        if not small:
            fail(f"category card has no description: {category_url}")
        count = len(by_category[category_url])
        current = small.get_text(" ", strip=True)
        if re.search(r"・\d+記事$", current):
            updated = re.sub(r"・\d+記事$", f"・{count}記事", current)
        else:
            updated = f"{current}・{count}記事"
        small.string = updated
        card["data-article-count"] = str(count)
    return serialize_html(soup)


def build_homepage(new_articles: list[Article]) -> str:
    path = ROOT / "index.html"
    soup = soup_from_path(path)
    kicker = soup.select_one(".hero .kicker")
    latest = soup.select_one(".article-list.compact")
    if not kicker or not latest:
        fail("index.html no longer has the expected hero kicker and new-article list")

    kicker.clear()
    dot = soup.new_tag("span")
    dot["aria-hidden"] = "true"
    dot.string = "●"
    kicker.append(dot)
    kicker.append(NavigableString(" 全400記事を公開中"))
    latest["data-article-count"] = str(len(new_articles))
    replace_children_with_html(latest, (article_card(article, include_description=False) for article in new_articles))

    windows_count = 15 + sum(article.category_url == "/category/windows/" for article in new_articles)
    windows_card = soup.select_one('.device-card[href="/category/windows/"] small')
    if windows_card:
        windows_card.string = f"{windows_count}件のトラブル解決ガイド"
    return serialize_html(soup)


def build_legacy_index() -> str:
    """Make the retained 153-page archive distinct from the 400-page master."""
    path = ROOT / "articles.html"
    soup = soup_from_path(path)
    if soup.title:
        soup.title.string = "SNS・AIガイド153記事｜直るナビ"
    h1 = soup.find("h1")
    if not h1:
        fail("articles.html has no H1")
    h1.string = "SNS・AIガイド153記事"
    eyebrow = h1.find_previous(class_="eyebrow")
    if eyebrow:
        eyebrow.string = "SNS & AI ARCHIVE"
    description = "直るナビで継続公開しているSNS・スマホ・学校・ネット安全・生成AIの153記事を検索できます。全記事一覧は別ページで確認できます。"
    set_meta_content(soup, 'meta[name="description"]', description)
    set_meta_content(soup, 'meta[property="og:description"]', description)
    set_meta_content(soup, 'meta[name="twitter:description"]', description)
    set_meta_content(soup, 'meta[property="og:title"]', "SNS・AIガイド153記事｜直るナビ")
    set_meta_content(soup, 'meta[name="twitter:title"]', "SNS・AIガイド153記事｜直るナビ")
    hero_paragraph = h1.find_next("p")
    if hero_paragraph:
        hero_paragraph.string = "SNS・スマホの困りごと53記事と、生成AIを使いこなす「AIラクワザ」100記事をまとめた既存ガイドです。全400記事は記事一覧から検索できます。"
    return serialize_html(soup)


def current_base_order(base_articles: list[Article], plan_paths: set[str]) -> list[Article]:
    raw = read_json(SEARCH_PATH)
    ordered_urls: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and isinstance(item.get("url"), str):
                url = canonical_path(item["url"])
                if url not in plan_paths and url not in ordered_urls:
                    ordered_urls.append(url)
    by_url = {article.url: article for article in base_articles}
    result = [by_url[url] for url in ordered_urls if url in by_url]
    seen = {article.url for article in result}
    result.extend(sorted((article for article in base_articles if article.url not in seen), key=lambda item: item.url))
    if len(result) != EXPECTED_BASE_ARTICLES:
        fail("could not establish a stable order for all base articles")
    return result


def parse_sitemap() -> tuple[list[str], dict[str, dict[str, str]]]:
    try:
        root = ET.parse(SITEMAP_XML_PATH).getroot()
    except (OSError, ET.ParseError) as exc:
        fail(f"cannot parse sitemap.xml: {exc}")
    order: list[str] = []
    metadata: dict[str, dict[str, str]] = {}
    for url_node in root:
        fields = {local_name(child.tag): (child.text or "").strip() for child in url_node}
        loc = fields.pop("loc", "")
        if not loc:
            fail("sitemap.xml contains a URL without loc")
        if loc in metadata:
            fail(f"sitemap.xml contains a duplicate URL: {loc}")
        order.append(loc)
        metadata[loc] = fields
    return order, metadata


def render_sitemap(
    article_order: list[Article],
    new_paths: set[str],
    publish_date: str,
) -> tuple[str, str, list[str]]:
    old_order, old_metadata = parse_sitemap()
    article_urls = [absolute_url(article.url) for article in article_order]
    article_url_set = set(article_urls)
    non_article_urls = [url for url in old_order if url not in article_url_set]
    if len(non_article_urls) != EXPECTED_NON_ARTICLE_URLS:
        fail(
            f"expected {EXPECTED_NON_ARTICLE_URLS} non-article sitemap URLs, "
            f"found {len(non_article_urls)}"
        )
    final_urls = non_article_urls + article_urls
    if len(final_urls) != EXPECTED_SITEMAP_URLS or len(final_urls) != len(set(final_urls)):
        fail(f"sitemap would contain {len(final_urls)} URLs instead of {EXPECTED_SITEMAP_URLS}, or has duplicates")

    lines = ["<?xml version='1.0' encoding='utf-8'?>", '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url in final_urls:
        lines.append("  <url>")
        lines.append(f"    <loc>{html.escape(url)}</loc>")
        path = canonical_path(url)
        fields = dict(old_metadata.get(url, {}))
        if path in new_paths:
            fields["lastmod"] = publish_date
        for field_name in ("lastmod", "changefreq", "priority"):
            field_value = fields.get(field_name)
            if field_value:
                lines.append(f"    <{field_name}>{html.escape(field_value)}</{field_name}>")
        lines.append("  </url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n", "\n".join(final_urls) + "\n", final_urls


def validate_generated_html(record: dict[str, Any], rendered: str, all_urls: set[str]) -> None:
    soup = BeautifulSoup(rendered, "html.parser")
    canonical = soup.select_one('link[rel="canonical"]')
    og_url = soup.select_one('meta[property="og:url"]')
    h1 = soup.find("h1")
    description = soup.select_one('meta[name="description"]')
    if not canonical or canonical.get("href") != absolute_url(record["path"]):
        fail(f"generated canonical mismatch: {record['path']}")
    if not og_url or og_url.get("content") != absolute_url(record["path"]):
        fail(f"generated og:url mismatch: {record['path']}")
    if not h1 or h1.get_text(" ", strip=True) != record["title"] or not description:
        fail(f"generated title/H1/description mismatch: {record['path']}")
    schemas: list[Any] = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            schemas.append(json.loads(script.get_text()))
        except json.JSONDecodeError as exc:
            fail(f"invalid JSON-LD in {record['path']}: {exc}")
    flattened_types = {
        node.get("@type")
        for schema in schemas
        for node in (schema.get("@graph", []) if isinstance(schema, dict) else [])
        if isinstance(node, dict)
    }
    if not {"Article", "BreadcrumbList"}.issubset(flattened_types):
        fail(f"Article or Breadcrumb JSON-LD missing: {record['path']}")
    if len(soup.select('.admax-ads[data-admax-id="23a16b749b5224c46c26784399bdfcad"]')) != 1:
        fail(f"Ninja AdMax marker mismatch: {record['path']}")
    ad_script = f"/assets/js/ad-loader.js?v={ASSET_VERSION}"
    site_script = f"/assets/js/site-v2.js?v={ASSET_VERSION}"
    site_style = f"/assets/css/site-v2.css?v={ASSET_VERSION}"
    if len(soup.find_all("script", src=ad_script)) != 1:
        fail(f"Ninja AdMax loader mismatch: {record['path']}")
    if len(soup.find_all("script", src=site_script)) != 1:
        fail(f"site-v2 loader mismatch: {record['path']}")
    if len(soup.find_all("link", href=site_style)) != 1:
        fail(f"site-v2 stylesheet mismatch: {record['path']}")
    html_node = soup.find("html")
    body = soup.find("body")
    if not html_node or "sora-ui-v2" not in html_node.get("class", []):
        fail(f"static v2 HTML class missing: {record['path']}")
    if not body or "sora-article-page" not in body.get("class", []):
        fail(f"static article body class missing: {record['path']}")
    if not soup.select_one("header.site-header.sora-v2-header .sora-v2-menu[aria-controls='sora-v2-nav']"):
        fail(f"static v2 header missing: {record['path']}")
    if not soup.select_one("footer.site-footer.sora-v2-footer"):
        fail(f"static v2 footer missing: {record['path']}")
    wide = soup.select_one("figure.sora-guide-visual svg.sora-guide-visual-wide[role=img] title")
    mobile = soup.select_one("figure.sora-guide-visual svg.sora-guide-visual-mobile[role=img] title")
    if not wide or not mobile or len(soup.select("figure.sora-guide-visual svg[role=img]")) != 2:
        fail(f"accessible desktop/mobile guide SVGs missing: {record['path']}")
    related = [canonical_path(str(link.get("href"))) for link in soup.select(".static-grid a[href]")]
    if len(related) != 4 or any(url not in all_urls for url in related):
        fail(f"related article block is incomplete or broken: {record['path']}")
    source = soup.select_one('.source-note a[href^="https://"]')
    if not source or source.get("href") != record["source_url"]:
        fail(f"official source link mismatch: {record['path']}")


def validate_listing(rendered: str, expected: int, selector: str = ".article-card") -> None:
    soup = BeautifulSoup(rendered, "html.parser")
    cards = soup.select(selector)
    if len(cards) != expected:
        fail(f"generated listing has {len(cards)} cards instead of {expected}")
    hrefs = [canonical_path(str(card.get("href", ""))) for card in cards]
    if len(hrefs) != len(set(hrefs)):
        fail("generated listing contains duplicate article links")


def atomic_write(path: Path, content: str) -> bool:
    encoded = content.encode("utf-8")
    if path.exists() and path.read_bytes() == encoded:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return True


def build(publish_date: str, *, check_only: bool) -> None:
    raw_plan = read_json(PLAN_PATH)
    provisional_paths = {
        canonical_path(record.get("path", ""))
        for record in raw_plan
        if isinstance(record, dict) and isinstance(record.get("path"), str)
    } if isinstance(raw_plan, list) else set()
    scanned = scan_article_files()
    base_articles = validate_base_articles(scanned, provisional_paths)
    plan = validate_plan(raw_plan, base_articles)
    plan_paths = {record["path"] for record in plan}
    base_order = current_base_order(base_articles, plan_paths)

    new_articles = [generated_article(record) for record in plan]
    all_articles = new_articles + base_order
    if len(all_articles) != EXPECTED_TOTAL_ARTICLES:
        fail(f"article total is {len(all_articles)}, expected {EXPECTED_TOTAL_ARTICLES}")
    all_urls = [article.url for article in all_articles]
    all_titles = [article.title for article in all_articles]
    if len(all_urls) != len(set(all_urls)) or len(all_titles) != len(set(all_titles)):
        fail("all-article set contains duplicate URL or title")
    article_by_url = {article.url: article for article in all_articles}

    outputs: dict[Path, str] = {}
    for record in plan:
        related = select_related(record, article_by_url, base_articles)
        outputs[ROOT / record["category"] / record["slug"] / "index.html"] = render_article(
            record, related, publish_date
        )

    outputs[ROOT / "articles" / "index.html"] = build_master_index(all_articles)
    outputs[ROOT / "categories" / "index.html"] = ""  # Filled after category grouping.
    outputs[ROOT / "articles.html"] = build_legacy_index()

    by_category: dict[str, list[Article]] = defaultdict(list)
    for article in all_articles:
        if article.category_url:
            by_category[article.category_url].append(article)

    category_files = sorted((ROOT / "category").glob("*/index.html"))
    if len(category_files) != 19:
        fail(f"expected 19 category pages, found {len(category_files)}")
    for category_file in category_files:
        category_url = f"/category/{category_file.parent.name}/"
        category_articles = by_category.get(category_url, [])
        if not category_articles:
            fail(f"no articles found for category page {category_url}")
        outputs[category_file] = build_category_page(category_file, category_articles)
    outputs[ROOT / "categories" / "index.html"] = build_categories_index(by_category)

    homepage_articles: list[Article] = []
    for category in CATEGORY_CONFIG:
        article = next((item for item in new_articles if item.url.startswith(f"/{category}/")), None)
        if article:
            homepage_articles.append(article)
    if len(homepage_articles) != len(CATEGORY_CONFIG):
        fail("could not select one homepage article for every expanded category")
    outputs[ROOT / "index.html"] = build_homepage(homepage_articles)

    search_data = [
        {"title": article.title, "description": article.description, "url": article.url}
        for article in all_articles
    ]
    if len(search_data) != EXPECTED_TOTAL_ARTICLES:
        fail("search index is not exactly 400 records")
    outputs[SEARCH_PATH] = json.dumps(search_data, ensure_ascii=False, indent=2) + "\n"

    sitemap_xml, sitemap_txt, sitemap_urls = render_sitemap(all_articles, plan_paths, publish_date)
    if len(sitemap_urls) != EXPECTED_SITEMAP_URLS:
        fail("sitemap validation failed")
    outputs[SITEMAP_XML_PATH] = sitemap_xml
    outputs[SITEMAP_TXT_PATH] = sitemap_txt

    # Validate every generated asset before the first write.
    all_url_set = set(all_urls)
    for record in plan:
        target = ROOT / record["category"] / record["slug"] / "index.html"
        validate_generated_html(record, outputs[target], all_url_set)
    validate_listing(outputs[ROOT / "articles" / "index.html"], EXPECTED_TOTAL_ARTICLES)
    for category_file in category_files:
        category_url = f"/category/{category_file.parent.name}/"
        validate_listing(outputs[category_file], len(by_category[category_url]))
    if len(json.loads(outputs[SEARCH_PATH])) != EXPECTED_TOTAL_ARTICLES:
        fail("serialized search index validation failed")

    changed = [path for path, content in outputs.items() if not path.exists() or path.read_bytes() != content.encode("utf-8")]
    print(
        f"validated: base={EXPECTED_BASE_ARTICLES}, new={EXPECTED_NEW_ARTICLES}, "
        f"articles={EXPECTED_TOTAL_ARTICLES}, sitemap={EXPECTED_SITEMAP_URLS}, "
        f"files_to_update={len(changed)}"
    )
    if changed:
        print("changes: " + ", ".join(str(path.relative_to(ROOT)) for path in changed))
    if check_only:
        print("check-only: no files written")
        return

    written = sum(atomic_write(path, content) for path, content in outputs.items())
    print(f"written: {written} files")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        default=DEFAULT_PUBLISH_DATE,
        help=f"publication/last-modified date for the 77 new pages (default: {DEFAULT_PUBLISH_DATE})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate and render everything in memory without writing files",
    )
    arguments = parser.parse_args()
    build(parse_iso_date(arguments.date), check_only=arguments.check)


if __name__ == "__main__":
    main()
