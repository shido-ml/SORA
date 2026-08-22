(function () {
  "use strict";

  // Ninja AdMax is enabled while AdSense auto ads are paused.
  // Change only this flag to false to stop every Ninja AdMax placement.
  var NINJA_ADMAX_ENABLED = true;

  if (!NINJA_ADMAX_ENABLED) {
    document.querySelectorAll(".sora-ad-slot").forEach(function (slot) {
      slot.remove();
    });
    return;
  }

  var MOBILE_STICKY = "https://adm.shinobi.jp/s/d044499f6d5b29a4f32ef05cb49e97fc";
  var PC_AD = "https://adm.shinobi.jp/s/f02de23bd9ffa66bc8b94ee3eef2c5c6";
  var INLINE_SDK = "https://adm.shinobi.jp/st/t.js";
  var INLINE_ID = "23a16b749b5224c46c26784399bdfcad";
  var mobilePattern = /Android|iPhone|iPad|iPod|IEMobile|Opera Mini|Mobile|BlackBerry|webOS/i;
  var isMobile = window.matchMedia("(max-width: 767px)").matches || mobilePattern.test(navigator.userAgent);

  function writeScript(source, attributes) {
    var attrs = attributes || "";
    document.write('<script src="' + source + '" ' + attrs + '><\/script>');
  }

  function directArticleChild(article, element) {
    var block = element;

    while (block.parentElement && block.parentElement !== article) {
      block = block.parentElement;
    }

    return block;
  }

  function addMidArticleSlot(originalSlot) {
    var article = originalSlot.closest("article") || originalSlot.parentElement;
    var headings;
    var target;
    var addedSlot;

    if (!article) {
      return;
    }

    headings = article.querySelectorAll("h2");
    if (headings.length < 3) {
      return;
    }

    target = directArticleChild(article, headings[Math.floor(headings.length / 2)]);
    if (!target || target === originalSlot || !target.parentNode) {
      return;
    }

    addedSlot = originalSlot.cloneNode(true);
    addedSlot.classList.add("sora-injected-inline-ad");
    addedSlot.setAttribute("data-ad-placement", "article-middle");
    target.parentNode.insertBefore(addedSlot, target);
  }

  function movePcStickyToSide() {
    var attempts = 0;
    var timer = window.setInterval(function () {
      var wrapper = document.querySelector("[data-admax-sticky-wrapper]");
      var stickyAd;

      attempts += 1;

      if (wrapper) {
        stickyAd = Array.prototype.find.call(wrapper.children, function (element) {
          return window.getComputedStyle(element).position === "fixed";
        });
      }

      if (stickyAd) {
        stickyAd.classList.add("sora-pc-admax-side");
        stickyAd.style.left = "auto";
        stickyAd.style.right = "16px";
        stickyAd.style.bottom = "16px";
        stickyAd.style.transform = "none";
        window.clearInterval(timer);
      } else if (attempts >= 40) {
        window.clearInterval(timer);
      }
    }, 100);
  }

  var originalInlineSlot = document.querySelector(".sora-mobile-inline-ad");

  // Run ads only on pages that already contain an approved placement marker.
  if (!originalInlineSlot) {
    return;
  }

  if (isMobile) {
    addMidArticleSlot(originalInlineSlot);
    document.body.classList.add("sora-admax-mobile-sticky-active");
    writeScript(MOBILE_STICKY);

    var inlineSlots = document.querySelectorAll(".sora-mobile-inline-ad");
    window.admaxads = (window.admaxads || []).filter(function (item) {
      return item.admax_id !== INLINE_ID;
    });

    inlineSlots.forEach(function () {
      window.admaxads.push({ admax_id: INLINE_ID, type: "banner" });
    });

    window.__admax_tag__ = undefined;
    writeScript(INLINE_SDK, "async");
  } else {
    document.querySelectorAll(".sora-mobile-inline-ad").forEach(function (slot) {
      slot.remove();
    });

    // Keep the 300px side unit outside the 1180px content canvas.
    if (!window.matchMedia("(min-width: 1900px)").matches) {
      return;
    }

    document.body.classList.add("sora-admax-pc-side-active");
    writeScript(PC_AD);
    movePcStickyToSide();
  }
})();
