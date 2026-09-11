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

  var otherRows = Array.prototype.slice.call(document.querySelectorAll("#other-receipt-list > .receipt"));
  var otherPage = 0, otherPrev = document.getElementById("other-prev"), otherNext = document.getElementById("other-next");
  function showOtherPage() {
    var visible = otherRows.filter(function (row) { return matchesExtra(row, "other-receipt-list"); });
    otherPage = Math.min(otherPage, Math.max(0, Math.ceil(visible.length / 20) - 1));
    otherRows.forEach(function (row) { row.hidden = true; });
    visible.slice(otherPage * 20, (otherPage + 1) * 20).forEach(function (row) { row.hidden = false; });
    if (!otherPrev || !otherNext) return;
    otherPrev.hidden = otherPage === 0;
    otherNext.hidden = (otherPage + 1) * 20 >= visible.length;
    otherPrev.parentElement.hidden = visible.length <= 20;
    document.getElementById("other-page").textContent = visible.length ?
      (otherPage * 20 + 1) + "–" + Math.min((otherPage + 1) * 20, visible.length) + " av " + visible.length : "Ingen treff";
    var count = document.getElementById("other-filter-count");
    if (count) count.textContent = visible.length + " kvitteringer";
  }
  if (otherPrev) otherPrev.addEventListener("click", function () { otherPage = Math.max(0, otherPage - 1); showOtherPage(); });
  if (otherNext) otherNext.addEventListener("click", function () { otherPage++; showOtherPage(); });
  var otherSort = document.getElementById("other-sort");
  function sortOther() {
    var parts = otherSort.value.split("-"), key = parts[0], direction = parts[1] === "asc" ? 1 : -1;
    otherRows.sort(function (a, b) {
      var x = a.dataset[key], y = b.dataset[key];
      if (!x !== !y) return !x ? 1 : -1;
      var cmp = !x ? 0 : key === "amount" ? Number(x) - Number(y) : x.localeCompare(y, "nb", {numeric: true, sensitivity: "base"});
      return cmp * direction || b.dataset.date.localeCompare(a.dataset.date);
    });
    otherRows.forEach(function (row) { document.getElementById("other-receipt-list").appendChild(row); });
    otherPage = 0;
    showOtherPage();
  }
  if (otherSort) { otherSort.addEventListener("change", sortOther); sortOther(); }
  else showOtherPage();

  // ---- filters ----------------------------------------------------------
  var nokFmt = new Intl.NumberFormat("nb-NO", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  function nok(x) { return nokFmt.format(x) + " kr"; }
  var chain = "", month = "", page = 0, pageSize = 50;
  var items = Array.prototype.slice.call(document.querySelectorAll("#list > .receipt"));
  items.sort(function (a, b) { return b.dataset.date.localeCompare(a.dataset.date); });
  var list = document.getElementById("list");
  items.forEach(function (li) { list.appendChild(li); });
  var prev = document.getElementById("receipts-prev"), next = document.getElementById("receipts-next");
  var pageEl = document.getElementById("receipt-page");
  var countEl = document.getElementById("count"), totalsEl = document.getElementById("totals"), emptyEl = document.getElementById("empty");
  function applyFilters() {
    var n = 0, sum = 0, bonus = 0, disc = 0;
    items.forEach(function (li) {
      var show = (!chain || li.dataset.chain === chain) && (!month || li.dataset.month === month) && matchesExtra(li, "list");
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
  document.querySelectorAll(".chips .chip[data-chain]").forEach(function (b) {
    b.addEventListener("click", function () {
      document.querySelectorAll(".chips .chip[data-chain]").forEach(function (x) { x.classList.remove("on"); });
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


  function todayOslo() {
    return new Intl.DateTimeFormat("sv-SE", {timeZone: "Europe/Oslo", year: "numeric", month: "2-digit", day: "2-digit"}).format(new Date());
  }
  function matchesExtra(row, id) {
    var controls = document.getElementById(id + "-filters");
    if (!controls) return true;
    var period = controls.dataset.period || "all", date = (row.dataset.date || "").slice(0, 10), today = todayOslo();
    var current = today.slice(0, 7), year = today.slice(0, 4);
    var previous = new Date(Date.UTC(Number(year), Number(today.slice(5, 7)) - 2, 1)).toISOString().slice(0, 7);
    var inPeriod = period === "all" || (period === "unknown" ? !date : !!date && (
      period === "current" ? date.slice(0, 7) === current && date <= today :
      period === "previous" ? date.slice(0, 7) === previous :
      period === "year" ? date.slice(0, 4) === year && date <= today :
      period.length === 4 ? date.slice(0, 4) === period : date.slice(0, 7) === period));
    var status = controls.querySelector("[data-registration-filter]").value;
    return inPeriod && (status === "all" || row.dataset.registration === status);
  }
  function refreshReceiptFilters() { page = 0; otherPage = 0; applyFilters(); showOtherPage(); }
  ["other-receipt-list", "list"].forEach(function (id) {
    var target = document.getElementById(id);
    if (!target) return;
    var controls = document.createElement("div"); controls.id = id + "-filters"; controls.className = "receipt-filter-controls";
    var periods = document.createElement("div"); periods.className = "period-buttons"; periods.setAttribute("aria-label", "Periode");
    [["current","Denne måneden"],["previous","Forrige måned"],["year","Hittil i år"],["all","Alle"]].forEach(function (pair) {
      var button = document.createElement("button"); button.type = "button"; button.className = "btn"; button.textContent = pair[1];
      button.dataset.periodValue = pair[0]; button.setAttribute("aria-pressed", pair[0] === "all" ? "true" : "false");
      button.onclick = function () { choose(pair[0]); }; periods.appendChild(button);
    });
    var select = document.createElement("select"); select.setAttribute("aria-label", "Velg måned eller år");
    function option(value, label) { var o = document.createElement("option"); o.value = value; o.textContent = label; select.appendChild(o); }
    option("all", "Velg måned / år"); option("unknown", "Ukjent dato");
    var dates = Array.from(target.querySelectorAll(".receipt")).map(function (row) { return (row.dataset.date || "").slice(0, 7); }).filter(Boolean);
    dates.push(todayOslo().slice(0, 7));
    Array.from(new Set(dates.map(function (d) { return d.slice(0, 4); }))).sort().reverse().forEach(function (y) { option(y, "Hele " + y); });
    Array.from(new Set(dates)).sort().reverse().forEach(function (d) {
      option(d, new Intl.DateTimeFormat("nb-NO", {month:"long", year:"numeric", timeZone:"UTC"}).format(new Date(d + "-01T00:00:00Z")));
    });
    function choose(value) {
      controls.dataset.period = value;
      select.value = Array.from(select.options).some(function (o) {return o.value === value;}) ? value : "all";
      periods.querySelectorAll("button").forEach(function (b) { b.setAttribute("aria-pressed", b.dataset.periodValue === value ? "true" : "false"); });
      refreshReceiptFilters();
    }
    select.onchange = function () { choose(select.value); };
    var registration = document.createElement("select"); registration.dataset.registrationFilter = "";
    registration.setAttribute("aria-label", "Registrering i Beancount");
    [["all","Alle registreringsstatuser"],["unregistered","Ikke registrert"],["registered","Registrert i Beancount"],["changed","Endret etter registrering"]].forEach(function (pair) {
      var o = document.createElement("option"); o.value = pair[0]; o.textContent = pair[1]; registration.appendChild(o);
    });
    registration.onchange = refreshReceiptFilters;
    controls.append(periods, select, registration);
    if (id === "other-receipt-list") { var count = document.createElement("span"); count.id = "other-filter-count"; count.className = "mut small"; controls.appendChild(count); }
    target.before(controls);
  });
  refreshReceiptFilters();
  var allRows = items.concat(otherRows);
  fetch("/api/bookkeeping").then(function (r) { if (!r.ok) throw new Error("Kunne ikke hente registreringsstatus"); return r.json(); }).then(function (records) {
    var mapping = new Map(records.map(function (r) { return [r.source + "/" + r.id, r]; }));
    allRows.forEach(function (row) {
      var record = mapping.get(row.dataset.source + "/" + row.dataset.id);
      var box = document.createElement("div"); box.className = "registration-controls";
      row.querySelector(".body").appendChild(box);
      if (!record) { row.dataset.registration = "unregistered"; box.textContent = "Bilaget må være i arkivet før det kan merkes registrert."; return; }
      var status = document.createElement("span"), reference = document.createElement("input"), button = document.createElement("button"), undo = document.createElement("button"), error = document.createElement("span");
      status.setAttribute("role", "status"); reference.placeholder = "Beancount-referanse (valgfri)"; reference.setAttribute("aria-label", "Beancount-referanse"); reference.maxLength = 500;
      button.type = undo.type = "button"; button.className = undo.className = "btn"; undo.textContent = "Angre registrering"; error.className = "err small";
      var badge = document.createElement("span"); badge.className = "registration-badge"; row.querySelector(".store").appendChild(badge);
      function update(value) {
        record = Object.assign(record, value); row.dataset.registration = record.state;
        badge.textContent = record.state === "registered" ? " · Registrert" : record.state === "changed" ? " · Endret etter registrering" : "";
        status.textContent = record.state === "unregistered" ? "Ikke registrert i Beancount" :
          (record.state === "changed" ? "Endret etter registrering" : "Registrert i Beancount") + " · " + new Date(record.registered_at).toLocaleDateString("nb-NO");
        reference.value = record.reference || ""; button.textContent = record.state === "changed" ? "Marker endringen som ført" : record.state === "registered" ? "Oppdater referanse" : "Registrert i Beancount";
        undo.hidden = record.state === "unregistered";
      }
      async function save(registered) {
        button.disabled = undo.disabled = true; error.textContent = "";
        try {
          var response = await fetch("/api/bookkeeping/" + record.source + "/" + record.archive_id, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({registered:registered, reference:reference.value})});
          var value = await response.json(); if (!response.ok) throw new Error(value.error || "Lagring feilet");
          update(value); refreshReceiptFilters();
        } catch (e) { error.textContent = e.message; }
        finally { button.disabled = undo.disabled = false; }
      }
      button.onclick = function () { save(true); }; undo.onclick = function () { save(false); };
      var hint = document.createElement("small"); hint.className = "mut"; hint.textContent = "Manuell huskelapp — ingen bankavstemming eller endring i eksporten.";
      box.append(status, reference, button, undo, hint, error); update(record);
    });
    refreshReceiptFilters();
  }).catch(function () {
    document.querySelectorAll(".receipt-filter-controls").forEach(function (controls) {
      var error = document.createElement("span"); error.className = "err small"; error.textContent = "Registreringsstatus kunne ikke lastes. Last siden på nytt."; controls.appendChild(error);
      controls.querySelector("[data-registration-filter]").disabled = true;
    });
  });

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
  function render(box, lines, currency) {
    function money(value) { return nokFmt.format(value) + " " + (currency === "NOK" ? "kr" : currency || ""); }
    if (!lines.length) { box.innerHTML = '<p class="mut small">Ingen varelinjer.</p>'; return; }
    var tot = 0, rows = lines.map(function (l) {
      tot += +l.amount || 0;
      return "<tr><td>" + esc(l.name) + (l.qty && l.qty !== 1 ? ' <span class="mut">× ' + esc(l.qty) + "</span>" : "") + "</td><td class=\"n\">" + money(+l.amount || 0) + "</td></tr>";
    });
    box.innerHTML = "<table>" + rows.join("") + '<tr class="sum"><td>Sum</td><td class="n">' + money(tot) + "</td></tr></table>";
  }
  items.concat(otherRows).forEach(function (li) {
    var head = li.querySelector(".head"), body = li.querySelector(".body"), box = li.querySelector(".lines");
    head.addEventListener("click", function () {
      var open = li.classList.toggle("open");
      body.hidden = !open; head.setAttribute("aria-expanded", open ? "true" : "false");
      var url = li.dataset.lines;
      if (open && url && !li.dataset.loaded) {
        li.dataset.loaded = "1";
        fetch(url).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
          .then(function (d) { render(box, d.lines || [], d.currency || li.dataset.currency || (li.dataset.chain ? "NOK" : "")); })
          .catch(function (e) { delete li.dataset.loaded; box.innerHTML = '<p class="err small">Kunne ikke hente varelinjer (' + esc(e.message) + ').</p>'; });
      }
    });
  });
})();
