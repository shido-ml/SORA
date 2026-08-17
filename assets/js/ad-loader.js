(function () {
  "use strict";

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

  var inlineSlots = document.querySelectorAll(".sora-mobile-inline-ad");

  if (isMobile) {
    writeScript(MOBILE_STICKY);

    if (inlineSlots.length) {
      window.admaxads = (window.admaxads || []).filter(function (item) {
        return item.admax_id !== INLINE_ID;
      });
      window.admaxads.push({ admax_id: INLINE_ID, type: "banner" });
      window.__admax_tag__ = undefined;
      writeScript(INLINE_SDK, "async");
    }
  } else {
    inlineSlots.forEach(function (slot) {
      slot.hidden = true;
      slot.setAttribute("aria-hidden", "true");
    });
    writeScript(PC_AD);
  }
})();
