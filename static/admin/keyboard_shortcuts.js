/* Keyboard shortcuts globales para el panel admin (estilo Linear / Notion).
 *
 * Sequencias:
 *   g o  → ir a Pedidos
 *   g s  → ir a Stock por producto
 *   g r  → ir a Renovaciones
 *   g c  → ir a Clientes
 *   g d  → ir a Dashboard
 *   g t  → ir a Tickets
 *   g f  → ir a Reportes financieros
 *
 * Atajos directos:
 *   ?    → mostrar lista de atajos
 *   /    → focus en buscar (sidebar) o abrir global search ⌘K
 *   n    → Nuevo pedido
 *   N    → Nuevo producto
 *   .    → abrir FAB de acciones rápidas
 *   Esc  → cerrar overlay de atajos
 *
 * No se activan si estás escribiendo en input/textarea/select.
 */
(function() {
    if (!location.pathname.startsWith("/jheliz-admin")) return;

    const ROUTES = {
        "go o": "/jheliz-admin/orders/order/",
        "go s": "/jheliz-admin/stock/",
        "go r": "/jheliz-admin/renewals/",
        "go c": "/jheliz-admin/accounts/user/",
        "go d": "/jheliz-admin/",
        "go t": "/jheliz-admin/support/ticket/",
        "go f": "/jheliz-admin/reports/",
    };

    const css = `
        .jh-shortcut-overlay {
            position: fixed; inset: 0; z-index: 10001;
            background: rgba(0,0,0,0.6); backdrop-filter: blur(6px);
            display: flex; align-items: center; justify-content: center;
            opacity: 0; pointer-events: none; transition: opacity .15s ease;
            font-family: ui-sans-serif, system-ui, sans-serif;
        }
        .jh-shortcut-overlay.show { opacity: 1; pointer-events: auto; }
        .jh-shortcut-card {
            background: #0f172a; color: #fff;
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 16px;
            padding: 24px 28px;
            min-width: 360px; max-width: 92vw;
            box-shadow: 0 20px 50px -10px rgba(0,0,0,0.6);
        }
        .jh-shortcut-card h2 {
            font-size: 16px; font-weight: 700; margin: 0 0 4px 0;
            color: #f9a8d4;
        }
        .jh-shortcut-card p { color: #94a3b8; font-size: 12px; margin: 0 0 16px; }
        .jh-shortcut-card section { margin-bottom: 14px; }
        .jh-shortcut-card section:last-child { margin-bottom: 0; }
        .jh-shortcut-card section h3 {
            font-size: 11px; text-transform: uppercase; letter-spacing: .08em;
            color: #cbd5e1; margin: 0 0 8px 0;
        }
        .jh-shortcut-list {
            display: grid; grid-template-columns: 1fr 1fr; gap: 8px 16px;
        }
        .jh-shortcut-row {
            display: flex; align-items: center; justify-content: space-between;
            font-size: 13px; padding: 6px 0;
        }
        .jh-shortcut-keys { display: flex; gap: 4px; }
        .jh-shortcut-keys kbd {
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.15);
            border-bottom-width: 2px;
            border-radius: 6px;
            padding: 2px 8px;
            font-size: 11px; font-family: ui-monospace, SFMono-Regular, monospace;
            min-width: 22px; text-align: center; color: #fff;
        }
        .jh-shortcut-hint {
            position: fixed; bottom: 14px; left: 14px;
            background: rgba(15,23,42,0.85);
            color: #cbd5e1; font-size: 11px;
            padding: 6px 10px; border-radius: 9999px;
            border: 1px solid rgba(255,255,255,0.08);
            z-index: 70; pointer-events: none;
            font-family: ui-sans-serif, system-ui, sans-serif;
        }
        .jh-shortcut-hint kbd {
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 4px;
            padding: 1px 5px;
            font-size: 10px; margin: 0 2px;
            color: #fff;
        }
    `;

    function isTyping(e) {
        const el = e.target;
        if (!el) return false;
        const tag = (el.tagName || "").toUpperCase();
        if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
        if (el.isContentEditable) return true;
        return false;
    }

    let pendingPrefix = null;
    let prefixTimer = null;

    function clearPrefix() {
        pendingPrefix = null;
        if (prefixTimer) { clearTimeout(prefixTimer); prefixTimer = null; }
    }

    function setPrefix(p) {
        pendingPrefix = p;
        if (prefixTimer) clearTimeout(prefixTimer);
        prefixTimer = setTimeout(clearPrefix, 1500);
    }

    function showOverlay() {
        const ov = ensureOverlay();
        ov.classList.add("show");
    }
    function hideOverlay() {
        const ov = document.querySelector(".jh-shortcut-overlay");
        if (ov) ov.classList.remove("show");
    }

    function ensureOverlay() {
        let ov = document.querySelector(".jh-shortcut-overlay");
        if (ov) return ov;
        ov = document.createElement("div");
        ov.className = "jh-shortcut-overlay";
        ov.innerHTML = `
            <div class="jh-shortcut-card">
                <h2>Atajos de teclado</h2>
                <p>Acelera tu trabajo en el panel sin levantar las manos del teclado.</p>
                <section>
                    <h3>Ir a…</h3>
                    <div class="jh-shortcut-list">
                        <div class="jh-shortcut-row"><span>Dashboard</span><span class="jh-shortcut-keys"><kbd>g</kbd><kbd>d</kbd></span></div>
                        <div class="jh-shortcut-row"><span>Pedidos</span><span class="jh-shortcut-keys"><kbd>g</kbd><kbd>o</kbd></span></div>
                        <div class="jh-shortcut-row"><span>Stock por producto</span><span class="jh-shortcut-keys"><kbd>g</kbd><kbd>s</kbd></span></div>
                        <div class="jh-shortcut-row"><span>Renovaciones</span><span class="jh-shortcut-keys"><kbd>g</kbd><kbd>r</kbd></span></div>
                        <div class="jh-shortcut-row"><span>Clientes</span><span class="jh-shortcut-keys"><kbd>g</kbd><kbd>c</kbd></span></div>
                        <div class="jh-shortcut-row"><span>Tickets</span><span class="jh-shortcut-keys"><kbd>g</kbd><kbd>t</kbd></span></div>
                        <div class="jh-shortcut-row"><span>Reportes</span><span class="jh-shortcut-keys"><kbd>g</kbd><kbd>f</kbd></span></div>
                    </div>
                </section>
                <section>
                    <h3>Acciones</h3>
                    <div class="jh-shortcut-list">
                        <div class="jh-shortcut-row"><span>Buscar (Cmd+K)</span><span class="jh-shortcut-keys"><kbd>/</kbd></span></div>
                        <div class="jh-shortcut-row"><span>Acciones rápidas (FAB)</span><span class="jh-shortcut-keys"><kbd>.</kbd></span></div>
                        <div class="jh-shortcut-row"><span>Nuevo pedido</span><span class="jh-shortcut-keys"><kbd>n</kbd></span></div>
                        <div class="jh-shortcut-row"><span>Nuevo producto</span><span class="jh-shortcut-keys"><kbd>shift</kbd><kbd>N</kbd></span></div>
                        <div class="jh-shortcut-row"><span>Mostrar atajos</span><span class="jh-shortcut-keys"><kbd>?</kbd></span></div>
                        <div class="jh-shortcut-row"><span>Cerrar</span><span class="jh-shortcut-keys"><kbd>Esc</kbd></span></div>
                    </div>
                </section>
            </div>
        `;
        ov.addEventListener("click", function(e) {
            if (e.target === ov) hideOverlay();
        });
        document.body.appendChild(ov);
        return ov;
    }

    function init() {
        const style = document.createElement("style");
        style.textContent = css;
        document.head.appendChild(style);

        // Hint en la esquina (solo desktop, una vez por sesión)
        if (window.innerWidth > 900 && !sessionStorage.getItem("jh_shortcut_hint_dismissed")) {
            const hint = document.createElement("div");
            hint.className = "jh-shortcut-hint";
            hint.innerHTML = "Pulsa <kbd>?</kbd> para ver atajos de teclado";
            document.body.appendChild(hint);
            setTimeout(() => {
                hint.style.transition = "opacity .5s ease";
                hint.style.opacity = "0";
                setTimeout(() => hint.remove(), 700);
            }, 8000);
            sessionStorage.setItem("jh_shortcut_hint_dismissed", "1");
        }

        document.addEventListener("keydown", function(e) {
            // Permite Esc siempre (incluso si overlay está abierto)
            if (e.key === "Escape") {
                if (document.querySelector(".jh-shortcut-overlay.show")) {
                    hideOverlay();
                    e.preventDefault();
                }
                clearPrefix();
                return;
            }
            if (isTyping(e)) return;
            if (e.metaKey || e.ctrlKey || e.altKey) return;

            // Sequencias g + X
            if (pendingPrefix === "go") {
                const route = ROUTES["go " + e.key];
                if (route) {
                    location.assign(route);
                    e.preventDefault();
                }
                clearPrefix();
                return;
            }

            if (e.key === "g") {
                setPrefix("go");
                return;
            }

            // Atajos directos
            switch (e.key) {
                case "?":
                    showOverlay();
                    e.preventDefault();
                    break;
                case "/":
                    if (window.openGlobalSearch) {
                        window.openGlobalSearch();
                        e.preventDefault();
                    } else {
                        const search = document.querySelector('input[type="search"]');
                        if (search) {
                            search.focus();
                            e.preventDefault();
                        }
                    }
                    break;
                case ".":
                    document.querySelector(".jh-fab-button")?.click();
                    e.preventDefault();
                    break;
                case "n":
                    location.assign("/jheliz-admin/orders/order/add/");
                    e.preventDefault();
                    break;
                case "N":
                    location.assign("/jheliz-admin/catalog/product/add/");
                    e.preventDefault();
                    break;
            }
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
