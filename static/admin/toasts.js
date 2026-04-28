/* Toasts modernos para mensajes Django.
 *
 * Detecta los mensajes que Django/Unfold inserta y los muestra como toasts
 * deslizándose desde la esquina inferior derecha en vez de banners arriba.
 * Mantiene los mensajes originales como fallback (solo los oculta visualmente).
 */
(function() {
    if (!location.pathname.startsWith("/jheliz-admin")) return;

    const css = `
        .jh-toast-stack {
            position: fixed; bottom: 24px; right: 24px;
            display: flex; flex-direction: column; gap: 10px;
            z-index: 10000; pointer-events: none;
            font-family: ui-sans-serif, system-ui, sans-serif;
        }
        .jh-toast {
            min-width: 280px; max-width: 420px;
            padding: 12px 16px;
            border-radius: 12px;
            background: rgba(15,23,42,0.96);
            color: #fff;
            box-shadow: 0 14px 30px -8px rgba(0,0,0,0.5),
                        0 4px 12px -2px rgba(0,0,0,0.3);
            border: 1px solid rgba(255,255,255,0.08);
            border-left: 4px solid #94a3b8;
            backdrop-filter: blur(8px);
            display: flex; align-items: flex-start; gap: 12px;
            opacity: 0; transform: translateX(20px);
            transition: opacity .25s ease, transform .25s ease;
            pointer-events: auto;
            font-size: 14px; line-height: 1.45;
        }
        .jh-toast.show { opacity: 1; transform: translateX(0); }
        .jh-toast.hide { opacity: 0; transform: translateX(20px); }
        .jh-toast.success { border-left-color: #10b981; }
        .jh-toast.error,
        .jh-toast.danger { border-left-color: #ef4444; }
        .jh-toast.warning { border-left-color: #f59e0b; }
        .jh-toast.info { border-left-color: #3b82f6; }
        .jh-toast-icon {
            display: flex; align-items: center; justify-content: center;
            width: 28px; height: 28px; border-radius: 9999px;
            flex-shrink: 0; color: #fff;
        }
        .jh-toast.success .jh-toast-icon { background: rgba(16,185,129,0.25); color: #6ee7b7; }
        .jh-toast.error  .jh-toast-icon,
        .jh-toast.danger .jh-toast-icon { background: rgba(239,68,68,0.25); color: #fca5a5; }
        .jh-toast.warning .jh-toast-icon { background: rgba(245,158,11,0.25); color: #fcd34d; }
        .jh-toast.info   .jh-toast-icon { background: rgba(59,130,246,0.25); color: #93c5fd; }
        .jh-toast-icon .material-symbols-outlined { font-size: 18px; font-weight: 700; }
        .jh-toast-body { flex: 1; }
        .jh-toast-close {
            background: none; border: none; color: rgba(255,255,255,0.5);
            cursor: pointer; padding: 0; font-size: 18px; line-height: 1;
            margin-left: 4px; align-self: flex-start;
        }
        .jh-toast-close:hover { color: #fff; }
        @media (max-width: 640px) {
            .jh-toast-stack { left: 12px; right: 12px; bottom: 12px; }
            .jh-toast { min-width: 0; }
        }
    `;

    const ICONS = {
        success: "check_circle",
        error: "error",
        danger: "error",
        warning: "warning",
        info: "info",
        debug: "info",
    };

    function ensureStack() {
        let stack = document.querySelector(".jh-toast-stack");
        if (!stack) {
            stack = document.createElement("div");
            stack.className = "jh-toast-stack";
            document.body.appendChild(stack);
        }
        return stack;
    }

    function show(level, text, opts) {
        opts = opts || {};
        const ms = opts.duration || 5000;
        const stack = ensureStack();
        const toast = document.createElement("div");
        toast.className = `jh-toast ${level}`;
        toast.innerHTML = `
            <span class="jh-toast-icon">
                <span class="material-symbols-outlined">${ICONS[level] || "info"}</span>
            </span>
            <div class="jh-toast-body"></div>
            <button type="button" class="jh-toast-close" aria-label="Cerrar">×</button>
        `;
        toast.querySelector(".jh-toast-body").textContent = text;
        stack.appendChild(toast);
        // Triple rAF for guaranteed layout-then-transition.
        requestAnimationFrame(() => requestAnimationFrame(() => {
            toast.classList.add("show");
        }));

        function dismiss() {
            toast.classList.remove("show");
            toast.classList.add("hide");
            setTimeout(() => toast.remove(), 300);
        }
        toast.querySelector(".jh-toast-close").addEventListener("click", dismiss);
        if (ms > 0) setTimeout(dismiss, ms);
    }

    // Expose a global helper so other scripts can trigger toasts directly.
    window.jhToast = show;

    function harvest() {
        const style = document.createElement("style");
        style.textContent = css;
        document.head.appendChild(style);

        // Unfold puts messages in `.unfold-messages` or `ul.messagelist`.
        const candidates = document.querySelectorAll(
            ".unfold-messages li, ul.messagelist li, .messagelist li"
        );
        candidates.forEach((li) => {
            // Map Django message tags (success/error/warning/info/debug) to level.
            const cls = (li.className || "").toLowerCase();
            let level = "info";
            ["success", "error", "danger", "warning", "info"].forEach((l) => {
                if (cls.indexOf(l) !== -1) level = l;
            });
            const text = (li.textContent || "").trim();
            if (text) show(level, text);
            li.style.display = "none";
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", harvest);
    } else {
        harvest();
    }
})();
