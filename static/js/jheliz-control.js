/* Jheliz Control — interacción: modales, ojo de contraseña, contador en vivo,
   utilidad automática, campana de notificaciones. */
(function () {
  "use strict";

  // ── Modales (fade + backdrop) ─────────────────────────────────────────
  function openModal(id) {
    var m = document.getElementById(id);
    if (m) { m.classList.add("is-open"); document.body.style.overflow = "hidden"; }
  }
  function closeModal(m) {
    m.classList.remove("is-open");
    document.body.style.overflow = "";
  }
  document.addEventListener("click", function (e) {
    var opener = e.target.closest("[data-jc-open]");
    if (opener) {
      e.preventDefault();
      openModal(opener.getAttribute("data-jc-open"));
      // Prefill: copiar data-fill-* a campos del modal con name correspondiente.
      var modal = document.getElementById(opener.getAttribute("data-jc-open"));
      if (modal) {
        Object.keys(opener.dataset).forEach(function (k) {
          if (k.indexOf("fill") === 0) {
            var field = k.replace(/^fill/, "");
            field = field.charAt(0).toLowerCase() + field.slice(1);
            var input = modal.querySelector('[name="' + field + '"]');
            if (input) { input.value = opener.dataset[k]; }
          }
        });
        // action override del form
        if (opener.dataset.action) {
          var form = modal.querySelector("form");
          if (form) { form.setAttribute("action", opener.dataset.action); }
        }
      }
      return;
    }
    if (e.target.closest("[data-jc-close]") || e.target.classList.contains("jc-modal__backdrop")) {
      var open = document.querySelector(".jc-modal.is-open");
      if (open) { closeModal(open); }
    }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      var open = document.querySelector(".jc-modal.is-open");
      if (open) { closeModal(open); }
    }
  });

  // ── Ojo de contraseña ─────────────────────────────────────────────────
  document.addEventListener("click", function (e) {
    var eye = e.target.closest(".jc-eye");
    if (!eye) { return; }
    var code = eye.parentNode.querySelector("code");
    var icon = eye.querySelector(".material-symbols-outlined");
    if (!code) { return; }
    if (code.dataset.shown === "1") {
      code.textContent = "••••••••";
      code.dataset.shown = "0";
      if (icon) { icon.textContent = "visibility"; }
    } else {
      code.textContent = code.dataset.value || "";
      code.dataset.shown = "1";
      if (icon) { icon.textContent = "visibility_off"; }
    }
  });

  // ── Contador en vivo (días/horas/minutos) ─────────────────────────────
  function fmtLeft(secs) {
    if (secs <= 0) { return "Vencida"; }
    var d = Math.floor(secs / 86400);
    var h = Math.floor((secs % 86400) / 3600);
    var m = Math.floor((secs % 3600) / 60);
    var out = [];
    if (d) { out.push(d + "d"); }
    if (h || d) { out.push(h + "h"); }
    out.push(m + "m");
    return out.join(" ");
  }
  function colorClass(secs) {
    if (secs <= 0) { return "jc-chip--expired"; }
    if (secs < 86400) { return "jc-chip--red"; }
    if (secs <= 3 * 86400) { return "jc-chip--yellow"; }
    return "jc-chip--green";
  }
  function tick() {
    var now = Date.now();
    document.querySelectorAll("[data-expires]").forEach(function (el) {
      var t = parseInt(el.getAttribute("data-expires"), 10) * 1000;
      var secs = Math.floor((t - now) / 1000);
      var label = el.querySelector(".jc-left-label");
      if (label) { label.textContent = fmtLeft(secs); }
      if (el.classList.contains("jc-chip")) {
        el.className = el.className.replace(/jc-chip--\w+/g, "").trim() + " " + colorClass(secs);
      }
    });
  }
  tick();
  setInterval(tick, 60000);

  // ── Utilidad automática (costo − inversión) ───────────────────────────
  function wireProfit(scope) {
    var cost = scope.querySelector('[name="cost"]');
    var inv = scope.querySelector('[name="investment"]');
    var out = scope.querySelector("[data-profit-out]");
    if (!cost || !inv || !out) { return; }
    var cur = (document.querySelector(".jc") || {}).dataset
      ? (document.querySelector(".jc").dataset.currency || "S/")
      : "S/";
    function calc() {
      var p = (parseFloat(cost.value) || 0) - (parseFloat(inv.value) || 0);
      out.textContent = "Utilidad: " + (p >= 0 ? "+" : "−") + cur + " " + Math.abs(p).toFixed(2);
      out.style.color = p >= 0 ? "" : "#991b1b";
    }
    cost.addEventListener("input", calc);
    inv.addEventListener("input", calc);
    calc();
  }
  document.querySelectorAll("form").forEach(wireProfit);

  // ── Campana de notificaciones ─────────────────────────────────────────
  var root = document.querySelector(".jc");
  var bell = document.getElementById("jcBell");
  var panel = document.getElementById("jcBellPanel");
  var countEl = document.getElementById("jcBellCount");
  function loadNotifs() {
    if (!root) { return; }
    var url = root.getAttribute("data-notif-url");
    fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (countEl) {
          if (data.count > 0) { countEl.textContent = data.count; countEl.hidden = false; }
          else { countEl.hidden = true; }
        }
        if (panel) {
          if (!data.alerts.length) {
            panel.innerHTML = '<div class="jc-bell__empty">Sin alertas de vencimiento 🎉</div>';
          } else {
            panel.innerHTML = data.alerts.map(function (a) {
              return '<a class="jc-bell__item" href="' + a.url + '">' +
                '<span class="jc-chip jc-chip--' + a.status + '"></span>' +
                '<span><strong>' + a.service + '</strong> · ' + a.client +
                '<br><small>' + a.time_left + '</small></span></a>';
            }).join("");
          }
        }
      })
      .catch(function () {});
  }
  if (bell && panel) {
    bell.addEventListener("click", function () { panel.hidden = !panel.hidden; });
    document.addEventListener("click", function (e) {
      if (!e.target.closest(".jc-topbar__actions")) { panel.hidden = true; }
    });
  }
  loadNotifs();
  setInterval(loadNotifs, 120000);
})();
