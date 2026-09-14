(() => {
  const app = document.querySelector('.mk-app');
  const store = document.getElementById('mk-store');
  const support = document.getElementById('mk-support');
  const frame = document.getElementById('mk-support-frame');
  if (!app || !store || !support || !frame) return;
  const summary = Array.from(store.parentElement.children).filter(el => el !== store && el !== support);
  const tabs = ['#resumen', '#tienda', '#soporte'];
  app.querySelectorAll('a').forEach(link => {
    if (link.pathname === new URL(frame.dataset.src, location.href).pathname) link.setAttribute('href', '#soporte');
    if (['/tienda/', '/distribuidor/catalogo/'].includes(link.pathname)) link.setAttribute('href', '#tienda');
  });
  function render() {
    const tab = tabs.includes(location.hash) ? location.hash : '#resumen';
    summary.forEach(el => el.hidden = tab !== '#resumen');
    store.hidden = tab !== '#tienda';
    support.hidden = tab !== '#soporte';
    if (tab === '#soporte' && !frame.hasAttribute('src')) frame.src = frame.dataset.src;
    app.querySelectorAll('.mk-side nav a').forEach(link => {
      const active = link.getAttribute('href') === tab;
      link.classList.toggle('active', active);
      if (active) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
  }
  app.addEventListener('click', event => {
    const link = event.target.closest('a');
    if (!link || !tabs.includes(link.getAttribute('href'))) return;
    event.preventDefault();
    const tab = link.getAttribute('href');
    if (location.hash !== tab) history.pushState(null, '', tab);
    render();
    window.scrollTo(0, 0);
  });
  frame.addEventListener('load', () => {
    try {
      frame.contentDocument.querySelectorAll('header.nav-glass, footer, .mk-side').forEach(el => el.hidden = true);
    } catch (_) { /* External error pages cannot be accessed. */ }
  });
  window.addEventListener('hashchange', render);
  window.addEventListener('popstate', render);
  render();
})();
