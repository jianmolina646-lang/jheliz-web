/**
 * Bell de notificaciones del admin (visible en TODAS las páginas).
 *
 * Hace polling al endpoint JSON `/jheliz-admin/notifications/count.json` cada
 * 30s y mantiene una lista compartida de pendientes (Yape por aprobar, pedidos
 * en preparación, tickets abiertos). Al detectar un item nuevo (no visto antes
 * por este browser), muestra un badge rojo + opcionalmente un beep y una
 * notificación nativa del SO.
 *
 * El "ya visto" se persiste en localStorage como un Set de IDs.
 */
(function () {
    "use strict";

    if (window.__jhelizBellMounted) return; // evita doble montaje
    window.__jhelizBellMounted = true;

    var POLL_MS = 30000;
    var ENDPOINT = "/jheliz-admin/notifications/count.json";
    var SEEN_KEY = "jheliz_admin_seen_notif_ids";
    var SEEN_MAX = 200; // evita que el storage crezca indefinidamente

    // ----- helpers -----
    function el(tag, attrs, children) {
        var node = document.createElement(tag);
        if (attrs) {
            Object.keys(attrs).forEach(function (k) {
                if (k === "className") node.className = attrs[k];
                else if (k === "text") node.textContent = attrs[k];
                else if (k === "html") node.innerHTML = attrs[k];
                else if (k.indexOf("on") === 0 && typeof attrs[k] === "function") {
                    node.addEventListener(k.slice(2).toLowerCase(), attrs[k]);
                } else {
                    node.setAttribute(k, attrs[k]);
                }
            });
        }
        if (children) {
            (Array.isArray(children) ? children : [children]).forEach(function (c) {
                if (c == null) return;
                node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
            });
        }
        return node;
    }

    function loadSeenIds() {
        try {
            var raw = localStorage.getItem(SEEN_KEY);
            return raw ? new Set(JSON.parse(raw)) : new Set();
        } catch (_) {
            return new Set();
        }
    }

    function saveSeenIds(set) {
        try {
            var arr = Array.from(set);
            if (arr.length > SEEN_MAX) arr = arr.slice(arr.length - SEEN_MAX);
            localStorage.setItem(SEEN_KEY, JSON.stringify(arr));
        } catch (_) { /* quota / privado */ }
    }

    function playBeep() {
        try {
            var ctx = window.__jhelizAudioCtx || new (window.AudioContext || window.webkitAudioContext)();
            window.__jhelizAudioCtx = ctx;
            var osc = ctx.createOscillator();
            var gain = ctx.createGain();
            osc.type = "sine";
            osc.frequency.setValueAtTime(880, ctx.currentTime);
            osc.frequency.exponentialRampToValueAtTime(440, ctx.currentTime + 0.18);
            gain.gain.setValueAtTime(0.0001, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.18, ctx.currentTime + 0.02);
            gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.22);
            osc.connect(gain).connect(ctx.destination);
            osc.start();
            osc.stop(ctx.currentTime + 0.25);
        } catch (_) { /* contexts requieren gesto del usuario en algunos browsers */ }
    }

    function nativeNotify(title, body) {
        if (!("Notification" in window)) return;
        if (Notification.permission !== "granted") return;
        try {
            new Notification(title, { body: body, icon: "/manifest-icon.png", tag: "jheliz-admin" });
        } catch (_) { /* iOS Safari no implementa */ }
    }

    // ----- DOM mount -----
    var bell, badge, panel, list, emptyState, footerLink;

    function buildShell() {
        bell = el("button", {
            id: "jheliz-bell",
            "aria-label": "Notificaciones",
            "aria-haspopup": "dialog",
            "aria-expanded": "false",
            type: "button",
            className: "jheliz-bell-button",
        }, [
            el("span", { className: "material-symbols-outlined", text: "notifications" }),
            el("span", { id: "jheliz-bell-badge", className: "jheliz-bell-badge hidden", text: "0" }),
        ]);

        list = el("ul", { id: "jheliz-bell-list", className: "jheliz-bell-list", role: "list" });
        emptyState = el("div", {
            id: "jheliz-bell-empty",
            className: "jheliz-bell-empty",
            text: "Sin pendientes. Todo en orden.",
        });
        footerLink = el("a", {
            href: "/jheliz-admin/orders/order/?status__exact=verifying",
            className: "jheliz-bell-footer-link",
            text: "Ver todos los Yape pendientes",
        });

        panel = el("div", {
            id: "jheliz-bell-panel",
            role: "dialog",
            "aria-label": "Lista de notificaciones",
            className: "jheliz-bell-panel hidden",
        }, [
            el("header", { className: "jheliz-bell-header" }, [
                el("strong", { text: "Notificaciones" }),
                el("button", {
                    type: "button",
                    "aria-label": "Cerrar",
                    className: "jheliz-bell-close",
                    onclick: function () { setOpen(false); },
                    text: "✕",
                }),
            ]),
            list,
            emptyState,
            el("footer", { className: "jheliz-bell-footer" }, [footerLink]),
        ]);

        bell.addEventListener("click", function (e) {
            e.stopPropagation();
            setOpen(panel.classList.contains("hidden"));
        });
        document.addEventListener("click", function (e) {
            if (!panel.classList.contains("hidden") && !panel.contains(e.target) && e.target !== bell && !bell.contains(e.target)) {
                setOpen(false);
            }
        });
        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape") setOpen(false);
        });

        document.body.appendChild(bell);
        document.body.appendChild(panel);
    }

    function setOpen(open) {
        bell.setAttribute("aria-expanded", open ? "true" : "false");
        panel.classList.toggle("hidden", !open);
        if (open) {
            // Marcar todo lo visible como visto (para que el badge baje al cerrar/refresh).
            markAllVisibleAsSeen();
            renderBadge(0);
        }
    }

    // ----- state + rendering -----
    var lastItems = [];
    var lastUnreadCount = 0;
    var firstFetch = true;

    function renderBadge(count) {
        if (!badge) badge = document.getElementById("jheliz-bell-badge");
        if (!badge) return;
        if (count > 0) {
            badge.textContent = count > 99 ? "99+" : String(count);
            badge.classList.remove("hidden");
            bell.classList.add("has-unread");
        } else {
            badge.classList.add("hidden");
            bell.classList.remove("has-unread");
        }
    }

    function renderList(items, seenIds) {
        list.innerHTML = "";
        if (!items.length) {
            list.classList.add("hidden");
            emptyState.classList.remove("hidden");
            return;
        }
        list.classList.remove("hidden");
        emptyState.classList.add("hidden");

        items.forEach(function (it) {
            var isNew = !seenIds.has(it.id);
            var icon = el("span", {
                className: "material-symbols-outlined jheliz-bell-item-icon kind-" + (it.kind || "default"),
                text: it.icon || "circle_notifications",
            });
            var titleEl = el("div", { className: "jheliz-bell-item-title", text: it.title || "" });
            var subtitleEl = el("div", { className: "jheliz-bell-item-subtitle", text: it.subtitle || "" });
            var when = el("div", { className: "jheliz-bell-item-when", text: it.relative || "" });
            var body = el("div", { className: "jheliz-bell-item-body" }, [titleEl, subtitleEl, when]);
            var link = el("a", {
                href: it.url || "#",
                className: "jheliz-bell-item-link",
                onclick: function () {
                    seenIds.add(it.id);
                    saveSeenIds(seenIds);
                },
            }, [icon, body]);
            if (isNew) link.classList.add("is-new");
            var li = el("li", { className: "jheliz-bell-item", "data-id": it.id }, [link]);
            list.appendChild(li);
        });
    }

    function markAllVisibleAsSeen() {
        var seen = loadSeenIds();
        lastItems.forEach(function (it) { seen.add(it.id); });
        saveSeenIds(seen);
    }

    function tick() {
        fetch(ENDPOINT, { credentials: "same-origin", headers: { Accept: "application/json" } })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (data) {
                if (!data) return;
                var items = Array.isArray(data.items) ? data.items : [];
                var seen = loadSeenIds();
                var unseen = items.filter(function (it) { return !seen.has(it.id); });

                renderList(items, seen);
                renderBadge(unseen.length);
                lastItems = items;

                // Si subió la cantidad de no-vistos respecto del último tick (y no es el primer
                // fetch al abrir la página), hacemos beep + native notification.
                if (!firstFetch && unseen.length > lastUnreadCount) {
                    var diff = unseen.length - lastUnreadCount;
                    playBeep();
                    var top = unseen[0];
                    nativeNotify(
                        diff === 1 ? "Jheliz · 1 nueva notificación" : "Jheliz · " + diff + " nuevas",
                        top ? top.title : "Hay actividad nueva en el panel.",
                    );
                }
                lastUnreadCount = unseen.length;
                firstFetch = false;
            })
            .catch(function () { /* silencioso, no es bloqueante */ });
    }

    // ----- entry -----
    function init() {
        if (!document.body) return;
        // Sólo monta dentro del admin (rutas que arrancan con /jheliz-admin/).
        // Evita que toque la web pública si el script se incluye por error.
        if (location.pathname.indexOf("/jheliz-admin/") !== 0) return;

        buildShell();

        // Pide permiso de notificaciones la primera vez que el usuario hace cualquier click.
        if ("Notification" in window && Notification.permission === "default") {
            document.addEventListener("click", function once() {
                try { Notification.requestPermission(); } catch (_) {}
                document.removeEventListener("click", once);
            }, { once: true });
        }

        tick();
        setInterval(tick, POLL_MS);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
