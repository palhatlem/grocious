/* grocious — theme picker, receipt filters, expandable line items. No framework, no CDN. */
(function () {
  "use strict";
  var root = document.documentElement;
  var KEY = "grocious.theme";

  // ---- theme ------------------------------------------------------------
  var sel = document.getElementById("theme");
  function applyTheme(id) {
    if (!id || id === "auto") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", id);
    try { localStorage.setItem(KEY, id || "auto"); } catch (e) {}
    if (sel) sel.value = id || "auto";
  }
  if (sel) {
    var saved = null;
    try { saved = localStorage.getItem(KEY); } catch (e) {}
    var fromUrl = /[?&]theme=([\w-]+)/.exec(location.search);
    if (fromUrl) applyTheme(fromUrl[1]); else sel.value = saved || "auto";
    sel.addEventListener("change", function () { applyTheme(sel.value); });
  }

  var settings = document.querySelector(".settings-menu");
  if (settings) {
    document.addEventListener("click", function (e) { if (!settings.contains(e.target)) settings.open = false; });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && settings.open) { settings.open = false; settings.querySelector("summary").focus(); }
    });
  }

  // ---- filters ----------------------------------------------------------
  var nokFmt = new Intl.NumberFormat("nb-NO", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  function nok(x) { return nokFmt.format(x) + " kr"; }
  var chain = "", month = "", page = 0, pageSize = 50;
  var items = Array.prototype.slice.call(document.querySelectorAll(".receipt"));
  items.sort(function (a, b) { return b.dataset.date.localeCompare(a.dataset.date); });
  var list = document.getElementById("list");
  items.forEach(function (li) { list.appendChild(li); });
  var prev = document.getElementById("receipts-prev"), next = document.getElementById("receipts-next");
  var pageEl = document.getElementById("receipt-page");
  var countEl = document.getElementById("count"), totalsEl = document.getElementById("totals"), emptyEl = document.getElementById("empty");
  function applyFilters() {
    var n = 0, sum = 0, bonus = 0, disc = 0;
    items.forEach(function (li) {
      var show = (!chain || li.dataset.chain === chain) && (!month || li.dataset.month === month);
      li.hidden = !show || n < page * pageSize || n >= (page + 1) * pageSize;
      if (show) { n++; sum += +li.dataset.amount || 0; bonus += +li.dataset.bonus || 0; disc += +li.dataset.discount || 0; }
    });
    if (prev) prev.hidden = page === 0;
    if (next) next.hidden = (page + 1) * pageSize >= n;
    if (pageEl) pageEl.textContent = n ? "Viser " + (page * pageSize + 1) + "–" + Math.min((page + 1) * pageSize, n) + " av " + n : "";
    if (countEl) countEl.textContent = n + " kvitteringer";
    if (totalsEl) totalsEl.textContent = n ? "Sum " + nok(sum) + (bonus ? " · bonus " + nok(bonus) : "") + (disc ? " · rabatt " + nok(disc) : "") : "";
    if (emptyEl) emptyEl.hidden = n > 0;
  }
  document.querySelectorAll(".chips .chip").forEach(function (b) {
    b.addEventListener("click", function () {
      document.querySelectorAll(".chips .chip").forEach(function (x) { x.classList.remove("on"); });
      b.classList.add("on"); chain = b.dataset.chain || ""; page = 0; applyFilters();
    });
  });
  var sortSel = document.getElementById("receipt-sort");
  if (sortSel) sortSel.addEventListener("change", function () {
    var parts = sortSel.value.split("-"), key = parts[0], direction = parts[1] === "asc" ? 1 : -1;
    items.sort(function (a, b) {
      var x = a.dataset[key], y = b.dataset[key], cmp;
      var absentX = x == null || x === "", absentY = y == null || y === "";
      if (absentX !== absentY) return absentX ? 1 : -1;
      if (absentX) cmp = 0;
      else if (key === "store") cmp = x.localeCompare(y, "nb", {sensitivity: "base", numeric: true});
      else if (key === "date") cmp = x.localeCompare(y);
      else cmp = Number(x) - Number(y);
      return cmp * direction || b.dataset.date.localeCompare(a.dataset.date);
    });
    items.forEach(function (li) { list.appendChild(li); });
    page = 0; applyFilters();
  });
  var monthSel = document.getElementById("month");
  if (monthSel) monthSel.addEventListener("change", function () { month = monthSel.value; page = 0; applyFilters(); });
  if (prev) prev.addEventListener("click", function () { page--; applyFilters(); document.getElementById("receipts").scrollIntoView(); });
  if (next) next.addEventListener("click", function () { page++; applyFilters(); document.getElementById("receipts").scrollIntoView(); });
  applyFilters();

  var hiddenOffers = [], offerKey = "grocious.hiddenOffers";
  try { var stored = JSON.parse(localStorage.getItem(offerKey) || "[]"); if (Array.isArray(stored)) hiddenOffers = stored; } catch (e) {}
  var offers = Array.prototype.slice.call(document.querySelectorAll("[data-offer-id]"));
  var resetOffers = document.getElementById("offers-reset");
  function showOffers() {
    var visible = 0;
    offers.forEach(function (card) { card.hidden = hiddenOffers.indexOf(card.dataset.offerId) !== -1; if (!card.hidden) visible++; });
    var empty = document.getElementById("offers-empty");
    if (empty) empty.hidden = visible > 0;
    if (resetOffers) resetOffers.hidden = !hiddenOffers.length;
  }
  offers.forEach(function (card) {
    card.querySelector(".offer-dismiss").addEventListener("click", function () {
      if (hiddenOffers.indexOf(card.dataset.offerId) === -1) hiddenOffers.push(card.dataset.offerId);
      try { localStorage.setItem(offerKey, JSON.stringify(hiddenOffers)); } catch (e) {}
      showOffers();
    });
  });
  if (resetOffers) resetOffers.addEventListener("click", function () {
    hiddenOffers = []; try { localStorage.removeItem(offerKey); } catch (e) {} showOffers();
  });
  showOffers();

  // ---- expandable line items -------------------------------------------
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function render(box, lines) {
    if (!lines.length) { box.innerHTML = '<p class="mut small">Ingen varelinjer.</p>'; return; }
    var tot = 0, rows = lines.map(function (l) {
      tot += +l.amount || 0;
      return "<tr><td>" + esc(l.name) + (l.qty && l.qty !== 1 ? ' <span class="mut">× ' + esc(l.qty) + "</span>" : "") + "</td><td class=\"n\">" + nok(+l.amount || 0) + "</td></tr>";
    });
    box.innerHTML = "<table>" + rows.join("") + '<tr class="sum"><td>Sum</td><td class="n">' + nok(tot) + "</td></tr></table>";
  }
  items.forEach(function (li) {
    var head = li.querySelector(".head"), body = li.querySelector(".body"), box = li.querySelector(".lines");
    head.addEventListener("click", function () {
      var open = li.classList.toggle("open");
      body.hidden = !open; head.setAttribute("aria-expanded", open ? "true" : "false");
      var url = li.dataset.lines;
      if (open && url && !li.dataset.loaded) {
        li.dataset.loaded = "1";
        fetch(url).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
          .then(function (d) { render(box, d.lines || []); })
          .catch(function (e) { box.innerHTML = '<p class="err small">Kunne ikke hente varelinjer (' + esc(e.message) + ').</p>'; });
      }
    });
  });
})();
