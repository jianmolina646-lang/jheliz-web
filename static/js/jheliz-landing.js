(function () {
  "use strict";

  var toggle = document.querySelector(".jl-navbar__toggle");
  var menu = document.getElementById("jlMobileMenu");
  if (!toggle || !menu) { return; }

  function setOpen(open) {
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    toggle.setAttribute("aria-label", open ? "Cerrar menú" : "Abrir menú");
    menu.hidden = !open;
  }

  toggle.addEventListener("click", function () {
    setOpen(toggle.getAttribute("aria-expanded") !== "true");
  });

  menu.addEventListener("click", function (event) {
    if (event.target.closest("a")) { setOpen(false); }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") {
      setOpen(false);
      toggle.focus();
    }
  });

  window.addEventListener("resize", function () {
    if (window.matchMedia("(min-width: 768px)").matches) { setOpen(false); }
  });
})();

(function () {
  "use strict";

  var canvas = document.getElementById("jlBusinessPreviewChart");
  if (!canvas || typeof window.Chart === "undefined") { return; }

  new window.Chart(canvas, {
    type: "bar",
    data: {
      labels: ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"],
      datasets: [{
        label: "Ingresos demostrativos",
        data: [38, 52, 44, 68, 59, 81, 72, 94, 86, 100, 78, 92],
        backgroundColor: "rgba(0, 225, 145, 0.72)",
        borderColor: "rgba(0, 225, 145, 1)",
        borderWidth: 1,
        borderRadius: 6,
        borderSkipped: false,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 450 },
      interaction: { intersect: false, mode: "index" },
      plugins: {
        legend: { display: false },
        tooltip: {
          displayColors: false,
          callbacks: { label: function (context) { return "Índice demostrativo: " + context.raw; } },
        },
      },
      scales: {
        x: {
          border: { display: false },
          grid: { display: false },
          ticks: { color: "rgba(226, 232, 240, 0.62)", font: { size: 9 } },
        },
        y: {
          beginAtZero: true,
          suggestedMax: 110,
          border: { display: false },
          grid: { color: "rgba(148, 163, 184, 0.10)" },
          ticks: { display: false },
        },
      },
    },
  });
})();
