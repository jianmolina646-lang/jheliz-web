/* Pack-Modern v1 — scroll reveal + number counter + subtle magnetic CTA */
(function () {
  'use strict';

  /* ---------------- Scroll reveal using IntersectionObserver ------- */
  function initScrollReveal() {
    var els = document.querySelectorAll('[data-reveal]');
    if (!els.length) return;
    if (!('IntersectionObserver' in window)) {
      // Fallback: just show them
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
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });
    els.forEach(function (el) { io.observe(el); });
  }

  /* ---------------- Animated number counter (data-counter) --------- */
  function animateCounter(el) {
    var target = parseFloat(el.getAttribute('data-counter')) || 0;
    var duration = parseInt(el.getAttribute('data-counter-duration') || '1400', 10);
    var suffix = el.getAttribute('data-counter-suffix') || '';
    var prefix = el.getAttribute('data-counter-prefix') || '';
    var decimals = parseInt(el.getAttribute('data-counter-decimals') || '0', 10);
    var start = performance.now();
    function tick(now) {
      var progress = Math.min(1, (now - start) / duration);
      var eased = 1 - Math.pow(1 - progress, 3);
      var val = target * eased;
      el.textContent = prefix + val.toFixed(decimals) + suffix;
      if (progress < 1) requestAnimationFrame(tick);
      else el.textContent = prefix + target.toFixed(decimals) + suffix;
    }
    requestAnimationFrame(tick);
  }

  function initCounters() {
    var counters = document.querySelectorAll('[data-counter]');
    if (!counters.length) return;
    if (!('IntersectionObserver' in window)) {
      counters.forEach(animateCounter);
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          animateCounter(entry.target);
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.35 });
    counters.forEach(function (c) { io.observe(c); });
  }

  /* ---------------- Tilt effect on product cards (subtle) --------- */
  function initCardTilt() {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    if (window.matchMedia('(hover: none)').matches) return; // skip on touch
    var cards = document.querySelectorAll('.product-card');
    cards.forEach(function (card) {
      var raf = null;
      card.addEventListener('mousemove', function (e) {
        if (raf) cancelAnimationFrame(raf);
        raf = requestAnimationFrame(function () {
          var r = card.getBoundingClientRect();
          var x = (e.clientX - r.left) / r.width - 0.5;
          var y = (e.clientY - r.top) / r.height - 0.5;
          card.style.transform =
            'translateY(-4px) rotateX(' + (-y * 2.2).toFixed(2) +
            'deg) rotateY(' + (x * 2.6).toFixed(2) + 'deg)';
        });
      });
      card.addEventListener('mouseleave', function () {
        card.style.transform = '';
      });
    });
  }

  /* ---------------- Payment method chip toggle -------------------- */
  function initPayOptions() {
    var groups = document.querySelectorAll('[data-pay-options]');
    groups.forEach(function (group) {
      var labels = group.querySelectorAll('.pay-option');
      function refresh() {
        labels.forEach(function (l) {
          var input = l.querySelector('input[type=radio]');
          l.classList.toggle('is-checked', !!input && input.checked);
        });
      }
      group.addEventListener('change', refresh);
      refresh();
    });
  }

  /* ---------------- Init on DOM ready ------------------------------ */
  function initAll() {
    initScrollReveal();
    initCounters();
    initCardTilt();
    initPayOptions();
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAll);
  } else {
    initAll();
  }
})();
