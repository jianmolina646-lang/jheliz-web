/* Jheliz Control — interacción: modales, ojo de contraseña, contador en vivo,
   utilidad automática, campana de notificaciones. */
(function () {
  "use strict";

  var app = document.querySelector(".jc-app");
  var menuToggle = document.getElementById("jcMenuToggle");
  var lastModalTrigger = null;
  var lastNavFocus = null;

  // Navegación responsive: drawer predecible, cerrable con overlay o Escape.
  function setNav(open) {
    if (!app || !menuToggle) { return; }
    var workspace = app.querySelector(".jc-workspace");
    var drawer = app.querySelector(".jc-sidebar");
    app.classList.toggle("is-nav-open", open);
    menuToggle.setAttribute("aria-expanded", open ? "true" : "false");
    menuToggle.setAttribute("aria-label", open ? "Cerrar navegación" : "Abrir navegación");
    document.body.style.overflow = open ? "hidden" : "";
    if (drawer && window.matchMedia("(max-width: 1023px)").matches) {
      drawer.setAttribute("role", "dialog");
      drawer.setAttribute("aria-modal", open ? "true" : "false");
      drawer.setAttribute("aria-hidden", open ? "false" : "true");
    }
    if (workspace) {
      if (open) { workspace.setAttribute("inert", ""); }
      else { workspace.removeAttribute("inert"); }
    }
    if (open) {
      lastNavFocus = document.activeElement;
      var activeLink = app.querySelector(".jc-tab.is-active") || app.querySelector(".jc-tab");
      if (activeLink) { activeLink.focus(); }
    } else if (lastNavFocus && typeof lastNavFocus.focus === "function") {
      lastNavFocus.focus();
      lastNavFocus = null;
    }
  }
  if (menuToggle) {
    menuToggle.addEventListener("click", function () {
      setNav(!app.classList.contains("is-nav-open"));
    });
  }
  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-jc-nav-close]")) { setNav(false); }
    if (e.target.closest(".jc-tab") && window.matchMedia("(max-width: 1023px)").matches) {
      setNav(false);
    }
  });
  document.querySelectorAll(".jc-tab.is-active").forEach(function (link) {
    link.setAttribute("aria-current", "page");
  });
  document.querySelectorAll(".jc-stitch-mobile-nav a.is-active").forEach(function (link) {
    link.setAttribute("aria-current", "page");
  });
  var desktopNav = window.matchMedia("(min-width: 1024px)");
  function closeNavOnDesktop(e) {
    var drawer = app ? app.querySelector(".jc-sidebar") : null;
    if (e.matches) {
      if (app && app.classList.contains("is-nav-open")) { setNav(false); }
      if (drawer) {
        drawer.removeAttribute("role");
        drawer.removeAttribute("aria-modal");
        drawer.setAttribute("aria-hidden", "false");
      }
    } else if (drawer && !app.classList.contains("is-nav-open")) {
      drawer.setAttribute("role", "dialog");
      drawer.setAttribute("aria-modal", "false");
      drawer.setAttribute("aria-hidden", "true");
    }
  }
  if (desktopNav.addEventListener) { desktopNav.addEventListener("change", closeNavOnDesktop); }
  closeNavOnDesktop(desktopNav);

  // Tema visual persistente (solo presentaciÃ³n).
  var themeToggle = document.getElementById("jcThemeToggle");
  var themeIcon = document.getElementById("jcThemeIcon");
  function syncThemeIcon() {
    var isLight = document.documentElement.classList.contains("jc-theme-light");
    if (themeIcon) { themeIcon.textContent = isLight ? "dark_mode" : "light_mode"; }
    if (themeToggle) {
      themeToggle.setAttribute("aria-label", isLight ? "Usar modo oscuro" : "Usar modo claro");
      themeToggle.setAttribute("title", isLight ? "Usar modo oscuro" : "Usar modo claro");
    }
  }
  if (themeToggle) {
    themeToggle.addEventListener("click", function () {
      var isLight = document.documentElement.classList.toggle("jc-theme-light");
      localStorage.setItem("jc-theme", isLight ? "light" : "dark");
      syncThemeIcon();
    });
  }
  syncThemeIcon();

  // ── Modales (fade + backdrop) ─────────────────────────────────────────
  function getFocusable(scope) {
    return Array.prototype.slice.call(scope.querySelectorAll(
      'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])'
    )).filter(function (el) { return !el.hidden && el.offsetParent !== null; });
  }
  function openModal(id, trigger) {
    var m = document.getElementById(id);
    if (m) {
      lastModalTrigger = trigger || document.activeElement;
      m.classList.add("is-open");
      m.setAttribute("aria-hidden", "false");
      document.body.style.overflow = "hidden";
      var focusable = getFocusable(m);
      if (focusable.length) { focusable[0].focus(); }
    }
  }
  function closeModal(m) {
    m.classList.remove("is-open");
    m.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
    if (lastModalTrigger && typeof lastModalTrigger.focus === "function") {
      lastModalTrigger.focus();
    }
    lastModalTrigger = null;
  }
  document.addEventListener("click", function (e) {
    var opener = e.target.closest("[data-jc-open]");
    if (opener) {
      e.preventDefault();
      openModal(opener.getAttribute("data-jc-open"), opener);
      // Prefill: copiar data-fill-* a campos del modal con name correspondiente.
      var modal = document.getElementById(opener.getAttribute("data-jc-open"));
      if (modal) {
        Object.keys(opener.dataset).forEach(function (k) {
          if (k.indexOf("fill") === 0) {
            var field = k.replace(/^fill/, "");
            field = field.charAt(0).toLowerCase() + field.slice(1);
            var input = modal.querySelector('[name="' + field + '"]');
            if (!input) {
              var snakeField = field.replace(/[A-Z]/g, function (letter) {
                return "_" + letter.toLowerCase();
              });
              input = modal.querySelector('[name="' + snakeField + '"]');
            }
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
    if (e.key === "Tab" && app && app.classList.contains("is-nav-open")) {
      var sidebar = app.querySelector(".jc-sidebar");
      var sidebarItems = sidebar ? getFocusable(sidebar) : [];
      if (sidebarItems.length) {
        var sidebarFirst = sidebarItems[0];
        var sidebarLast = sidebarItems[sidebarItems.length - 1];
        if (e.shiftKey && document.activeElement === sidebarFirst) {
          e.preventDefault();
          sidebarLast.focus();
        } else if (!e.shiftKey && document.activeElement === sidebarLast) {
          e.preventDefault();
          sidebarFirst.focus();
        }
      }
    }
    if (e.key === "Escape") {
      var open = document.querySelector(".jc-modal.is-open");
      if (open) { closeModal(open); return; }
      if (app && app.classList.contains("is-nav-open")) { setNav(false); }
    }
    if (e.key === "Tab") {
      var activeModal = document.querySelector(".jc-modal.is-open");
      if (!activeModal) { return; }
      var items = getFocusable(activeModal);
      if (!items.length) { return; }
      var first = items[0];
      var last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
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
    var currencyInput = scope.querySelector('[name="currency"]');
    var app = document.querySelector(".jc");
    function calc() {
      var p = (parseFloat(cost.value) || 0) - (parseFloat(inv.value) || 0);
      var cur = currencyInput ? currencyInput.value : ((app && app.dataset.currency) || "PEN");
      out.textContent = "Utilidad: " + (p >= 0 ? "+" : "−") + Math.abs(p).toFixed(2) + " " + cur;
      out.style.color = p >= 0 ? "" : "#991b1b";
    }
    cost.addEventListener("input", calc);
    inv.addEventListener("input", calc);
    if (currencyInput) { currencyInput.addEventListener("change", calc); }
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

  // Modal de nueva suscripción: navegación visual en cuatro pasos.
  document.querySelectorAll("[data-lvas-form]").forEach(function (form) {
    var modal = form.closest(".jc-modal");
    var content = form.querySelector(".lvas-content");
    var steps = Array.prototype.slice.call(form.querySelectorAll("[data-lvas-step]"));
    var indicators = Array.prototype.slice.call(form.querySelectorAll("[data-lvas-stepper]"));
    var currentLabel = form.querySelector("[data-lvas-current]");
    var progress = form.querySelector("[data-lvas-progress]");
    var back = form.querySelector("[data-lvas-back]");
    var next = form.querySelector("[data-lvas-next]");
    var submit = form.querySelector("[data-lvas-submit]");
    var footerProfit = form.querySelector("[data-lvas-footer-profit]");
    var step = 1;
    var maxReached = 1;

    function firstInvalid(scope) {
      var clientId = form.querySelector("[data-jc-client]");
      var clientName = form.querySelector("[data-jc-cname]");
      if (step === 1 && !((clientId && clientId.value) || (clientName && clientName.value.trim()))) {
        if (clientName) {
          clientName.setCustomValidity("Selecciona un cliente o escribe su nombre.");
          clientName.reportValidity();
          clientName.setCustomValidity("");
          clientName.focus();
        }
        return true;
      }
      var fields = Array.prototype.slice.call(scope.querySelectorAll("input,textarea,select"));
      for (var i = 0; i < fields.length; i += 1) {
        if (!fields[i].disabled && !fields[i].checkValidity()) {
          fields[i].reportValidity();
          fields[i].focus();
          return true;
        }
      }
      return false;
    }

    function showStep(value) {
      step = Math.max(1, Math.min(4, value));
      maxReached = Math.max(maxReached, step);
      steps.forEach(function (panel) {
        var active = parseInt(panel.getAttribute("data-lvas-step"), 10) === step;
        panel.hidden = !active;
        panel.classList.toggle("is-active", active);
      });
      indicators.forEach(function (item) {
        var itemStep = parseInt(item.getAttribute("data-lvas-stepper"), 10);
        item.classList.toggle("is-active", itemStep === step);
        item.classList.toggle("is-done", itemStep < step);
        var badge = item.querySelector("button>span");
        if (badge) { badge.textContent = itemStep < step ? "✓" : String(itemStep); }
      });
      if (currentLabel) { currentLabel.textContent = String(step); }
      if (progress) { progress.style.width = String(step * 25) + "%"; }
      if (back) { back.hidden = step === 1; }
      if (next) { next.hidden = step === 4; }
      if (submit) { submit.hidden = step !== 4; }
      if (footerProfit) { footerProfit.hidden = step !== 4; }
      if (content) { content.scrollTop = 0; }
    }

    if (next) {
      next.addEventListener("click", function () {
        var panel = form.querySelector('[data-lvas-step="' + step + '"]');
        if (!panel || firstInvalid(panel)) { return; }
        showStep(step + 1);
      });
    }
    if (back) { back.addEventListener("click", function () { showStep(step - 1); }); }
    form.querySelectorAll("[data-lvas-select]").forEach(function (button) {
      button.addEventListener("click", function () {
        var target = parseInt(button.getAttribute("data-lvas-select"), 10);
        if (target <= maxReached) { showStep(target); }
      });
    });

    var passwordToggle = form.querySelector("[data-lvas-password]");
    if (passwordToggle) {
      passwordToggle.addEventListener("click", function () {
        var input = form.querySelector('[name="account_password"]');
        if (!input) { return; }
        var visible = input.type === "text";
        input.type = visible ? "password" : "text";
        passwordToggle.setAttribute("aria-label", visible ? "Mostrar contraseña" : "Ocultar contraseña");
        var icon = passwordToggle.querySelector(".material-symbols-outlined");
        if (icon) { icon.textContent = visible ? "visibility" : "visibility_off"; }
      });
    }

    var cost = form.querySelector('[name="cost"]');
    var investment = form.querySelector('[name="investment"]');
    var currency = form.querySelector('[name="currency"]');
    var saleOut = form.querySelector("[data-lvas-sale]");
    var investmentOut = form.querySelector("[data-lvas-investment]");
    var profitOut = form.querySelector("[data-profit-out]");
    function moneySymbol(code) { return code === "PEN" ? "S/" : code === "USD" ? "$" : code; }
    function refreshFinance() {
      var sale = parseFloat(cost && cost.value) || 0;
      var invested = parseFloat(investment && investment.value) || 0;
      var profitValue = sale - invested;
      var code = currency ? currency.value : "PEN";
      var symbol = moneySymbol(code);
      form.querySelectorAll("[data-lvas-currency]").forEach(function (label) { label.textContent = code; });
      if (saleOut) { saleOut.textContent = symbol + " " + sale.toFixed(2); }
      if (investmentOut) { investmentOut.textContent = symbol + " " + invested.toFixed(2); }
      var profitText = (profitValue >= 0 ? "+" : "−") + symbol + " " + Math.abs(profitValue).toFixed(2);
      if (profitOut) {
        profitOut.textContent = profitText;
        profitOut.closest("div").classList.toggle("is-negative", profitValue < 0);
      }
      if (footerProfit) {
        footerProfit.textContent = "Utilidad " + profitText;
        footerProfit.classList.toggle("is-negative", profitValue < 0);
      }
    }
    if (cost) { cost.addEventListener("input", refreshFinance); }
    if (investment) { investment.addEventListener("input", refreshFinance); }
    if (currency) { currency.addEventListener("change", refreshFinance); }
    refreshFinance();

    if (modal && window.MutationObserver) {
      new MutationObserver(function () {
        if (modal.classList.contains("is-open")) {
          maxReached = 1;
          showStep(1);
        }
      }).observe(modal, { attributes: true, attributeFilter: ["class"] });
    }
    showStep(1);
  });

  // ── Campana de notificaciones ─────────────────────────────────────────
  var root = document.querySelector(".jc");
  var bell = document.getElementById("jcBell");
  var panel = document.getElementById("jcBellPanel");
  var countEl = document.getElementById("jcBellCount");
  var bellDot = bell ? bell.querySelector(".lv-bell-dot") : null;
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
        if (bellDot) { bellDot.hidden = !(data.count > 0); }
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
    bell.setAttribute("aria-expanded", "false");
    bell.setAttribute("aria-controls", "jcBellPanel");
    bell.addEventListener("click", function () {
      panel.hidden = !panel.hidden;
      bell.setAttribute("aria-expanded", panel.hidden ? "false" : "true");
    });
    document.addEventListener("click", function (e) {
      if (!e.target.closest(".jc-topbar__actions")) {
        panel.hidden = true;
        bell.setAttribute("aria-expanded", "false");
      }
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
      document.querySelectorAll(".jc-table--subs tbody tr, .lvsd-mobile-card")
    );
    var subNoMatch = Array.prototype.slice.call(
      document.querySelectorAll(".jc-subs-nomatch")
    );
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
      subNoMatch.forEach(function (emptyState) {
        emptyState.hidden = !(term && shown === 0);
      });
    }
    subSearch.addEventListener("input", filterSubs);
    filterSubs();
  }

  // Inventario de correos: revelar/copiar credenciales y exigir cliente al vender.
  function syncInventoryForm(form) {
    var status = form.querySelector("[data-jc-status-select]");
    var customerField = form.querySelector("[data-jc-customer-field]");
    if (!status || !customerField) { return; }
    var customerInput = customerField.querySelector('[name="customer_name"]');
    var isSold = status.value === "sold";
    customerField.hidden = !isSold;
    if (customerInput) {
      customerInput.required = isSold;
      if (!isSold) { customerInput.value = ""; }
    }
  }
  document.querySelectorAll("[data-jc-inventory-form]").forEach(function (form) {
    var status = form.querySelector("[data-jc-status-select]");
    if (status) {
      status.addEventListener("change", function () { syncInventoryForm(form); });
      syncInventoryForm(form);
    }
  });

  // Modal "Agregar correos": interacción visual de Lovable conectada al formulario real.
  document.querySelectorAll("[data-jc-email-add-form]").forEach(function (form) {
    var emailsInput = form.querySelector('[name="emails"]');
    var passwordInput = form.querySelector('[name="password"]');
    var countOutput = form.querySelector("[data-jc-email-count]");
    var summaryOutput = form.querySelector("[data-jc-email-save-summary]");
    var statusSelect = form.querySelector("[data-jc-status-select]");
    var platformSelect = form.querySelector('[name="service"]');
    var platformPreview = form.querySelector("[data-jc-platform-preview]");

    function countEmails() {
      var count = (emailsInput.value || "").split(/[\n,]/).map(function (item) {
        return item.trim();
      }).filter(Boolean).length;
      countOutput.textContent = count + (count === 1 ? " correo agregado" : " correos agregados");
      countOutput.classList.toggle("has-items", count > 0);
      summaryOutput.textContent = count > 0
        ? "Se guardarán " + count + (count === 1 ? " cuenta." : " cuentas.")
        : "Añade al menos un correo.";
    }

    function passwordScore(value) {
      var score = 0;
      if (value.length >= 8) { score++; }
      if (/[A-Z]/.test(value) && /[a-z]/.test(value)) { score++; }
      if (/\d/.test(value)) { score++; }
      if (/[^A-Za-z0-9]/.test(value)) { score++; }
      return score;
    }

    function updatePasswordStrength() {
      var score = passwordScore(passwordInput.value || "");
      var labels = ["Muy débil", "Débil", "Aceptable", "Buena", "Excelente"];
      var color = score <= 1 ? "var(--ea-danger)" : (score === 2 ? "#eab308" : "var(--ea-brand)");
      form.querySelectorAll("[data-jc-password-bars] i").forEach(function (bar, index) {
        bar.style.backgroundColor = passwordInput.value && index < score
          ? color
          : "color-mix(in oklab,var(--ea-fg) 10%,transparent)";
      });
      form.querySelector("[data-jc-password-strength]").textContent = passwordInput.value ? labels[score] : "Seguridad";
    }

    function updatePlatformPreview() {
      var option = platformSelect.options[platformSelect.selectedIndex];
      var hasPlatform = Boolean(platformSelect.value && option);
      platformPreview.hidden = !hasPlatform;
      if (hasPlatform) {
        var label = option.textContent.trim();
        form.querySelector("[data-jc-platform-name]").textContent = label;
        form.querySelector("[data-jc-platform-mark]").textContent = label.slice(0, 3).toUpperCase();
      }
    }

    form.querySelectorAll("[data-jc-status-chip]").forEach(function (chip) {
      chip.addEventListener("click", function () {
        statusSelect.value = chip.getAttribute("data-jc-status-chip");
        statusSelect.dispatchEvent(new Event("change", { bubbles: true }));
        form.querySelectorAll("[data-jc-status-chip]").forEach(function (item) {
          item.classList.toggle("is-active", item === chip);
        });
      });
    });

    var passwordToggle = form.querySelector("[data-jc-email-password-toggle]");
    passwordToggle.addEventListener("click", function () {
      var showing = passwordInput.type === "text";
      passwordInput.type = showing ? "password" : "text";
      passwordToggle.setAttribute("aria-label", showing ? "Mostrar contraseña" : "Ocultar contraseña");
      passwordToggle.querySelector(".material-symbols-outlined").textContent = showing ? "visibility" : "visibility_off";
    });

    emailsInput.addEventListener("input", countEmails);
    passwordInput.addEventListener("input", updatePasswordStrength);
    platformSelect.addEventListener("change", updatePlatformPreview);
    countEmails();
    updatePasswordStrength();
    updatePlatformPreview();
  });

  // Modal "Agregar servicio": réplica visual de Lovable conectada al ServiceForm real.
  document.querySelectorAll("[data-jc-service-add-form]").forEach(function (form) {
    var nameInput = form.querySelector('[name="name"]');
    var categorySelect = form.querySelector('[name="category"]');
    var iconInput = form.querySelector('[name="icon"]');
    var imageInput = form.querySelector('[name="image"]');
    var summary = form.querySelector("[data-jc-service-save-summary]");
    var categoryPreview = form.querySelector("[data-jc-service-category-preview]");
    var iconPreview = form.querySelector("[data-jc-service-icon-preview]");
    var dropzone = form.querySelector("[data-jc-service-dropzone]");
    var emptyState = form.querySelector("[data-jc-service-upload-empty]");
    var previewState = form.querySelector("[data-jc-service-upload-preview]");
    var previewImage = form.querySelector("[data-jc-service-preview-image]");
    var fileName = form.querySelector("[data-jc-service-file-name]");
    var removeImage = form.querySelector("[data-jc-service-image-remove]");
    var objectUrl = "";

    function updateSummary() {
      var name = nameInput.value.trim();
      summary.textContent = name ? "Se creará “" + name + "”." : "Escribe un nombre para el servicio.";
    }

    function updateCategory() {
      var option = categorySelect.options[categorySelect.selectedIndex];
      categoryPreview.hidden = !categorySelect.value;
      if (categorySelect.value && option) {
        form.querySelector("[data-jc-service-category-name]").textContent = option.textContent.trim();
      }
    }

    function updateIcon() {
      var icon = iconInput.value.trim();
      iconPreview.textContent = icon || "auto_awesome";
      iconPreview.classList.toggle("has-icon", Boolean(icon));
      form.querySelectorAll("[data-jc-service-icon]").forEach(function (button) {
        button.classList.toggle("is-active", button.getAttribute("data-jc-service-icon") === icon);
      });
    }

    function setImage(file) {
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
        objectUrl = "";
      }
      if (!file) {
        imageInput.value = "";
        emptyState.hidden = false;
        previewState.hidden = true;
        removeImage.hidden = true;
        previewImage.removeAttribute("src");
        fileName.textContent = "";
        return;
      }
      objectUrl = URL.createObjectURL(file);
      previewImage.src = objectUrl;
      fileName.textContent = file.name;
      emptyState.hidden = true;
      previewState.hidden = false;
      removeImage.hidden = false;
    }

    form.querySelectorAll("[data-jc-service-icon]").forEach(function (button) {
      button.addEventListener("click", function () {
        iconInput.value = button.getAttribute("data-jc-service-icon");
        iconInput.dispatchEvent(new Event("input", { bubbles: true }));
      });
    });
    dropzone.addEventListener("click", function () { imageInput.click(); });
    dropzone.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        imageInput.click();
      }
    });
    ["dragenter", "dragover"].forEach(function (eventName) {
      dropzone.addEventListener(eventName, function (event) {
        event.preventDefault();
        dropzone.classList.add("is-dragging");
      });
    });
    ["dragleave", "drop"].forEach(function (eventName) {
      dropzone.addEventListener(eventName, function (event) {
        event.preventDefault();
        dropzone.classList.remove("is-dragging");
      });
    });
    dropzone.addEventListener("drop", function (event) {
      var file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
      if (!file) { return; }
      var transfer = new DataTransfer();
      transfer.items.add(file);
      imageInput.files = transfer.files;
      setImage(file);
    });
    imageInput.addEventListener("click", function (event) { event.stopPropagation(); });
    imageInput.addEventListener("change", function () { setImage(imageInput.files && imageInput.files[0]); });
    removeImage.addEventListener("click", function () { setImage(null); });
    nameInput.addEventListener("input", updateSummary);
    categorySelect.addEventListener("change", updateCategory);
    iconInput.addEventListener("input", updateIcon);
    form.addEventListener("reset", function () {
      window.setTimeout(function () {
        updateSummary();
        updateCategory();
        updateIcon();
        setImage(null);
      }, 0);
    });
    updateSummary();
    updateCategory();
    updateIcon();
  });

  function showCopyFeedback(message) {
    var old = document.querySelector(".jc-copy-feedback");
    if (old) { old.remove(); }
    var notice = document.createElement("div");
    notice.className = "jc-copy-feedback";
    notice.setAttribute("role", "status");
    notice.textContent = message;
    document.body.appendChild(notice);
    window.setTimeout(function () { notice.remove(); }, 1600);
  }

  function loadInventorySecret(url) {
    return fetch(url, {
      credentials: "same-origin",
      headers: { "Accept": "application/json" }
    }).then(function (response) {
      if (!response.ok) { throw new Error("secret_unavailable"); }
      return response.json();
    }).then(function (data) {
      return data.password || "";
    });
  }

  document.addEventListener("click", function (event) {
    var reveal = event.target.closest("[data-jc-reveal]");
    if (reveal) {
      var box = reveal.closest(".jc-email-card__password");
      var output = box && box.querySelector("[data-jc-secret]");
      if (output && box) {
        var isHidden = output.getAttribute("data-visible") !== "true";
        if (!isHidden) {
          output.textContent = "••••••••••";
          output.setAttribute("data-visible", "false");
        } else {
          reveal.disabled = true;
          loadInventorySecret(box.getAttribute("data-jc-secret-url")).then(function (secret) {
            output.textContent = secret || "Sin contraseña";
            output.setAttribute("data-visible", "true");
          }).catch(function () {
            showCopyFeedback("No se pudo obtener la contraseña");
          }).finally(function () {
            reveal.disabled = false;
          });
        }
        var icon = reveal.querySelector(".material-symbols-outlined");
        if (icon) { icon.textContent = isHidden ? "visibility_off" : "visibility"; }
        reveal.setAttribute("aria-label", isHidden ? "Ocultar contraseña" : "Mostrar contraseña");
      }
      return;
    }

    var copySecret = event.target.closest("[data-jc-copy-secret]");
    if (copySecret) {
      var secretBox = copySecret.closest(".jc-email-card__password");
      loadInventorySecret(secretBox.getAttribute("data-jc-secret-url")).then(function (secret) {
        if (!secret) { throw new Error("empty_secret"); }
        return navigator.clipboard.writeText(secret);
      }).then(function () {
        showCopyFeedback("Contraseña copiada");
      }).catch(function () {
        showCopyFeedback("No se pudo copiar la contraseña");
      });
      return;
    }

    var copy = event.target.closest("[data-jc-copy]");
    if (copy) {
      var value = copy.getAttribute("data-jc-copy") || "";
      if (value && navigator.clipboard) {
        navigator.clipboard.writeText(value).then(function () {
          showCopyFeedback("Copiado");
        });
      }
      return;
    }

    var opener = event.target.closest('[data-jc-open="modalEmailSell"]');
    if (opener) {
      var sellModal = document.getElementById("modalEmailSell");
      var display = sellModal && sellModal.querySelector("[data-jc-email-display]");
      if (display) { display.textContent = opener.getAttribute("data-fill-email-display") || ""; }
      window.setTimeout(function () {
        var customer = sellModal && sellModal.querySelector('[name="customer_name"]');
        if (customer) { customer.focus(); }
      }, 0);
    }

    var inventoryOpener = event.target.closest('[data-jc-open="modalEmailEdit"]');
    if (inventoryOpener) {
      var secretUrl = inventoryOpener.getAttribute("data-secret-url");
      window.setTimeout(function () {
        var editForm = document.querySelector("#modalEmailEdit [data-jc-inventory-form]");
        if (editForm) {
          syncInventoryForm(editForm);
          var passwordInput = editForm.querySelector('[name="password"]');
          if (passwordInput && secretUrl) {
            passwordInput.disabled = true;
            loadInventorySecret(secretUrl).then(function (secret) {
              passwordInput.value = secret;
            }).catch(function () {
              showCopyFeedback("No se pudo cargar la contraseña");
            }).finally(function () {
              passwordInput.disabled = false;
            });
          }
        }
      }, 0);
    }
  });
})();
