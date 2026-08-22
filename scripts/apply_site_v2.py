"""Attach the shared SORA v2 interface and stable shell to every HTML page."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
STYLE = '<link href="/assets/css/site-v2.css?v=20260823" rel="stylesheet"/>'
SCRIPT = '<script defer src="/assets/js/site-v2.js?v=20260823"></script>'
FAVICON = '<link href="/assets/img/favicon.svg" rel="icon" type="image/svg+xml"/>'
AD_SCRIPT = '<script src="/assets/js/ad-loader.js?v=20260823"></script>'
SKIP = {ROOT / "googlec674e3cbc3834198.html"}
HEADER = (
    '<header class="site-header sora-v2-header"><div class="sora-v2-header-inner">'
    '<a aria-label="直るナビ トップページ" class="sora-v2-brand" href="/">'
    '<span aria-hidden="true" class="sora-v2-brand-mark">✓</span>'
    '<span><strong>直るナビ</strong><small>困ったを、安全な順番で解決。</small></span></a>'
    '<button aria-controls="sora-v2-nav" aria-expanded="false" aria-label="メニューを開く" '
    'class="sora-v2-menu" type="button">☰</button>'
    '<nav aria-label="メインナビゲーション" class="sora-v2-nav" id="sora-v2-nav">'
    '<a href="/">トップ</a><a href="/categories/">カテゴリ</a><a href="/articles/">全400記事</a>'
    '<a href="/articles.html">SNS・AI</a><a href="/about/">このサイトについて</a>'
    '</nav></div></header>'
)
FOOTER = (
    '<footer class="site-footer sora-v2-footer"><div class="sora-v2-footer-grid"><div>'
    '<a aria-label="直るナビ トップページ" class="sora-v2-brand" href="/">'
    '<span aria-hidden="true" class="sora-v2-brand-mark">✓</span>'
    '<span><strong>直るナビ</strong><small>困ったを、安全な順番で解決。</small></span></a>'
    '<p>スマホ、PC、ブラウザ、Webサービスの不調を、危険の少ない確認から順番に切り分ける実用ガイドです。</p>'
    '</div><nav aria-label="フッターのガイド"><strong>ガイド</strong><a href="/articles/">全400記事</a>'
    '<a href="/categories/">カテゴリ一覧</a><a href="/iphone/">iPhone</a><a href="/articles.html">SNS・AI</a>'
    '</nav><nav aria-label="運営情報"><strong>運営情報</strong><a href="/about/">このサイトについて</a>'
    '<a href="/contact/">お問い合わせ</a><a href="/privacy/">プライバシー</a>'
    '<a href="/disclaimer/">免責事項</a></nav></div>'
    '<div class="sora-v2-footer-bottom">© 2026 直るナビ　重要な操作は各サービスの公式情報もご確認ください。</div></footer>'
)
HEADER_RE = re.compile(
    r'<header\b(?=[^>]*\bclass=["\'][^"\']*\bsite-header\b[^"\']*["\'])[^>]*>.*?</header>',
    re.IGNORECASE | re.DOTALL,
)
FOOTER_RE = re.compile(
    r'<footer\b(?=[^>]*\bclass=["\'][^"\']*\bsite-footer\b[^"\']*["\'])[^>]*>.*?</footer>',
    re.IGNORECASE | re.DOTALL,
)


def add_class_to_tag(html: str, tag: str, class_name: str) -> str:
    pattern = re.compile(rf"<{tag}\b([^>]*)>", re.IGNORECASE)
    match = pattern.search(html)
    if not match:
        raise ValueError(f"Missing <{tag}>")
    attributes = match.group(1)
    class_match = re.search(r'class=(["\'])(.*?)\1', attributes, re.IGNORECASE | re.DOTALL)
    if class_match:
        classes = class_match.group(2).split()
        if class_name in classes:
            return html
        replacement = class_match.group(0).replace(class_match.group(2), class_match.group(2) + " " + class_name)
        updated_attributes = attributes[: class_match.start()] + replacement + attributes[class_match.end() :]
    else:
        updated_attributes = f' class="{class_name}"' + attributes
    return html[: match.start()] + f"<{tag}{updated_attributes}>" + html[match.end() :]


def inject_header(html: str) -> str:
    if HEADER_RE.search(html):
        return HEADER_RE.sub(HEADER, html, count=1)
    body_match = re.search(r"<body\b[^>]*>", html, re.IGNORECASE)
    if not body_match:
        raise ValueError("Missing <body>")
    insertion = body_match.end()
    tail = html[insertion:]
    skip_match = re.match(
        r'(\s*<a\b(?=[^>]*\bclass=["\'][^"\']*\bskip(?:-link)?\b[^"\']*["\'])[^>]*>.*?</a>)',
        tail,
        re.IGNORECASE | re.DOTALL,
    )
    if skip_match:
        insertion += skip_match.end()
    return html[:insertion] + HEADER + html[insertion:]


def inject_footer(html: str) -> str:
    if FOOTER_RE.search(html):
        return FOOTER_RE.sub(FOOTER, html, count=1)
    if "</body>" not in html:
        raise ValueError("Missing </body>")
    return html.replace("</body>", FOOTER + "</body>", 1)


def update_page(path: Path) -> bool:
    html = path.read_text(encoding="utf-8")
    updated = html

    updated = re.sub(
        r'<link\s+href="/assets/css/site-v2\.css(?:\?[^" ]*)?"\s+rel="stylesheet"\s*/?>',
        STYLE,
        updated,
        flags=re.IGNORECASE,
    )
    updated = re.sub(
        r'<script\b[^>]*\bsrc="/assets/js/site-v2\.js(?:\?[^" ]*)?"[^>]*></script>',
        SCRIPT,
        updated,
        flags=re.IGNORECASE,
    )
    updated = re.sub(
        r'<script\s+src="/assets/js/ad-loader\.js(?:\?[^" ]*)?"></script>',
        AD_SCRIPT,
        updated,
        flags=re.IGNORECASE,
    )

    updated = add_class_to_tag(updated, "html", "sora-ui-v2")
    is_article = (
        "article-body" in updated
        or "article-main" in updated
        or (path.parent == ROOT / "articles" and path.name != "index.html")
    )
    if is_article:
        updated = add_class_to_tag(updated, "body", "sora-article-page")
    if is_article and "article-body" not in updated and "article-main" not in updated:
        updated = add_class_to_tag(updated, "body", "sora-legacy-card")
        if "--bg:#0b0f17" in updated.replace(" ", ""):
            updated = add_class_to_tag(updated, "body", "sora-legacy-dark")

    updated = inject_header(updated)
    updated = inject_footer(updated)

    if STYLE not in updated:
        if "</head>" not in updated:
            raise ValueError(f"Missing </head>: {path.relative_to(ROOT)}")
        updated = updated.replace("</head>", f"{STYLE}</head>", 1)

    if FAVICON not in updated and "rel=\"icon\"" not in updated and "rel='icon'" not in updated:
        updated = updated.replace("</head>", f"{FAVICON}</head>", 1)

    if SCRIPT not in updated:
        if "</body>" not in updated:
            raise ValueError(f"Missing </body>: {path.relative_to(ROOT)}")
        updated = updated.replace("</body>", f"{SCRIPT}</body>", 1)

    if updated == html:
        return False

    path.write_text(updated, encoding="utf-8", newline="")
    return True


def main() -> None:
    changed = 0
    for path in sorted(ROOT.rglob("*.html")):
        if path in SKIP or ".git" in path.parts:
            continue
        changed += update_page(path)
    print(f"Attached SORA v2 assets to {changed} HTML files")


if __name__ == "__main__":
    main()
