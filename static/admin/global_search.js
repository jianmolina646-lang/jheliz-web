/**
 * Global search (Cmd+K / Ctrl+K) para el admin.
 *
 * Inserta un modal en cualquier página del admin. El usuario presiona
 * Ctrl+K (o Cmd+K en Mac) y aparece un input. Al escribir, hace fetch
 * al endpoint /jheliz-admin/search/?q=... que devuelve JSON con orders,
 * products, customers, plans y tickets. Click en un resultado abre la
 * página de edición correspondiente.
 */
(function(){
    if(window.__jhelizGlobalSearchInstalled) return;
    window.__jhelizGlobalSearchInstalled = true;

    var API_URL = "/jheliz-admin/search/";

    var styles = document.createElement("style");
    styles.textContent = (
        ".jh-cmd-overlay{position:fixed;inset:0;background:rgba(0,0,0,.65);z-index:99998;display:none;align-items:flex-start;justify-content:center;padding-top:8vh}" +
        ".jh-cmd-overlay.open{display:flex}" +
        ".jh-cmd-modal{width:min(640px,92vw);background:#0f172a;border:1px solid #1f2937;border-radius:12px;box-shadow:0 20px 60px rgba(0,0,0,.5);overflow:hidden;color:#e5e7eb;font-family:Inter,system-ui,sans-serif}" +
        ".jh-cmd-input{width:100%;padding:14px 18px;background:transparent;border:0;border-bottom:1px solid #1f2937;color:#fff;font-size:15px;outline:none}" +
        ".jh-cmd-input::placeholder{color:#64748b}" +
        ".jh-cmd-results{max-height:60vh;overflow:auto;padding:6px 0}" +
        ".jh-cmd-section{padding:6px 16px;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#64748b;font-weight:600;margin-top:6px}" +
        ".jh-cmd-item{display:flex;align-items:center;gap:10px;padding:10px 16px;color:#e5e7eb;text-decoration:none;border-left:2px solid transparent;cursor:pointer}" +
        ".jh-cmd-item:hover,.jh-cmd-item.active{background:rgba(244,114,182,.10);border-left-color:#f472b6}" +
        ".jh-cmd-item .jh-cmd-meta{font-size:11px;color:#64748b;margin-left:auto}" +
        ".jh-cmd-empty{padding:18px 16px;color:#94a3b8;font-size:13px}" +
        ".jh-cmd-hint{padding:8px 16px;border-top:1px solid #1f2937;color:#64748b;font-size:11px;display:flex;justify-content:space-between}" +
        ".jh-cmd-kbd{display:inline-block;padding:1px 6px;border:1px solid #334155;border-radius:4px;background:#1e293b;font-family:ui-monospace,monospace;font-size:10px}"
    );
    document.head.appendChild(styles);

    var overlay = document.createElement("div");
    overlay.className = "jh-cmd-overlay";
    overlay.innerHTML = (
        '<div class="jh-cmd-modal" role="dialog" aria-label="Búsqueda global">' +
        '  <input class="jh-cmd-input" type="text" placeholder="Buscar pedido, cliente, producto, plan o ticket... (Ctrl+K)" autocomplete="off" />' +
        '  <div class="jh-cmd-results" role="listbox"></div>' +
        '  <div class="jh-cmd-hint">' +
        '    <span><span class="jh-cmd-kbd">↑</span> <span class="jh-cmd-kbd">↓</span> navegar  <span class="jh-cmd-kbd">↵</span> abrir  <span class="jh-cmd-kbd">Esc</span> cerrar</span>' +
        '    <span class="jh-cmd-kbd">Ctrl+K</span>' +
        '  </div>' +
        '</div>'
    );
    document.body.appendChild(overlay);

    var input = overlay.querySelector(".jh-cmd-input");
    var results = overlay.querySelector(".jh-cmd-results");
    var modal = overlay.querySelector(".jh-cmd-modal");
    var activeIdx = -1;
    var currentItems = [];
    var debounceTimer = null;
    var lastQuery = "";

    // Quick actions estáticas que aparecen sin escribir nada o cuando el query
    // matchea por nombre. Permiten navegar a páginas custom del admin con 2 letras.
    var QUICK_ACTIONS = [
        { kw: "stock inventario",      label: "📦 Stock",                    url: "/jheliz-admin/stock/" },
        { kw: "renovacion vencer",     label: "🔁 Renovaciones pendientes",  url: "/jheliz-admin/renewals/" },
        { kw: "entrega lote bulk",     label: "⚡ Entrega en masa",          url: "/jheliz-admin/bulk-delivery/" },
        { kw: "reporte ventas",        label: "📊 Reportes financieros",     url: "/jheliz-admin/reports/" },
        { kw: "clientes top",          label: "⭐ Clientes valiosos",        url: "/jheliz-admin/top-customers/" },
        { kw: "cliente 360",           label: "👥 Buscar cliente",           url: "/jheliz-admin/customers/" },
        { kw: "salud health",          label: "❤️ Estado de servicios",     url: "/jheliz-admin/health/" },
        { kw: "yape inbox bandeja",    label: "💸 Bandeja Yape pendientes",  url: "/jheliz-admin/orders/order/yape-inbox/" },
        { kw: "pedido nuevo",          label: "➕ Crear pedido",             url: "/jheliz-admin/orders/order/add/" },
        { kw: "producto nuevo",        label: "➕ Crear producto",           url: "/jheliz-admin/catalog/product/add/" },
        { kw: "cupon descuento",       label: "🎟 Cupones",                  url: "/jheliz-admin/orders/coupon/" },
        { kw: "ticket soporte",        label: "💬 Tickets de soporte",       url: "/jheliz-admin/support/ticket/" },
        { kw: "codigo solicitud",      label: "🔑 Solicitudes de código",    url: "/jheliz-admin/support/coderequest/" },
        { kw: "plantilla respuesta",   label: "📝 Plantillas de respuesta",  url: "/jheliz-admin/support/replytemplate/" },
        { kw: "reseña review",         label: "⭐ Reseñas",                 url: "/jheliz-admin/catalog/productreview/" },
        { kw: "landing seo",           label: "🌐 Landing pages SEO",        url: "/jheliz-admin/catalog/platformlanding/" },
        { kw: "reemplazar bloqueada",  label: "🔄 Reemplazar cuenta",        url: "/jheliz-admin/replace-blocked-account/" },
    ];

    function filterQuickActions(q){
        if(!q) return QUICK_ACTIONS.slice(0, 8);
        var ql = q.toLowerCase();
        return QUICK_ACTIONS.filter(function(a){
            return a.kw.indexOf(ql) >= 0 || a.label.toLowerCase().indexOf(ql) >= 0;
        }).slice(0, 6);
    }

    function renderQuickActions(){
        var actions = filterQuickActions("");
        var html = '<div class="jh-cmd-section">Acciones rápidas</div>';
        currentItems = [];
        actions.forEach(function(a){
            currentItems.push({ url: a.url, label: a.label });
            var idx = currentItems.length - 1;
            html += (
                '<a class="jh-cmd-item" data-idx="' + idx + '" href="' + escapeHtml(a.url) + '">' +
                '  <span>' + escapeHtml(a.label) + '</span>' +
                '</a>'
            );
        });
        html += '<div class="jh-cmd-empty" style="padding:12px 16px 16px;">Escribe para buscar pedidos, clientes, productos…</div>';
        results.innerHTML = html;
    }

    function open(){
        overlay.classList.add("open");
        input.value = "";
        renderQuickActions();
        activeIdx = -1;
        setTimeout(function(){ input.focus(); }, 0);
    }

    function close(){
        overlay.classList.remove("open");
    }

    function escapeHtml(s){
        return String(s == null ? "" : s)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function renderResults(data){
        var html = "";
        currentItems = [];
        // Mezcla acciones rápidas que matcheen el query encima de los resultados.
        var q = input.value.trim();
        var matchedActions = filterQuickActions(q);
        if(matchedActions.length){
            html += '<div class="jh-cmd-section">Acciones rápidas</div>';
            matchedActions.forEach(function(a){
                currentItems.push({ url: a.url, label: a.label });
                var idx = currentItems.length - 1;
                html += (
                    '<a class="jh-cmd-item" data-idx="' + idx + '" href="' + escapeHtml(a.url) + '">' +
                    '  <span>' + escapeHtml(a.label) + '</span>' +
                    '</a>'
                );
            });
        }
        var sections = [
            ["orders", "Pedidos"],
            ["customers", "Clientes"],
            ["products", "Productos"],
            ["plans", "Planes"],
            ["tickets", "Tickets"],
        ];
        var any = matchedActions.length > 0;
        sections.forEach(function(pair){
            var key = pair[0], label = pair[1];
            var items = data[key] || [];
            if(!items.length) return;
            any = true;
            html += '<div class="jh-cmd-section">' + label + '</div>';
            items.forEach(function(it){
                currentItems.push(it);
                var idx = currentItems.length - 1;
                html += (
                    '<a class="jh-cmd-item" data-idx="' + idx + '" href="' + escapeHtml(it.url) + '">' +
                    '  <span>' + escapeHtml(it.label) + '</span>' +
                    (it.meta ? '  <span class="jh-cmd-meta">' + escapeHtml(it.meta) + '</span>' : '') +
                    '</a>'
                );
            });
        });
        if(!any){
            html = '<div class="jh-cmd-empty">Sin resultados.</div>';
        }
        // Footer: link a la página completa de resultados.
        if(q.length >= 2){
            html += (
                '<a class="jh-cmd-item jh-cmd-seeall" href="' + API_URL +
                '?full=1&q=' + encodeURIComponent(q) + '">' +
                '  <span>Ver todos los resultados para "' + escapeHtml(q) + '"</span>' +
                '  <span class="jh-cmd-meta">↵</span>' +
                '</a>'
            );
        }
        results.innerHTML = html;
        activeIdx = -1;
    }

    function search(q){
        if(q === lastQuery) return;
        lastQuery = q;
        if(q.length < 2){
            renderQuickActions();
            return;
        }
        fetch(API_URL + "?q=" + encodeURIComponent(q), { credentials: "same-origin" })
            .then(function(r){ return r.ok ? r.json() : null; })
            .then(function(d){
                if(d) renderResults(d);
            })
            .catch(function(){ /* silencioso */ });
    }

    function setActive(idx){
        var items = results.querySelectorAll(".jh-cmd-item");
        items.forEach(function(el, i){
            el.classList.toggle("active", i === idx);
            if(i === idx){
                el.scrollIntoView({ block: "nearest" });
            }
        });
        activeIdx = idx;
    }

    input.addEventListener("input", function(){
        var q = input.value.trim();
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(function(){ search(q); }, 200);
    });

    input.addEventListener("keydown", function(e){
        if(e.key === "Escape"){ close(); return; }
        if(e.key === "ArrowDown"){
            e.preventDefault();
            setActive(Math.min(activeIdx + 1, currentItems.length - 1));
        } else if(e.key === "ArrowUp"){
            e.preventDefault();
            setActive(Math.max(activeIdx - 1, 0));
        } else if(e.key === "Enter" && activeIdx >= 0){
            e.preventDefault();
            var item = currentItems[activeIdx];
            if(item) window.location.href = item.url;
        }
    });

    overlay.addEventListener("click", function(e){
        if(e.target === overlay) close();
    });

    document.addEventListener("keydown", function(e){
        var isMac = navigator.platform.toUpperCase().indexOf("MAC") >= 0;
        var modKey = isMac ? e.metaKey : e.ctrlKey;
        if(modKey && (e.key === "k" || e.key === "K")){
            e.preventDefault();
            if(overlay.classList.contains("open")) close();
            else open();
        }
    });

    // Click delegate so SPA-style item nav still works (in case href is set).
    results.addEventListener("click", function(e){
        var item = e.target.closest(".jh-cmd-item");
        if(item){
            var idx = parseInt(item.getAttribute("data-idx"), 10);
            if(currentItems[idx]){
                window.location.href = currentItems[idx].url;
            }
        }
    });
})();
