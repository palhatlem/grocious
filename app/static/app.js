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

  // ---- filters ----------------------------------------------------------
  var nokFmt = new Intl.NumberFormat("nb-NO", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  function nok(x) { return nokFmt.format(x) + " kr"; }
  var chain = "", month = "";
  var items = Array.prototype.slice.call(document.querySelectorAll(".receipt"));
  var countEl = document.getElementById("count"), totalsEl = document.getElementById("totals"), emptyEl = document.getElementById("empty");
  function applyFilters() {
    var n = 0, sum = 0, bonus = 0, disc = 0;
    items.forEach(function (li) {
      var show = (!chain || li.dataset.chain === chain) && (!month || li.dataset.month === month);
      li.hidden = !show;
      if (show) { n++; sum += +li.dataset.amount || 0; bonus += +li.dataset.bonus || 0; disc += +li.dataset.discount || 0; }
    });
    if (countEl) countEl.textContent = n + " kvitteringer";
    if (totalsEl) totalsEl.textContent = n ? "Sum " + nok(sum) + (bonus ? " · bonus " + nok(bonus) : "") + (disc ? " · rabatt " + nok(disc) : "") : "";
    if (emptyEl) emptyEl.hidden = n > 0;
  }
  document.querySelectorAll(".chips .chip").forEach(function (b) {
    b.addEventListener("click", function () {
      document.querySelectorAll(".chips .chip").forEach(function (x) { x.classList.remove("on"); });
      b.classList.add("on"); chain = b.dataset.chain || ""; applyFilters();
    });
  });
  var monthSel = document.getElementById("month");
  if (monthSel) monthSel.addEventListener("change", function () { month = monthSel.value; applyFilters(); });
  applyFilters();

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
