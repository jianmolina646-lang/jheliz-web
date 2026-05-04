/* Modern 2026 polish — interactions
 * - Scroll reveal (IntersectionObserver)
 * - Sticky header glass on scroll
 * - 3D tilt on product cards (mouse only)
 * - Stat counter on viewport entry
 *
 * No external deps. Idempotent — safe to load once on every page.
 */
(function () {
  'use strict';

  if (window.__j2026Init) return;
  window.__j2026Init = true;

  var prefersReduced = false;
  try {
    prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  } catch (e) { /* noop */ }

  /* ---------- 1. Scroll reveal ---------- */
  function initReveal() {
    var els = document.querySelectorAll('.reveal-up, .reveal-stagger');
    if (!els.length) return;
    if (prefersReduced || !('IntersectionObserver' in window)) {
      els.forEach(function (el) { el.classList.add('is-visible'); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -60px 0px' });
    els.forEach(function (el) { io.observe(el); });
  }

  /* ---------- 2. Header glass on scroll ---------- */
  function initHeaderScroll() {
    var lastY = -1;
    function onScroll() {
      var y = window.scrollY || window.pageYOffset || 0;
      if (y > 12 && lastY <= 12) document.body.classList.add('is-scrolled');
      else if (y <= 12 && lastY > 12) document.body.classList.remove('is-scrolled');
      lastY = y;
    }
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
  }

  /* ---------- 3. 3D tilt on product cards ---------- */
  function initTilt() {
    if (prefersReduced) return;
    var coarse = false;
    try { coarse = window.matchMedia('(pointer: coarse)').matches; } catch (e) {}
    if (coarse) return;

    var cards = document.querySelectorAll('.product-card.j2026-tilt');
    cards.forEach(function (card) {
      var raf = 0;
      var rect = null;
      function recalc() { rect = card.getBoundingClientRect(); }
      card.addEventListener('mouseenter', recalc);
      window.addEventListener('resize', recalc, { passive: true });

      card.addEventListener('mousemove', function (ev) {
        if (!rect) recalc();
        if (raf) return;
        raf = requestAnimationFrame(function () {
          raf = 0;
          var x = ev.clientX - rect.left;
          var y = ev.clientY - rect.top;
          var px = x / rect.width;
          var py = y / rect.height;
          var rx = (py - 0.5) * -7;   // tilt x  (degrees)
          var ry = (px - 0.5) *  7;   // tilt y
          card.style.setProperty('--tx', ry.toFixed(2) + 'deg');
          card.style.setProperty('--ty', rx.toFixed(2) + 'deg');
          card.style.setProperty('--gx', (px * 100).toFixed(1) + '%');
          card.style.setProperty('--gy', (py * 100).toFixed(1) + '%');
        });
      }, { passive: true });

      card.addEventListener('mouseleave', function () {
        card.style.setProperty('--tx', '0deg');
        card.style.setProperty('--ty', '0deg');
      });
    });
  }

  /* ---------- 4. Stat counter on view ---------- */
  function parseStat(text) {
    if (!text) return null;
    var m = String(text).match(/([+~]?)(\d[\d.,]*)([^\d]*)$/);
    if (!m) return null;
    var num = parseFloat(m[2].replace(/[,]/g, ''));
    if (isNaN(num)) return null;
    return { prefix: m[1] || '', value: num, suffix: m[3] || '', raw: text };
  }

  function animateNumber(el, info) {
    var duration = 1100;
    var start = performance.now();
    var startVal = 0;
    var endVal = info.value;
    var hasDecimal = String(info.value).indexOf('.') >= 0;
    function frame(now) {
      var t = Math.min(1, (now - start) / duration);
      // ease-out cubic
      var eased = 1 - Math.pow(1 - t, 3);
      var cur = startVal + (endVal - startVal) * eased;
      var formatted;
      if (hasDecimal) {
        formatted = cur.toFixed(1);
      } else if (endVal >= 1000) {
        formatted = Math.round(cur).toLocaleString('es-PE');
      } else {
        formatted = Math.round(cur).toString();
      }
      el.textContent = info.prefix + formatted + info.suffix;
      if (t < 1) requestAnimationFrame(frame);
      else el.textContent = info.raw;
    }
    requestAnimationFrame(frame);
  }

  function initCounters() {
    if (prefersReduced || !('IntersectionObserver' in window)) return;
    var nodes = document.querySelectorAll('[data-counter]');
    if (!nodes.length) return;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        var el = entry.target;
        var info = parseStat(el.textContent.trim());
        if (info) animateNumber(el, info);
        io.unobserve(el);
      });
    }, { threshold: 0.5 });
    nodes.forEach(function (el) { io.observe(el); });
  }

  function init() {
    initReveal();
    initHeaderScroll();
    initTilt();
    initCounters();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
