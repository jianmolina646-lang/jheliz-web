(() => {
  const app = document.querySelector('.mk-app');
  const store = document.getElementById('mk-store');
  const support = document.getElementById('mk-support');
  const content = document.getElementById('mk-support-content');
  const status = document.getElementById('mk-support-status');
  if (!app || !store || !support || !content) return;
  let loaded = false;
  let loading = false;
  let currentUrl = content.dataset.src;
  const supportPath = new URL(currentUrl, location.href).pathname;
  async function loadSupport(url, options = {}) {
    if (loading) return;
    loading = true;
    status.textContent = 'Cargando soporte…';
    content.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch(url, {credentials: 'same-origin', ...options});
      if (!response.ok) throw new Error('request');
      const destination = new URL(response.url);
      if (destination.origin !== location.origin || !destination.pathname.startsWith(supportPath)) throw new Error('session');
      const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
      const main = doc.querySelector('main');
      if (!main) throw new Error('content');
      main.querySelectorAll('script').forEach(el => el.remove());
      main.querySelectorAll('form').forEach(form => {
        if (!form.hasAttribute('action')) form.setAttribute('action', response.url);
        Array.from(form.attributes).filter(attr => attr.name.startsWith('hx-')).forEach(attr => form.removeAttribute(attr.name));
      });
      content.replaceChildren(...Array.from(main.childNodes));
      currentUrl = response.url;
      loaded = true;
      status.textContent = '';
      if (window.htmx) window.htmx.process(content);
    } catch (error) {
      status.textContent = error.message === 'session' ? 'Tu sesión expiró. Vuelve a ingresar para consultar tus tickets.' : 'No se pudo cargar soporte. Pulsa Soporte para reintentar. No se ha confirmado el envío; revisa tus tickets antes de reenviar.';
    } finally {
      loading = false;
      content.removeAttribute('aria-busy');
    }
  }
  const summary = Array.from(store.parentElement.children).filter(el => el !== store && el !== support);
  const tabs = ['#resumen', '#tienda', '#soporte'];
  const search = document.getElementById('ms-search');
  const rows = Array.from(app.querySelectorAll('.ms-table tbody tr'));
  let service = 'all';
  function filterStore() {
    const query = (search?.value || '').trim().toLocaleLowerCase();
    let count = 0;
    rows.forEach(row => {
      const visible = (service === 'all' || row.dataset.service === service) && row.dataset.search.toLocaleLowerCase().includes(query);
      row.hidden = !visible;
      if (visible) count++;
    });
    const empty = document.getElementById('ms-empty');
    if (empty) empty.hidden = count > 0;
  }
  search?.addEventListener('input', filterStore);
  app.querySelectorAll('.ms-filters button').forEach(button => button.addEventListener('click', () => {
    service = button.dataset.service;
    app.querySelectorAll('.ms-filters button').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    filterStore();
  }));
  filterStore();
  app.querySelectorAll('a').forEach(link => {
    if (link.pathname === supportPath) link.setAttribute('href', '#soporte');
    if (['/tienda/', '/distribuidor/catalogo/'].includes(link.pathname)) link.setAttribute('href', '#tienda');
  });
  function render() {
    const tab = tabs.includes(location.hash) ? location.hash : '#resumen';
    app.dataset.view = tab.slice(1);
    summary.forEach(el => el.hidden = tab !== '#resumen');
    store.hidden = tab !== '#tienda';
    support.hidden = tab !== '#soporte';
    if (tab === '#soporte' && !loaded) loadSupport(currentUrl);
    app.querySelectorAll('.mk-side nav a').forEach(link => {
      const active = link.getAttribute('href') === tab;
      link.classList.toggle('active', active);
      if (active) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
  }
  app.addEventListener('click', event => {
    const link = event.target.closest('a');
    if (link && content.contains(link) && link.origin === location.origin && link.pathname.startsWith(supportPath)) {
      event.preventDefault();
      loadSupport(link.href);
      return;
    }
    if (!link || !tabs.includes(link.getAttribute('href'))) return;
    event.preventDefault();
    const tab = link.getAttribute('href');
    if (location.hash !== tab) history.pushState(null, '', tab);
    render();
    window.scrollTo(0, 0);
  });
  content.addEventListener('submit', event => {
    event.preventDefault();
    const form = event.target;
    const target = new URL(form.action || currentUrl, location.href);
    if (target.origin !== location.origin || !target.pathname.startsWith(supportPath)) return;
    loadSupport(target.href, {method: 'POST', body: new FormData(form)});
  });
  window.addEventListener('hashchange', render);
  window.addEventListener('popstate', render);
  render();
})();
