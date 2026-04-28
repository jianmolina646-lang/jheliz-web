/* Floating Action Button (FAB) — atajos rápidos para acciones frecuentes.
 *
 * Se inyecta automáticamente en cualquier página /jheliz-admin/* y muestra
 * un botón flotante abajo a la derecha que abre un menú con shortcuts.
 */
(function() {
    if (!location.pathname.startsWith("/jheliz-admin")) return;

    const ITEMS = [
        {
            label: "Nuevo pedido manual",
            icon: "add_shopping_cart",
            color: "#10b981",
            href: "/jheliz-admin/orders/order/add/",
        },
        {
            label: "Importar stock",
            icon: "inventory",
            color: "#f472b6",
            href: "/jheliz-admin/catalog/stockitem/importar/",
        },
        {
            label: "Stock por producto",
            icon: "grid_view",
            color: "#8b5cf6",
            href: "/jheliz-admin/stock/",
        },
        {
            label: "Renovaciones",
            icon: "autorenew",
            color: "#06b6d4",
            href: "/jheliz-admin/renewals/",
        },
        {
            label: "Reportes",
            icon: "monitoring",
            color: "#f59e0b",
            href: "/jheliz-admin/reports/",
        },
        {
            label: "Nuevo producto",
            icon: "add_box",
            color: "#ec4899",
            href: "/jheliz-admin/catalog/product/add/",
        },
        {
            label: "Buscar (⌘K)",
            icon: "search",
            color: "#94a3b8",
            action: () => {
                if (window.openGlobalSearch) window.openGlobalSearch();
                else document.querySelector('input[type="search"]')?.focus();
            },
        },
    ];

    const css = `
        .jh-fab-root {
            position: fixed; bottom: 24px; right: 24px; z-index: 9990;
            font-family: ui-sans-serif, system-ui, sans-serif;
        }
        .jh-fab-button {
            width: 56px; height: 56px; border-radius: 9999px;
            background: linear-gradient(135deg, #f472b6, #d946ef);
            color: white; font-size: 28px; line-height: 56px; text-align: center;
            box-shadow: 0 10px 25px -5px rgba(217,70,239,0.5),
                        0 4px 10px -2px rgba(0,0,0,0.3);
            cursor: pointer; user-select: none;
            transition: transform .2s ease, box-shadow .2s ease;
            border: none; padding: 0;
        }
        .jh-fab-button:hover { transform: scale(1.08); }
        .jh-fab-button.open { transform: rotate(45deg); }
        .jh-fab-menu {
            position: absolute; bottom: 70px; right: 0;
            display: flex; flex-direction: column-reverse; gap: 10px;
            opacity: 0; pointer-events: none; transform: translateY(6px);
            transition: opacity .15s ease, transform .15s ease;
        }
        .jh-fab-menu.open { opacity: 1; pointer-events: auto; transform: translateY(0); }
        .jh-fab-item {
            display: flex; align-items: center; gap: 10px;
            background: rgba(15,23,42,0.95);
            color: #fff; text-decoration: none;
            padding: 8px 14px 8px 8px;
            border-radius: 9999px;
            border: 1px solid rgba(255,255,255,0.08);
            box-shadow: 0 6px 16px -4px rgba(0,0,0,0.4);
            font-size: 13px; white-space: nowrap;
            backdrop-filter: blur(8px);
            transition: transform .15s ease, background .15s ease;
            cursor: pointer; font-weight: 500;
        }
        .jh-fab-item:hover {
            transform: translateX(-3px);
            background: rgba(30,41,59,0.95);
            color: #fff;
        }
        .jh-fab-item-icon {
            width: 32px; height: 32px; border-radius: 9999px;
            display: flex; align-items: center; justify-content: center;
            color: #fff; flex-shrink: 0;
        }
        .jh-fab-item-icon .material-symbols-outlined { font-size: 20px; }
        .jh-fab-backdrop {
            position: fixed; inset: 0; background: rgba(0,0,0,0.2);
            z-index: 9980; opacity: 0; pointer-events: none;
            transition: opacity .15s ease;
        }
        .jh-fab-backdrop.open { opacity: 1; pointer-events: auto; }
        @media (max-width: 640px) {
            .jh-fab-root { bottom: 16px; right: 16px; }
        }
    `;

    function init() {
        const style = document.createElement("style");
        style.textContent = css;
        document.head.appendChild(style);

        const root = document.createElement("div");
        root.className = "jh-fab-root";

        const backdrop = document.createElement("div");
        backdrop.className = "jh-fab-backdrop";
        document.body.appendChild(backdrop);

        const menu = document.createElement("div");
        menu.className = "jh-fab-menu";

        ITEMS.forEach(it => {
            const el = it.href
                ? document.createElement("a")
                : document.createElement("button");
            el.className = "jh-fab-item";
            if (it.href) el.href = it.href;
            el.innerHTML = `
                <span class="jh-fab-item-icon" style="background:${it.color}">
                    <span class="material-symbols-outlined">${it.icon}</span>
                </span>
                <span>${it.label}</span>
            `;
            if (it.action) {
                el.type = "button";
                el.addEventListener("click", (e) => {
                    e.preventDefault();
                    closeMenu();
                    setTimeout(() => it.action(), 100);
                });
            }
            menu.appendChild(el);
        });

        const btn = document.createElement("button");
        btn.className = "jh-fab-button";
        btn.type = "button";
        btn.title = "Acciones rápidas";
        btn.innerHTML = "+";

        function openMenu() {
            btn.classList.add("open");
            menu.classList.add("open");
            backdrop.classList.add("open");
        }
        function closeMenu() {
            btn.classList.remove("open");
            menu.classList.remove("open");
            backdrop.classList.remove("open");
        }
        function toggle() {
            menu.classList.contains("open") ? closeMenu() : openMenu();
        }

        btn.addEventListener("click", toggle);
        backdrop.addEventListener("click", closeMenu);
        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape") closeMenu();
        });

        root.appendChild(menu);
        root.appendChild(btn);
        document.body.appendChild(root);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
