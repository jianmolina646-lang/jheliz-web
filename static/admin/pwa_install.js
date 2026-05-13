// Jheliz Admin PWA installer
// 1. Inyecta <link rel="manifest"> y meta theme-color para que Chrome detecte
//    el panel como instalable.
// 2. Registra el service worker dedicado del admin.
// 3. Muestra un banner discreto "📱 Instalar app" cuando el browser dispara
//    `beforeinstallprompt` (Chrome/Edge en Android).
// 4. En iOS Safari muestra una guía corta porque iOS no expone la API de
//    instalación automática (hay que usar "Compartir → Añadir a inicio").

(function () {
  "use strict";

  if (typeof document === "undefined") return;

  // --- 1. Inyectar manifest + theme-color + apple-touch-icon ---
  function injectHeadTags() {
    var head = document.head;
    if (!head) return;

    if (!head.querySelector('link[rel="manifest"]')) {
      var link = document.createElement("link");
      link.rel = "manifest";
      link.href = "/panel-jheliz-2026/manifest.webmanifest";
      head.appendChild(link);
    }

    if (!head.querySelector('meta[name="theme-color"]')) {
      var meta = document.createElement("meta");
      meta.name = "theme-color";
      meta.content = "#ec4899";
      head.appendChild(meta);
    }

    if (!head.querySelector('link[rel="apple-touch-icon"]')) {
      var apple = document.createElement("link");
      apple.rel = "apple-touch-icon";
      apple.href = "/static/img/apple-touch-icon.png";
      head.appendChild(apple);
    }

    if (!head.querySelector('meta[name="apple-mobile-web-app-capable"]')) {
      var capable = document.createElement("meta");
      capable.name = "apple-mobile-web-app-capable";
      capable.content = "yes";
      head.appendChild(capable);

      var statusBar = document.createElement("meta");
      statusBar.name = "apple-mobile-web-app-status-bar-style";
      statusBar.content = "black-translucent";
      head.appendChild(statusBar);

      var title = document.createElement("meta");
      title.name = "apple-mobile-web-app-title";
      title.content = "Jheliz Admin";
      head.appendChild(title);
    }
  }

  // --- 2. Registrar service worker ---
  function registerServiceWorker() {
    if (!("serviceWorker" in navigator)) return;
    // Cumple los requisitos de PWA "instalable" (Chrome necesita SW + manifest).
    navigator.serviceWorker
      .register("/panel-jheliz-2026/sw.js", { scope: "/panel-jheliz-2026/" })
      .catch(function () {
        // Si falla, la web sigue andando. No mostramos error al usuario.
      });
  }

  // --- 3. Banner "Instalar app" ---
  var deferredPrompt = null;
  var bannerShown = false;
  var STORAGE_KEY = "jheliz_admin_pwa_banner_dismissed_at";
  var DISMISS_DAYS = 14;

  function shouldShowBanner() {
    // No mostrar si ya está instalado.
    if (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) {
      return false;
    }
    if (window.navigator.standalone === true) {
      return false; // iOS standalone
    }
    // No mostrar si fue descartado hace poco.
    try {
      var ts = parseInt(localStorage.getItem(STORAGE_KEY) || "0", 10);
      if (ts && Date.now() - ts < DISMISS_DAYS * 24 * 3600 * 1000) {
        return false;
      }
    } catch (e) {
      /* localStorage no disponible: seguimos */
    }
    return true;
  }

  function buildBanner(onInstall, onDismiss, isIOS) {
    var wrap = document.createElement("div");
    wrap.id = "jheliz-pwa-banner";
    wrap.setAttribute("role", "dialog");
    wrap.setAttribute("aria-label", "Instalar Jheliz Admin");
    wrap.style.cssText =
      "position:fixed;left:50%;bottom:18px;transform:translateX(-50%);" +
      "z-index:99999;max-width:480px;width:calc(100% - 28px);" +
      "background:linear-gradient(135deg,#1a1330 0%,#2b1645 60%,#3a0f3a 100%);" +
      "color:#fff;border:1px solid rgba(236,72,153,.45);" +
      "border-radius:18px;padding:14px 16px;" +
      "box-shadow:0 18px 48px rgba(0,0,0,.55),0 0 36px rgba(236,72,153,.25);" +
      "display:flex;align-items:center;gap:12px;font-family:'Geist','Inter',system-ui,sans-serif;" +
      "transform:translate(-50%,140%);transition:transform .35s cubic-bezier(.2,.8,.2,1);";

    var iconBox = document.createElement("div");
    iconBox.style.cssText =
      "flex:0 0 44px;height:44px;border-radius:12px;" +
      "background:linear-gradient(135deg,#ec4899,#a855f7);" +
      "display:flex;align-items:center;justify-content:center;font-size:22px;" +
      "box-shadow:0 8px 22px rgba(236,72,153,.45);";
    iconBox.textContent = "📱";

    var body = document.createElement("div");
    body.style.cssText = "flex:1;min-width:0;line-height:1.25;";
    var title = document.createElement("div");
    title.style.cssText = "font-weight:700;font-size:14px;color:#fff;";
    title.textContent = isIOS ? "Instalar Jheliz Admin" : "Instalar el panel como app";
    var sub = document.createElement("div");
    sub.style.cssText = "font-size:12px;color:#fbcfe8;margin-top:2px;";
    sub.textContent = isIOS
      ? "Tocá Compartir y luego «Añadir a inicio» para tener el panel en tu home."
      : "Acceso 1-tap desde tu cel, sin barra del browser.";
    body.appendChild(title);
    body.appendChild(sub);

    var actions = document.createElement("div");
    actions.style.cssText = "display:flex;align-items:center;gap:6px;flex-shrink:0;";

    if (!isIOS) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = "Instalar";
      btn.style.cssText =
        "background:linear-gradient(135deg,#ec4899,#a855f7);" +
        "color:#fff;border:0;border-radius:999px;" +
        "padding:8px 14px;font-weight:700;font-size:13px;cursor:pointer;" +
        "box-shadow:0 6px 16px rgba(236,72,153,.45);";
      btn.addEventListener("click", function () {
        onInstall();
      });
      actions.appendChild(btn);
    }

    var close = document.createElement("button");
    close.type = "button";
    close.setAttribute("aria-label", "Cerrar");
    close.textContent = "✕";
    close.style.cssText =
      "background:rgba(255,255,255,.06);color:#fff;border:0;" +
      "border-radius:999px;width:30px;height:30px;cursor:pointer;font-size:13px;";
    close.addEventListener("click", function () {
      onDismiss();
    });
    actions.appendChild(close);

    wrap.appendChild(iconBox);
    wrap.appendChild(body);
    wrap.appendChild(actions);
    return wrap;
  }

  function showBanner(isIOS) {
    if (bannerShown) return;
    if (!shouldShowBanner()) return;
    bannerShown = true;

    var node = buildBanner(
      function onInstall() {
        if (!deferredPrompt) {
          // Si por algún motivo perdimos el evento, igual marcamos como descartado.
          dismiss();
          return;
        }
        deferredPrompt.prompt();
        deferredPrompt.userChoice.finally(function () {
          deferredPrompt = null;
          dismiss();
        });
      },
      function onDismiss() {
        dismiss();
      },
      isIOS
    );

    document.body.appendChild(node);
    // Animación de entrada.
    requestAnimationFrame(function () {
      node.style.transform = "translate(-50%, 0)";
    });

    function dismiss() {
      try {
        localStorage.setItem(STORAGE_KEY, String(Date.now()));
      } catch (e) {
        /* noop */
      }
      node.style.transform = "translate(-50%, 140%)";
      setTimeout(function () {
        if (node.parentNode) node.parentNode.removeChild(node);
      }, 350);
    }
  }

  function setup() {
    injectHeadTags();
    registerServiceWorker();

    // Chrome/Edge en Android disparan beforeinstallprompt cuando todo está listo.
    window.addEventListener("beforeinstallprompt", function (e) {
      e.preventDefault();
      deferredPrompt = e;
      showBanner(false);
    });

    // iOS Safari: detectar y mostrar guía manual.
    var ua = window.navigator.userAgent || "";
    var isIOS = /iPhone|iPad|iPod/.test(ua) && !window.MSStream;
    var isIOSSafari = isIOS && /Safari\//.test(ua) && !/CriOS|FxiOS/.test(ua);
    if (isIOSSafari) {
      // Mostrar la guía después de 2 s así no estorba al primer paint.
      setTimeout(function () {
        showBanner(true);
      }, 2000);
    }

    // Listener "appinstalled" para limpiar el banner si terminó de instalarse.
    window.addEventListener("appinstalled", function () {
      var node = document.getElementById("jheliz-pwa-banner");
      if (node && node.parentNode) node.parentNode.removeChild(node);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setup);
  } else {
    setup();
  }
})();
