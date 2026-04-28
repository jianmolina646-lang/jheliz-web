/**
 * Inserción de plantillas de respuesta en el admin de tickets (#13).
 *
 * Al cargar la página de edición de un ticket, busca los textarea con
 * id que termine en "-body" (los del inline de TicketMessage) y agrega
 * arriba un <select> con todas las plantillas activas. Al elegir una,
 * rellena el textarea con el body renderizado (variables sustituidas).
 */
(function(){
    if(window.__jhelizTicketTemplatesInstalled) return;
    window.__jhelizTicketTemplatesInstalled = true;

    // Detectar que estamos en la página de un ticket.
    var match = window.location.pathname.match(/\/jheliz-admin\/support\/ticket\/(\d+)\/change\/?$/);
    if(!match) return;
    var ticketId = match[1];

    var API_URL = "/jheliz-admin/reply-templates.json?ticket_id=" + encodeURIComponent(ticketId);

    function injectInto(textarea, templates){
        if(textarea.dataset.jhTemplatesAdded) return;
        textarea.dataset.jhTemplatesAdded = "1";

        var wrap = document.createElement("div");
        wrap.style.cssText = "margin-bottom:6px;display:flex;align-items:center;gap:6px;flex-wrap:wrap";

        var label = document.createElement("span");
        label.textContent = "Plantilla:";
        label.style.cssText = "font-size:12px;color:#94a3b8";

        var sel = document.createElement("select");
        sel.style.cssText = "padding:4px 8px;border-radius:6px;background:#0f172a;color:#e5e7eb;border:1px solid #334155;font-size:12px;max-width:320px";
        sel.innerHTML = '<option value="">— elegir plantilla —</option>';
        var groups = {};
        templates.forEach(function(t){
            (groups[t.category_label] = groups[t.category_label] || []).push(t);
        });
        Object.keys(groups).forEach(function(cat){
            var og = document.createElement("optgroup");
            og.label = cat;
            groups[cat].forEach(function(t){
                var opt = document.createElement("option");
                opt.value = t.id;
                opt.textContent = t.name;
                og.appendChild(opt);
            });
            sel.appendChild(og);
        });

        sel.addEventListener("change", function(){
            if(!sel.value) return;
            var t = templates.find(function(x){ return String(x.id) === sel.value; });
            if(!t) return;
            if(textarea.value && !confirm("¿Reemplazar el contenido actual con la plantilla?")){
                sel.value = "";
                return;
            }
            textarea.value = t.body_rendered;
            textarea.dispatchEvent(new Event("input", { bubbles: true }));
            textarea.focus();
            sel.value = "";
        });

        wrap.appendChild(label);
        wrap.appendChild(sel);
        textarea.parentNode.insertBefore(wrap, textarea);
    }

    function tryInject(templates){
        var textareas = document.querySelectorAll(
            'textarea[name$="-body"], textarea[id$="-body"]'
        );
        textareas.forEach(function(ta){ injectInto(ta, templates); });
    }

    document.addEventListener("DOMContentLoaded", function(){
        fetch(API_URL, { credentials: "same-origin" })
            .then(function(r){ return r.ok ? r.json() : null; })
            .then(function(data){
                if(!data || !data.templates || !data.templates.length) return;
                tryInject(data.templates);
                // Re-inyectar cuando se agreguen filas inline (Unfold/Django).
                var observer = new MutationObserver(function(){
                    tryInject(data.templates);
                });
                observer.observe(document.body, { childList: true, subtree: true });
            })
            .catch(function(){ /* silencioso */ });
    });
})();
