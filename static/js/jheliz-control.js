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

  // ── "Ver todas" — desplegar suscripciones extra de un cliente ─────────
  document.addEventListener("click", function (e) {
    var more = e.target.closest("[data-jc-more]");
    if (!more) { return; }
    var list = more.previousElementSibling;
    while (list && !list.classList.contains("jc-csubs")) { list = list.previousElementSibling; }
    if (!list) { return; }
    var open = list.classList.toggle("is-open");
    var label = more.lastChild;
    var total = list.querySelectorAll(".jc-csub2").length;
    if (label) { label.textContent = open ? " Ver menos" : " Ver todas (" + total + ")"; }
    var icon = more.querySelector(".material-symbols-outlined");
    if (icon) { icon.textContent = open ? "expand_less" : "expand_more"; }
  });

  // ── "Ver" cuenta: revela correo + contraseña ──────────────────────────
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-jc-ver]");
    if (!btn) { return; }
    var box = btn.parentNode.querySelector("[data-jc-acctbox]");
    if (!box) { return; }
    var icon = btn.querySelector(".material-symbols-outlined");
    var lbl = btn.querySelector("[data-jc-verlbl]");
    var hidden = box.hasAttribute("hidden");
    if (hidden) {
      box.removeAttribute("hidden");
      btn.classList.add("is-open");
      if (icon) { icon.textContent = "visibility_off"; }
      if (lbl) { lbl.textContent = "Ocultar"; }
    } else {
      box.setAttribute("hidden", "");
      btn.classList.remove("is-open");
      if (icon) { icon.textContent = "visibility"; }
      if (lbl) { lbl.textContent = "Ver"; }
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
      code.textContent = code.dataset.label || "••••••••";
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

  // ── Botones de perfiles (1–7 / cuenta completa) ───────────────────────
  document.querySelectorAll("[data-jc-pchips]").forEach(function (box) {
    var form = box.closest("form");
    if (!form) { return; }
    var planEl = form.querySelector("[data-jc-plan]");
    var profEl = form.querySelector("[data-jc-profiles]");
    box.addEventListener("click", function (e) {
      var chip = e.target.closest("[data-jc-profile]");
      if (!chip) { return; }
      box.querySelectorAll(".jc-pchip").forEach(function (c) { c.classList.remove("is-active"); });
      chip.classList.add("is-active");
      var val = chip.getAttribute("data-jc-profile");
      if (val === "full") {
        if (planEl) { planEl.value = "completa"; }
        if (profEl) { profEl.value = "1"; }
      } else {
        if (planEl) { planEl.value = "perfil"; }
        if (profEl) { profEl.value = val; }
      }
    });
  });

  // ── Tiempo del servicio: por días o por fecha de vencimiento ──────────
  document.querySelectorAll("[data-jc-timemode]").forEach(function (box) {
    var field = box.closest(".jc-field");
    if (!field) { return; }
    var panes = field.querySelectorAll("[data-jc-tmpane]");
    var helps = field.querySelectorAll("[data-jc-tmhelp]");
    function setMode(mode) {
      box.querySelectorAll("[data-jc-tmode]").forEach(function (b) {
        b.classList.toggle("is-active", b.getAttribute("data-jc-tmode") === mode);
      });
      panes.forEach(function (pane) {
        var on = pane.getAttribute("data-jc-tmpane") === mode;
        pane.hidden = !on;
        // El input oculto se deshabilita para que no se envíe (evita que una
        // fecha cargada pise los días, o viceversa).
        pane.querySelectorAll("input").forEach(function (i) { i.disabled = !on; });
      });
      helps.forEach(function (help) {
        help.hidden = help.getAttribute("data-jc-tmhelp") !== mode;
      });
    }
    box.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-jc-tmode]");
      if (!btn) { return; }
      setMode(btn.getAttribute("data-jc-tmode"));
    });
    setMode("days");
  });

  // ── Selección rápida de cliente (buscar / elegir / crear nuevo) ───────
  document.querySelectorAll("[data-jc-subform]").forEach(function (form) {
    var search = form.querySelector("[data-jc-csearch]");
    var list = form.querySelector("[data-jc-clist]");
    var hidden = form.querySelector("[data-jc-client]");
    var nameI = form.querySelector("[data-jc-cname]");
    var waI = form.querySelector("[data-jc-cwa]");
    var tgI = form.querySelector("[data-jc-ctg]");
    if (search && list) {
      search.addEventListener("input", function () {
        var q = search.value.trim().toLowerCase();
        list.querySelectorAll("[data-jc-cpick]").forEach(function (item) {
          var hay = (item.getAttribute("data-search") || "").toLowerCase();
          item.style.display = (!q || hay.indexOf(q) !== -1) ? "" : "none";
        });
      });
    }
    if (list) {
      list.addEventListener("click", function (e) {
        var item = e.target.closest("[data-jc-cpick]");
        if (!item) { return; }
        list.querySelectorAll("[data-jc-cpick]").forEach(function (c) { c.classList.remove("is-active"); });
        item.classList.add("is-active");
        if (hidden) { hidden.value = item.getAttribute("data-id") || ""; }
        if (nameI) { nameI.value = item.getAttribute("data-name") || ""; }
        if (waI) { waI.value = item.getAttribute("data-wa") || ""; }
        if (tgI) { tgI.value = item.getAttribute("data-tg") || ""; }
      });
    }
    // Si el usuario edita el nombre a mano, dejamos de usar el cliente elegido
    // (se creará uno nuevo con lo que escriba).
    if (nameI) {
      nameI.addEventListener("input", function () {
        if (hidden) { hidden.value = ""; }
        if (list) { list.querySelectorAll("[data-jc-cpick]").forEach(function (c) { c.classList.remove("is-active"); }); }
      });
    }
  });

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

  // ── Buscador instantáneo en "Mis clientes" ───────────────────────────
  var cliSearch = document.querySelector(".jc-clients-search");
  if (cliSearch) {
    var cards = Array.prototype.slice.call(document.querySelectorAll(".jc-client"));
    var noMatch = document.getElementById("jcClientsNoMatch");
    // Búsqueda instantánea en el cliente: no recargar la página.
    var form = cliSearch.closest("form");
    if (form) { form.addEventListener("submit", function (e) { e.preventDefault(); }); }
    function norm(s) { return (s || "").toString().toLowerCase().trim(); }
    function filterClients() {
      var term = norm(cliSearch.value);
      var shown = 0;
      cards.forEach(function (card) {
        var hay = norm(card.getAttribute("data-search"));
        var match = !term || hay.indexOf(term) !== -1;
        card.hidden = !match;
        if (match) { shown += 1; }
      });
      if (noMatch) { noMatch.hidden = !(term && shown === 0); }
    }
    cliSearch.addEventListener("input", filterClients);
    filterClients();
  }

  // ── Buscador instantáneo de suscripciones (detalle de servicio) ───────
  var subSearch = document.querySelector(".jc-subs-search");
  if (subSearch) {
    var rows = Array.prototype.slice.call(
      document.querySelectorAll(".jc-table--subs tbody tr")
    );
    var subNoMatch = document.querySelector(".jc-subs-nomatch");
    function nrm(s) { return (s || "").toString().toLowerCase().trim(); }
    function filterSubs() {
      var term = nrm(subSearch.value);
      var shown = 0;
      rows.forEach(function (row) {
        var hay = nrm(row.getAttribute("data-search"));
        var match = !term || hay.indexOf(term) !== -1;
        row.hidden = !match;
        if (match) { shown += 1; }
      });
      if (subNoMatch) { subNoMatch.hidden = !(term && shown === 0); }
    }
    subSearch.addEventListener("input", filterSubs);
    filterSubs();
  }
})();
