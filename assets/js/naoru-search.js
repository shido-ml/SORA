(function () {
  "use strict";

  var form = document.querySelector(".trouble-search");
  var input = form && form.querySelector('input[name="q"]');
  var list = document.querySelector(".article-list");
  if (!form || !input || !list) return;

  var cards = Array.prototype.slice.call(list.querySelectorAll(".article-card"));
  var empty = document.createElement("p");
  empty.className = "search-empty";
  empty.hidden = true;
  empty.textContent = "一致する記事がありません。言葉を短くしてもう一度お試しください。";
  list.parentNode.insertBefore(empty, list.nextSibling);

  function normalize(value) {
    return value.toLocaleLowerCase("ja").replace(/[\s　]+/g, " ").trim();
  }

  function filter() {
    var query = normalize(input.value);
    var words = query ? query.split(" ") : [];
    var visible = 0;
    cards.forEach(function (card) {
      var text = normalize(card.textContent || "");
      var match = words.every(function (word) { return text.indexOf(word) !== -1; });
      card.hidden = !match;
      if (match) visible += 1;
    });
    empty.hidden = visible !== 0;
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var url = new URL(window.location.href);
    var value = input.value.trim();
    if (value) url.searchParams.set("q", value);
    else url.searchParams.delete("q");
    window.history.replaceState({}, "", url.pathname + url.search);
    filter();
  });
  input.addEventListener("input", filter);

  input.value = new URL(window.location.href).searchParams.get("q") || "";
  filter();
}());
