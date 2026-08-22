(function () {
  "use strict";

  var root = document.documentElement;
  var canonical = document.querySelector('link[rel="canonical"]');
  var canonicalPath = canonical ? new URL(canonical.href, window.location.origin).pathname : window.location.pathname;
  var articleSchema = Array.prototype.some.call(document.querySelectorAll('script[type="application/ld+json"]'), function (script) {
    return /["']@type["']\s*:\s*["']Article["']/.test(script.textContent || "");
  });
  var articleMarker = document.querySelector("article.article-body, article.article-main");
  var legacyArticlePath = /^\/articles\/[^/]+\.html$/.test(canonicalPath);
  var isArticle = articleSchema || legacyArticlePath || Boolean(articleMarker && canonicalPath !== "/");

  root.classList.add("sora-ui-v2");

  function brandMarkup() {
    return '<a aria-label="直るナビ トップページ" class="sora-v2-brand" href="/">' +
      '<span aria-hidden="true" class="sora-v2-brand-mark">✓</span>' +
      '<span><strong>直るナビ</strong><small>困ったを、安全な順番で解決。</small></span></a>';
  }

  function headerMarkup() {
    return '<div class="sora-v2-header-inner">' + brandMarkup() +
      '<button aria-controls="sora-v2-nav" aria-expanded="false" aria-label="メニューを開く" class="sora-v2-menu" type="button">☰</button>' +
      '<nav aria-label="メインナビゲーション" class="sora-v2-nav" id="sora-v2-nav">' +
      '<a href="/">トップ</a><a href="/categories/">カテゴリ</a><a href="/articles/">全400記事</a>' +
      '<a href="/articles.html">SNS・AI</a><a href="/about/">このサイトについて</a></nav></div>';
  }

  function footerMarkup() {
    return '<div class="sora-v2-footer-grid"><div>' + brandMarkup() +
      '<p>スマホ、PC、ブラウザ、Webサービスの不調を、危険の少ない確認から順番に切り分ける実用ガイドです。</p></div>' +
      '<nav aria-label="フッターのガイド"><strong>ガイド</strong><a href="/articles/">全400記事</a>' +
      '<a href="/categories/">カテゴリ一覧</a><a href="/iphone/">iPhone</a><a href="/articles.html">SNS・AI</a></nav>' +
      '<nav aria-label="運営情報"><strong>運営情報</strong><a href="/about/">このサイトについて</a>' +
      '<a href="/contact/">お問い合わせ</a><a href="/privacy/">プライバシー</a><a href="/disclaimer/">免責事項</a></nav></div>' +
      '<div class="sora-v2-footer-bottom">© 2026 直るナビ　重要な操作は各サービスの公式情報もご確認ください。</div>';
  }

  function normalizeChrome() {
    var header = document.querySelector(".site-header");
    var footer = document.querySelector(".site-footer");

    if (!header) {
      header = document.createElement("header");
      var skipLink = document.querySelector("body > a.skip-link, body > a[class*='skip'][href^='#']");
      if (skipLink) skipLink.insertAdjacentElement("afterend", header);
      else document.body.insertBefore(header, document.body.firstChild);
    }
    header.className = "site-header sora-v2-header";
    header.innerHTML = headerMarkup();

    if (!footer) {
      footer = document.createElement("footer");
      document.body.appendChild(footer);
    }
    footer.className = "site-footer sora-v2-footer";
    footer.innerHTML = footerMarkup();

    var menu = header.querySelector(".sora-v2-menu");
    var nav = header.querySelector(".sora-v2-nav");
    Array.prototype.forEach.call(nav.querySelectorAll("a"), function (link) {
      var linkPath = new URL(link.href, window.location.origin).pathname;
      if (linkPath === canonicalPath || (linkPath !== "/" && canonicalPath.indexOf(linkPath) === 0)) {
        link.setAttribute("aria-current", "page");
      }
    });
    menu.addEventListener("click", function () {
      var open = nav.classList.toggle("is-open");
      menu.setAttribute("aria-expanded", String(open));
      menu.setAttribute("aria-label", open ? "メニューを閉じる" : "メニューを開く");
      if (open) nav.querySelector("a").focus();
    });
    nav.addEventListener("click", function (event) {
      if (event.target.closest("a")) {
        nav.classList.remove("is-open");
        menu.setAttribute("aria-expanded", "false");
        menu.setAttribute("aria-label", "メニューを開く");
      }
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && nav.classList.contains("is-open")) {
        nav.classList.remove("is-open");
        menu.setAttribute("aria-expanded", "false");
        menu.setAttribute("aria-label", "メニューを開く");
        menu.focus();
      }
    });
    window.addEventListener("resize", function () {
      if (window.matchMedia("(min-width: 901px)").matches && nav.classList.contains("is-open")) {
        nav.classList.remove("is-open");
        menu.setAttribute("aria-expanded", "false");
        menu.setAttribute("aria-label", "メニューを開く");
      }
    });
  }

  function contentRoot() {
    return document.querySelector("article.article-body, article.article-main") ||
      Array.prototype.find.call(document.querySelectorAll(".wrap"), function (element) {
        return element.querySelector("h1") && element.querySelectorAll("h2").length;
      });
  }

  function ensureHeadingIds(container) {
    var used = {};
    Array.prototype.forEach.call(container.querySelectorAll("h2"), function (heading, index) {
      var base = heading.id || "section-" + (index + 1);
      var candidate = base;
      var suffix = 2;
      while (used[candidate] || (document.getElementById(candidate) && document.getElementById(candidate) !== heading)) {
        candidate = base + "-" + suffix;
        suffix += 1;
      }
      heading.id = candidate;
      used[candidate] = true;
    });
  }

  function addGuideMeta(container) {
    if (container.querySelector(".sora-guide-meta")) return;
    if (document.querySelector(".article-meta, .article-main > .meta, .meta-row")) return;
    var textLength = (container.textContent || "").replace(/\s+/g, "").length;
    var minutes = Math.max(3, Math.round(textLength / 520));
    var sections = container.querySelectorAll("h2").length;
    var meta = document.createElement("div");
    meta.className = "sora-guide-meta";
    meta.setAttribute("aria-label", "記事情報");
    meta.innerHTML = '<span>✓ 安全な順番</span><span>約' + minutes + '分</span>' +
      '<span>' + sections + '項目</span><span>スマホ対応</span>';
    var legacyHero = container.querySelector("header.hero");
    if (legacyHero) {
      var legacyInner = legacyHero.querySelector(".hero-inner") || legacyHero;
      var legacyAnchor = legacyInner.querySelector("nav.toc, .sora-toc, .callout");
      if (legacyAnchor) legacyInner.insertBefore(meta, legacyAnchor);
      else legacyInner.appendChild(meta);
      return;
    }
    var anchor = container.querySelector(".answer-box, .lead") || container.firstElementChild;
    if (anchor) anchor.parentNode.insertBefore(meta, anchor);
  }

  function addGuideVisual(container) {
    if (container.querySelector(".sora-guide-visual")) return;
    var figure = document.createElement("figure");
    var labelId = "sora-guide-visual-title";
    figure.className = "sora-guide-visual";
    figure.setAttribute("aria-labelledby", labelId);
    figure.innerHTML = '<svg class="sora-guide-visual-wide" role="img" viewBox="0 0 960 250" xmlns="http://www.w3.org/2000/svg">' +
      '<title id="' + labelId + '">トラブルを安全に切り分ける3段階</title>' +
      '<defs><linearGradient id="soraFlow" x1="0" x2="1"><stop stop-color="#1749d5"/><stop offset="1" stop-color="#08a8dc"/></linearGradient></defs>' +
      '<path d="M255 116h65M640 116h65" stroke="#9fb5d8" stroke-width="7" stroke-linecap="round"/>' +
      '<path d="M307 101l18 15-18 15M692 101l18 15-18 15" fill="none" stroke="#9fb5d8" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>' +
      '<g><rect x="18" y="25" width="235" height="182" rx="28" fill="#fff" stroke="#c8d7ed" stroke-width="2"/>' +
      '<circle cx="71" cy="78" r="30" fill="url(#soraFlow)"/><path d="M57 78l9 9 20-22" fill="none" stroke="#fff" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>' +
      '<text x="119" y="70" fill="#1749d5" font-size="20" font-weight="800">STEP 1</text><text x="119" y="101" fill="#10233f" font-size="25" font-weight="800">症状を確認</text>' +
      '<text x="43" y="157" fill="#60718a" font-size="18">どこで・何をすると</text><text x="43" y="183" fill="#60718a" font-size="18">起きるかを分ける</text></g>' +
      '<g><rect x="362" y="25" width="235" height="182" rx="28" fill="#fff" stroke="#9fb9ef" stroke-width="3"/>' +
      '<circle cx="415" cy="78" r="30" fill="url(#soraFlow)"/><path d="M403 78h24M415 66v24" stroke="#fff" stroke-width="7" stroke-linecap="round"/>' +
      '<text x="463" y="70" fill="#1749d5" font-size="20" font-weight="800">STEP 2</text><text x="463" y="101" fill="#10233f" font-size="25" font-weight="800">安全に試す</text>' +
      '<text x="387" y="157" fill="#60718a" font-size="18">データを消さない</text><text x="387" y="183" fill="#60718a" font-size="18">対処から進める</text></g>' +
      '<g><rect x="706" y="25" width="235" height="182" rx="28" fill="#fff" stroke="#c8d7ed" stroke-width="2"/>' +
      '<circle cx="759" cy="78" r="30" fill="#0c9b7b"/><path d="M746 79l9 9 19-23" fill="none" stroke="#fff" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>' +
      '<text x="807" y="70" fill="#0c8268" font-size="20" font-weight="800">STEP 3</text><text x="807" y="101" fill="#10233f" font-size="25" font-weight="800">結果で判断</text>' +
      '<text x="731" y="157" fill="#60718a" font-size="18">直らなければ原因を</text><text x="731" y="183" fill="#60718a" font-size="18">絞って相談する</text></g></svg>' +
      '<svg class="sora-guide-visual-mobile" role="img" viewBox="0 0 320 570" xmlns="http://www.w3.org/2000/svg">' +
      '<title>トラブルを安全に切り分ける3段階</title><defs><linearGradient id="soraFlowMobile" x1="0" x2="1"><stop stop-color="#1749d5"/><stop offset="1" stop-color="#08a8dc"/></linearGradient></defs>' +
      '<path d="M160 166v34M160 356v34" stroke="#9fb5d8" stroke-width="6" stroke-linecap="round"/><path d="M146 188l14 16 14-16M146 378l14 16 14-16" fill="none" stroke="#9fb5d8" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>' +
      '<g><rect x="12" y="10" width="296" height="156" rx="24" fill="#fff" stroke="#c8d7ed" stroke-width="2"/><circle cx="56" cy="55" r="25" fill="url(#soraFlowMobile)"/><path d="M45 55l8 8 17-19" fill="none" stroke="#fff" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/><text x="92" y="49" fill="#1749d5" font-size="16" font-weight="800">STEP 1</text><text x="92" y="75" fill="#10233f" font-size="23" font-weight="800">症状を確認</text><text x="35" y="119" fill="#60718a" font-size="16">どこで・何をすると起きるかを分ける</text></g>' +
      '<g><rect x="12" y="200" width="296" height="156" rx="24" fill="#fff" stroke="#9fb9ef" stroke-width="3"/><circle cx="56" cy="245" r="25" fill="url(#soraFlowMobile)"/><path d="M46 245h20M56 235v20" stroke="#fff" stroke-width="6" stroke-linecap="round"/><text x="92" y="239" fill="#1749d5" font-size="16" font-weight="800">STEP 2</text><text x="92" y="265" fill="#10233f" font-size="23" font-weight="800">安全に試す</text><text x="35" y="309" fill="#60718a" font-size="16">データを消さない対処から進める</text></g>' +
      '<g><rect x="12" y="390" width="296" height="156" rx="24" fill="#fff" stroke="#c8d7ed" stroke-width="2"/><circle cx="56" cy="435" r="25" fill="#0c9b7b"/><path d="M45 435l8 8 17-19" fill="none" stroke="#fff" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/><text x="92" y="429" fill="#0c8268" font-size="16" font-weight="800">STEP 3</text><text x="92" y="455" fill="#10233f" font-size="23" font-weight="800">結果で判断</text><text x="35" y="499" fill="#60718a" font-size="16">直らなければ原因を絞って相談する</text></g></svg>' +
      '<figcaption>初期化や削除を急がず、結果を確認しながら次の手順へ進みます。</figcaption>';
    var anchor = container.querySelector(".answer-box, .lead");
    var firstHeading = container.querySelector("h2");
    if (anchor) anchor.insertAdjacentElement("afterend", figure);
    else if (firstHeading) firstHeading.insertAdjacentElement("afterend", figure);
  }

  function addToc(container) {
    var headings = Array.prototype.slice.call(container.querySelectorAll("h2"));
    if (headings.length < 2) return;
    var nav = document.querySelector(".article-sidebar .side-card:first-child, .sidebar .toc, nav.toc");
    var created = false;
    if (!nav) {
      nav = document.createElement("nav");
      created = true;
      var visual = container.querySelector(".sora-guide-visual");
      if (visual) visual.insertAdjacentElement("afterend", nav);
      else container.insertBefore(nav, container.firstChild);
    }
    nav.classList.add("sora-toc");
    if (nav.tagName !== "NAV") nav.setAttribute("role", "navigation");
    nav.setAttribute("aria-label", "この記事の目次");
    if (created) {
      var title = document.createElement("p");
      var list = document.createElement("ol");
      title.className = "sora-toc-title";
      title.innerHTML = 'この記事の目次 <span aria-hidden="true">⌄</span>';
      headings.forEach(function (heading, index) {
        var item = document.createElement("li");
        var link = document.createElement("a");
        link.href = "#" + heading.id;
        link.textContent = (index + 1) + ". " + heading.textContent.trim();
        item.appendChild(link);
        list.appendChild(item);
      });
      nav.appendChild(title);
      nav.appendChild(list);
    }
    var legacyHero = nav.closest("header.hero");
    if (legacyHero && document.body.classList.contains("sora-legacy-card")) {
      legacyHero.insertAdjacentElement("afterend", nav);
    }
  }

  function wrapTables(container) {
    Array.prototype.forEach.call(container.querySelectorAll("table"), function (table) {
      if (table.parentElement && table.parentElement.classList.contains("sora-table-scroll")) return;
      var wrapper = document.createElement("div");
      wrapper.className = "sora-table-scroll";
      table.parentNode.insertBefore(wrapper, table);
      wrapper.appendChild(table);
    });
  }

  function addReadingTools(container) {
    var progress = document.createElement("div");
    var topButton = document.createElement("button");
    progress.className = "sora-reading-progress";
    progress.setAttribute("aria-hidden", "true");
    topButton.className = "sora-back-to-top";
    topButton.type = "button";
    topButton.setAttribute("aria-label", "ページ上部へ戻る");
    topButton.setAttribute("aria-hidden", "true");
    topButton.tabIndex = -1;
    topButton.textContent = "↑";
    document.body.appendChild(progress);
    document.body.appendChild(topButton);

    function update() {
      var max = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
      var visible = window.scrollY > 700;
      progress.style.width = Math.min(100, window.scrollY / max * 100) + "%";
      topButton.classList.toggle("is-visible", visible);
      topButton.setAttribute("aria-hidden", String(!visible));
      topButton.tabIndex = visible ? 0 : -1;
    }
    window.addEventListener("scroll", update, { passive: true });
    topButton.addEventListener("click", function () {
      var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      window.scrollTo({ top: 0, behavior: reducedMotion ? "auto" : "smooth" });
    });
    update();

    Array.prototype.forEach.call(container.querySelectorAll("img"), function (image) {
      if (!image.hasAttribute("loading")) image.loading = "lazy";
      image.decoding = "async";
    });
  }

  normalizeChrome();

  if (isArticle) {
    var container = contentRoot();
    document.body.classList.add("sora-article-page");
    if (!document.querySelector("article.article-body, article.article-main")) {
      document.body.classList.add("sora-legacy-card");
      if (window.getComputedStyle(root).getPropertyValue("--bg").trim().toLowerCase() === "#0b0f17") {
        document.body.classList.add("sora-legacy-dark");
      }
    }
    if (container) {
      ensureHeadingIds(container);
      addGuideMeta(container);
      addGuideVisual(container);
      addToc(container);
      wrapTables(container);
      addReadingTools(container);
    }
  }
}());
