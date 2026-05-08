/**
 * empty_state.js — PR I del paquete admin (item 9).
 *
 * Inyecta un empty state bonito (icono + título + sub + CTA) cuando un
 * changelist no tiene resultados. Reemplaza el feo "0 X" de Django.
 *
 * No requiere config: detecta automáticamente cuando un .results table
 * tiene 0 filas en tbody, oculta la tabla + paginator y muestra el card.
 */
(function(){
  if (window.__jhEmptyStateInstalled) return;
  window.__jhEmptyStateInstalled = true;

  // Mensaje + CTA según el tipo de página (orders / catalog / accounts...).
  // El path del admin trae el modelo, así podemos personalizar el mensaje.
  function getEmptyConfig() {
    var path = window.location.pathname;
    var qs = window.location.search;
    // Si viene de un filtro rápido, el mensaje es distinto (no es que no
    // exista nada, es que el filtro vacío).
    var isFiltered = qs && (qs.indexOf("?") === 0) && qs.length > 1;

    if (path.indexOf("/orders/order/") >= 0) {
      if (isFiltered) {
        return {
          icon: "🔍",
          title: "No hay pedidos con este filtro",
          sub: "Probá con otro filtro rápido o limpiá los filtros para ver todos los pedidos.",
          cta_label: "Limpiar filtros",
          cta_url: window.location.pathname,
        };
      }
      return {
        icon: "📦",
        title: "Aún no tenés pedidos",
        sub: "Cuando un cliente haga su primera compra, va a aparecer acá. Mientras tanto, podés crear uno manualmente.",
        cta_label: "Crear pedido manual",
        cta_url: window.location.pathname + "add/",
      };
    }
    if (path.indexOf("/catalog/product/") >= 0) {
      return {
        icon: "🛒",
        title: isFiltered ? "Ningún producto coincide" : "Tu catálogo está vacío",
        sub: isFiltered
          ? "Probá ajustando los filtros o la búsqueda."
          : "Empezá agregando tus servicios (Netflix, Disney+, Prime…) para que tus clientes los compren.",
        cta_label: isFiltered ? "Limpiar filtros" : "Crear producto",
        cta_url: isFiltered ? window.location.pathname : window.location.pathname + "add/",
      };
    }
    if (path.indexOf("/support/ticket/") >= 0) {
      return {
        icon: "✨",
        title: "Sin tickets sin responder",
        sub: "Buen trabajo. Todos los clientes tienen respuesta hasta el momento.",
        cta_label: null,
        cta_url: null,
      };
    }
    if (path.indexOf("/catalog/productreview/") >= 0) {
      return {
        icon: "⭐",
        title: "Sin reseñas por moderar",
        sub: "Cuando llegue una reseña nueva, te va a aparecer acá para aprobar o rechazar.",
        cta_label: null,
        cta_url: null,
      };
    }
    if (path.indexOf("/accounts/customer/") >= 0) {
      return {
        icon: "👥",
        title: isFiltered ? "Sin clientes con este criterio" : "Aún no tenés clientes",
        sub: isFiltered
          ? "Probá con otro filtro o búsqueda."
          : "Tus clientes aparecen acá automáticamente cuando hagan su primer pedido.",
        cta_label: isFiltered ? "Limpiar filtros" : null,
        cta_url: isFiltered ? window.location.pathname : null,
      };
    }
    // Default genérico para cualquier otro changelist.
    return {
      icon: isFiltered ? "🔍" : "📋",
      title: isFiltered ? "Sin resultados" : "No hay items todavía",
      sub: isFiltered
        ? "Probá ajustando los filtros o la búsqueda."
        : "Cuando agregues el primer item, va a aparecer acá.",
      cta_label: isFiltered ? "Limpiar filtros" : null,
      cta_url: isFiltered ? window.location.pathname : null,
    };
  }

  function renderEmptyState(container, cfg) {
    var html = (
      '<div class="jh-empty-state">' +
      '  <div class="jh-empty-state__icon">' + cfg.icon + '</div>' +
      '  <div class="jh-empty-state__title">' + escapeHtml(cfg.title) + '</div>' +
      '  <div class="jh-empty-state__sub">' + escapeHtml(cfg.sub) + '</div>' +
      (cfg.cta_label ? (
        '  <a href="' + escapeHtml(cfg.cta_url) + '" class="jh-empty-state__cta">' +
        '    ' + escapeHtml(cfg.cta_label) +
        '    <span aria-hidden="true">→</span>' +
        '  </a>'
      ) : '') +
      '</div>'
    );
    var wrap = document.createElement("div");
    wrap.innerHTML = html;
    container.appendChild(wrap.firstChild);
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function init() {
    // Sólo en páginas de changelist (las que tienen un id="result_list" o
    // un .results dentro del content).
    var resultList = document.getElementById("result_list");
    if (!resultList) return;
    // Si la tabla tiene filas, no hacemos nada.
    var rows = resultList.querySelectorAll("tbody tr");
    if (rows.length > 0) return;

    // Detectado: changelist sin filas. Buscamos el contenedor para inyectar.
    var container = resultList.closest(".result-list-wrapper")
      || resultList.parentNode;
    if (!container) return;

    var cfg = getEmptyConfig();
    // Ocultamos la tabla vacía y la paginación "0 X".
    var paginatorBlock = container.querySelector(".paginator");
    if (resultList) resultList.style.display = "none";
    if (paginatorBlock) paginatorBlock.style.display = "none";
    // También ocultamos el "Action:" dropdown si está vacío.
    var actionsBlock = container.querySelector(".actions");
    if (actionsBlock) actionsBlock.style.display = "none";

    renderEmptyState(container, cfg);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
