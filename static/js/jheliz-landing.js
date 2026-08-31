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

  var started = false;
  var colors = ["#22d3ee", "#38bdf8", "#60a5fa", "#818cf8", "#a78bfa", "#8b5cf6", "#ec4899", "#fb7185", "#f59e0b", "#fbbf24", "#34d399", "#00c98b"];

  function startChart() {
    if (started) { return; }
    started = true;
    new window.Chart(canvas, {
    type: "bar",
    data: {
      labels: ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"],
      datasets: [{
        label: "Ingresos demostrativos",
        data: [38, 52, 44, 68, 59, 81, 72, 94, 86, 100, 78, 92],
        backgroundColor: function (context) {
          var area = context.chart.chartArea;
          var color = colors[context.dataIndex] || "#00c98b";
          if (!area) { return color; }
          var gradient = context.chart.ctx.createLinearGradient(0, area.top, 0, area.bottom);
          gradient.addColorStop(0, color);
          gradient.addColorStop(1, color + "88");
          return gradient;
        },
        hoverBackgroundColor: colors,
        borderColor: colors,
        borderWidth: 1.5,
        borderRadius: { topLeft: 10, topRight: 10, bottomLeft: 4, bottomRight: 4 },
        borderSkipped: false,
        barPercentage: .72,
        categoryPercentage: .9,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: {
        duration: 1450,
        easing: "easeOutQuart",
        delay: function (context) { return context.type === "data" ? context.dataIndex * 75 : 0; },
      },
      transitions: { active: { animation: { duration: 320, easing: "easeOutCubic" } } },
      interaction: { intersect: false, mode: "index" },
      plugins: {
        legend: { display: false },
        tooltip: {
          displayColors: true,
          backgroundColor: "rgba(15,35,28,.94)",
          titleColor: "#fff",
          bodyColor: "#d8fff0",
          borderColor: "rgba(71,229,176,.45)",
          borderWidth: 1,
          cornerRadius: 12,
          padding: 12,
          callbacks: { label: function (context) { return "Índice demostrativo: " + context.raw; } },
        },
      },
      scales: {
        x: {
          border: { display: false },
          grid: { display: false },
          ticks: { color: "rgba(65,94,82,.72)", font: { size: 9, weight: "600" } },
        },
        y: {
          beginAtZero: true,
          suggestedMax: 110,
          border: { display: false },
          grid: { color: "rgba(54,111,89,0.10)" },
          ticks: { display: false },
        },
      },
    },
    });
  }

  if ("IntersectionObserver" in window) {
    var observer = new IntersectionObserver(function (entries) {
      if (entries[0].isIntersecting) { startChart(); observer.disconnect(); }
    }, { threshold: .3 });
    observer.observe(canvas);
  } else { startChart(); }
})();
