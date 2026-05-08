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
        // Overlay con blur de fondo y fade-in.
        ".jh-cmd-overlay{position:fixed;inset:0;background:rgba(8,7,15,.72);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);z-index:99998;display:none;align-items:flex-start;justify-content:center;padding-top:14vh;animation:jhCmdFadeIn .18s ease-out}" +
        ".jh-cmd-overlay.open{display:flex}" +
        "@keyframes jhCmdFadeIn{from{opacity:0}to{opacity:1}}" +
        "@keyframes jhCmdSlideUp{from{transform:translateY(18px) scale(.97);opacity:0}to{transform:translateY(0) scale(1);opacity:1}}" +
        // Modal: glassmorphism + gradient ring + shadow rosado sutil.
        ".jh-cmd-modal{width:min(680px,94vw);background:linear-gradient(180deg,#13111c,#0a0810);border:1px solid rgba(244,114,182,.18);border-radius:18px;box-shadow:0 30px 80px rgba(0,0,0,.55),0 0 0 1px rgba(255,255,255,.03) inset,0 0 60px -20px rgba(244,114,182,.35);overflow:hidden;color:#e5e7eb;font-family:Inter,system-ui,sans-serif;animation:jhCmdSlideUp .22s cubic-bezier(.16,1,.3,1)}" +
        // Input grande con icono lupa.
        ".jh-cmd-input-wrap{position:relative;border-bottom:1px solid rgba(255,255,255,.06)}" +
        ".jh-cmd-input-wrap::before{content:'';position:absolute;left:20px;top:50%;width:18px;height:18px;transform:translateY(-50%);background-image:url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' fill='none' stroke='%23a1a1aa' stroke-width='2' viewBox='0 0 24 24' stroke-linecap='round' stroke-linejoin='round'><circle cx='11' cy='11' r='8'/><path d='m21 21-4.3-4.3'/></svg>\");background-size:contain;background-repeat:no-repeat;pointer-events:none;opacity:.7}" +
        ".jh-cmd-input{width:100%;padding:18px 18px 18px 50px;background:transparent;border:0;color:#fff;font-size:17px;font-weight:500;outline:none;letter-spacing:-.01em}" +
        ".jh-cmd-input::placeholder{color:#71717a}" +
        // Results.
        ".jh-cmd-results{max-height:62vh;overflow:auto;padding:8px 0;scrollbar-width:thin;scrollbar-color:#3f3f46 transparent}" +
        ".jh-cmd-results::-webkit-scrollbar{width:6px}" +
        ".jh-cmd-results::-webkit-scrollbar-thumb{background:#3f3f46;border-radius:3px}" +
        ".jh-cmd-section{padding:10px 18px 6px;font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#71717a;font-weight:700;display:flex;align-items:center;gap:6px}" +
        ".jh-cmd-section::after{content:'';flex:1;height:1px;background:rgba(255,255,255,.05);margin-left:8px}" +
        // Item: padding generoso, bordes redondeados al hover, label más grande.
        ".jh-cmd-item{display:flex;align-items:center;gap:12px;padding:11px 14px;margin:1px 8px;color:#e5e7eb;text-decoration:none;border-radius:10px;cursor:pointer;transition:background 120ms ease,transform 120ms ease;font-size:14px}" +
        ".jh-cmd-item:hover,.jh-cmd-item.active{background:linear-gradient(135deg,rgba(236,72,153,.16),rgba(168,85,247,.10));transform:translateX(2px)}" +
        ".jh-cmd-item.active{box-shadow:0 0 0 1px rgba(236,72,153,.28) inset}" +
        ".jh-cmd-item__label{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:500}" +
        ".jh-cmd-item__sub{font-size:12px;color:#a1a1aa;font-weight:400;margin-left:4px}" +
        ".jh-cmd-item .jh-cmd-meta{font-size:11px;color:#71717a;margin-left:auto;font-weight:500;letter-spacing:.02em}" +
        ".jh-cmd-item__arrow{opacity:0;color:#ec4899;transition:opacity 120ms ease}" +
        ".jh-cmd-item:hover .jh-cmd-item__arrow,.jh-cmd-item.active .jh-cmd-item__arrow{opacity:1}" +
        ".jh-cmd-empty{padding:22px 18px;color:#a1a1aa;font-size:13px;text-align:center}" +
        ".jh-cmd-empty__icon{font-size:32px;display:block;margin-bottom:8px;opacity:.5}" +
        // Hint footer.
        ".jh-cmd-hint{padding:10px 16px;border-top:1px solid rgba(255,255,255,.06);background:rgba(255,255,255,.015);color:#a1a1aa;font-size:11px;display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap}" +
        ".jh-cmd-hint__group{display:inline-flex;align-items:center;gap:8px}" +
        ".jh-cmd-kbd{display:inline-flex;align-items:center;justify-content:center;min-width:18px;padding:2px 6px;border:1px solid rgba(255,255,255,.10);border-radius:5px;background:rgba(255,255,255,.04);font-family:ui-monospace,monospace;font-size:10px;font-weight:600;color:#d4d4d8;box-shadow:0 1px 0 rgba(0,0,0,.2)}"
    );
    document.head.appendChild(styles);

    var overlay = document.createElement("div");
    overlay.className = "jh-cmd-overlay";
    overlay.innerHTML = (
        '<div class="jh-cmd-modal" role="dialog" aria-label="Búsqueda global">' +
        '  <div class="jh-cmd-input-wrap">' +
        '    <input class="jh-cmd-input" type="text" placeholder="Buscar pedido, cliente, producto, plan o ticket…" autocomplete="off" />' +
        '  </div>' +
        '  <div class="jh-cmd-results" role="listbox"></div>' +
        '  <div class="jh-cmd-hint">' +
        '    <span class="jh-cmd-hint__group"><span class="jh-cmd-kbd">↑</span><span class="jh-cmd-kbd">↓</span> navegar</span>' +
        '    <span class="jh-cmd-hint__group"><span class="jh-cmd-kbd">↵</span> abrir</span>' +
        '    <span class="jh-cmd-hint__group"><span class="jh-cmd-kbd">Esc</span> cerrar</span>' +
        '    <span class="jh-cmd-hint__group" style="margin-left:auto"><span class="jh-cmd-kbd">Ctrl</span><span class="jh-cmd-kbd">K</span></span>' +
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
        html += '<div class="jh-cmd-empty" style="padding:14px 16px 18px;"><span class="jh-cmd-empty__icon">⌨️</span>Escribe para buscar pedidos, clientes, productos, planes o tickets</div>';
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
            html = '<div class="jh-cmd-empty"><span class="jh-cmd-empty__icon">🔍</span>Sin resultados para "' + escapeHtml(input.value) + '"</div>';
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
