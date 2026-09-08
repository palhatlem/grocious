(function () {
  "use strict";
  var form = document.getElementById("navigation-settings");
  if (!form) return;
  var data = JSON.parse(document.getElementById("navigation-data").textContent);
  var editor = document.getElementById("navigation-editor"), status = document.getElementById("navigation-status");
  var add = document.getElementById("navigation-add"), enabled = document.getElementById("navigation-enabled");
  function addRow(link) {
    var row = document.createElement("div"); row.className = "navigation-row";
    var label = document.createElement("input"); label.type = "text"; label.required = true; label.maxLength = 60;
    label.placeholder = "Visningsnavn"; label.setAttribute("aria-label", "Visningsnavn"); label.value = link.label || "";
    var url = document.createElement("input"); url.type = "url"; url.required = true; url.maxLength = 2000;
    url.placeholder = "https://…"; url.setAttribute("aria-label", "Nettadresse"); url.value = link.url || "";
    var remove = document.createElement("button"); remove.type = "button"; remove.className = "btn";
    remove.textContent = "×"; remove.setAttribute("aria-label", "Fjern lenke");
    remove.addEventListener("click", function () { row.remove(); add.disabled = false; });
    row.append(label, url, remove); editor.append(row); add.disabled = editor.children.length >= 20;
    return label;
  }
  data.links.forEach(addRow);
  add.addEventListener("click", function () { if (editor.children.length < 20) addRow({}).focus(); });
  form.addEventListener("submit", async function (event) {
    event.preventDefault(); status.textContent = "Lagrer …";
    var button = form.querySelector('button[type="submit"]'); button.disabled = true;
    var links = Array.from(editor.children).map(function (row) {
      var fields = row.querySelectorAll("input"); return {label: fields[0].value, url: fields[1].value};
    });
    try {
      var response = await fetch("/api/navigation", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({enabled: enabled.checked, links: links})});
      var saved = await response.json();
      if (!response.ok) throw new Error(saved.error || "Kunne ikke lagre lenkene.");
      var nav = document.getElementById("quick-links"); nav.replaceChildren();
      saved.links.forEach(function (link) {
        var a = document.createElement("a"); a.textContent = link.label; a.href = link.url;
        a.target = "_blank"; a.rel = "noopener noreferrer"; nav.append(a);
      });
      nav.hidden = !saved.enabled || !saved.links.length;
      status.textContent = "Lagret.";
    } catch (error) { status.textContent = error.message || "Kunne ikke lagre lenkene."; }
    finally { button.disabled = false; }
  });
}());
