/* =========================================================================
   responsive.js — Shared UI/UX controller
   -------------------------------------------------------------------------
   Loaded by EVERY page. Responsibilities (all non-destructive):
     • Injects a mobile top-bar + hamburger + overlay (mobile only)
     • Opens / closes the sidebar; closes on overlay click, ESC, or link click
     • Marks body.sidebar-open to lock background scroll
     • Exposes AptiUI.showToast(msg, type) for success/error notifications
     • Adds reveal-on-scroll for cards (.apti-reveal)
     • Marks <body class="js-ready"> for fade-in animations
     • Basic keyboard a11y (focus the sidebar on open)
   It does NOT touch existing per-page JS. Each page's own script still
   handles data-page navigation and logout. The injected hamburger just
   toggles the sidebar classes that the existing CSS already understands.
   ========================================================================= */

(function () {
  'use strict';

  var AptiUI = (window.AptiUI = window.AptiUI || {});

  /* ── Toast / notification system ──────────────────────────────────────── */
  var toastContainer = null;
  function ensureToastContainer() {
    if (toastContainer && document.body.contains(toastContainer)) return toastContainer;
    toastContainer = document.createElement('div');
    toastContainer.id = 'apti-toast-container';
    toastContainer.style.cssText =
      'position:fixed;top:18px;right:18px;z-index:10000;display:flex;' +
      'flex-direction:column;gap:10px;max-width:calc(100vw - 36px);' +
      'pointer-events:none;';
    document.body.appendChild(toastContainer);
    return toastContainer;
  }

  function showToast(message, type) {
    type = type || 'info';
    var palette = {
      success: { bg: '#3f7d46', icon: 'fa-circle-check' },
      error:   { bg: '#b45748', icon: 'fa-circle-exclamation' },
      info:    { bg: '#4d4742', icon: 'fa-circle-info' },
    };
    var p = palette[type] || palette.info;
    var el = document.createElement('div');
    el.setAttribute('role', type === 'error' ? 'alert' : 'status');
    el.style.cssText =
      'display:flex;align-items:center;gap:10px;color:#fff;background:' + p.bg + ';' +
      'padding:13px 16px;border-radius:10px;font-size:14px;font-weight:600;' +
      'font-family:Poppins,sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.18);' +
      'min-width:240px;max-width:360px;pointer-events:auto;opacity:0;' +
      'transform:translateX(40px);transition:opacity .3s ease, transform .3s ease;';
    el.innerHTML =
      '<i class="fa-solid ' + p.icon + '" aria-hidden="true"></i>' +
      '<span style="flex:1;line-height:1.35"></span>' +
      '<button class="apti-toast-x" aria-label="Close" style="background:none;border:none;' +
      'color:#fff;cursor:pointer;font-size:14px;opacity:.8;padding:0 2px;">&times;</button>';
    el.querySelector('span').textContent = String(message);

    var box = ensureToastContainer();
    box.appendChild(el);
    requestAnimationFrame(function () {
      el.style.opacity = '1';
      el.style.transform = 'translateX(0)';
    });

    function dismiss() {
      el.style.opacity = '0';
      el.style.transform = 'translateX(40px)';
      setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 300);
    }
    el.querySelector('.apti-toast-x').addEventListener('click', dismiss);
    var timer = setTimeout(dismiss, 4000);
    el.addEventListener('mouseenter', function () { clearTimeout(timer); });
    el.addEventListener('mouseleave', function () { timer = setTimeout(dismiss, 3000); });
    return el;
  }
  AptiUI.showToast = showToast;

  // Backwards-compat alias used by some legacy inline scripts
  window.showNotification = window.showNotification || function (m, t) { showToast(m, t); };

  /* ── Mobile sidebar / hamburger controller ────────────────────────────── */
  function ready(fn) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn);
    } else { fn(); }
  }

  ready(function () {
    document.body.classList.add('js-ready');

    var sidebar = document.querySelector('.sidebar') || document.querySelector('.admin-sidebar');
    if (!sidebar) { return; } // landing/auth pages have no sidebar

    var isAdmin = sidebar.classList.contains('admin-sidebar');
    if (isAdmin) document.body.classList.add('admin-body');

    // Build top bar
    var topbar = document.createElement('header');
    topbar.className = 'app-topbar';

    var brand = document.createElement('div');
    brand.className = 'app-topbar__brand';
    var brandLogo = document.querySelector('.sidebar .logo img, .admin-sidebar .admin-logo');
    if (brandLogo) {
      var imgClone = brandLogo.cloneNode();
      imgClone.style.height = '34px';
      imgClone.style.width = 'auto';
      imgClone.style.maxWidth = '150px';
      imgClone.removeAttribute('width');
      imgClone.removeAttribute('height');
      brand.appendChild(imgClone);
    }
    var title = document.createElement('span');
    title.className = 'app-topbar__title';
    title.textContent = document.title.replace(/\s*[-|].*$/, '').trim() || 'Aptitude';
    brand.appendChild(title);
    topbar.appendChild(brand);

    var ham = document.createElement('button');
    ham.type = 'button';
    ham.className = 'hamburger';
    ham.setAttribute('aria-label', 'Open menu');
    ham.setAttribute('aria-controls', sidebar.id || 'sidebar');
    ham.setAttribute('aria-expanded', 'false');
    ham.innerHTML = '<i class="fa-solid fa-bars hamburger__icon" aria-hidden="true"></i>';
    topbar.appendChild(ham);

    // Insert topbar as the first child of <body>
    document.body.insertBefore(topbar, document.body.firstChild);

    // Build overlay
    var overlay = document.createElement('div');
    overlay.className = 'sidebar-overlay';
    overlay.setAttribute('aria-hidden', 'true');
    document.body.appendChild(overlay);

    function openSidebar() {
      sidebar.classList.add('is-open');
      // aptitude-test.js uses .show — keep both for compatibility
      sidebar.classList.add('show');
      overlay.classList.add('is-open');
      overlay.setAttribute('aria-hidden', 'false');
      ham.setAttribute('aria-expanded', 'true');
      ham.setAttribute('aria-label', 'Close menu');
      document.body.classList.add('sidebar-open');
      // Move focus into the sidebar for keyboard / screen-reader users
      var first = sidebar.querySelector('a, button, [tabindex], input, li');
      if (first) { try { first.focus({ preventScroll: true }); } catch (e) {} }
    }
    function closeSidebar() {
      sidebar.classList.remove('is-open', 'show');
      overlay.classList.remove('is-open');
      overlay.setAttribute('aria-hidden', 'true');
      ham.setAttribute('aria-expanded', 'false');
      ham.setAttribute('aria-label', 'Open menu');
      document.body.classList.remove('sidebar-open');
    }
    AptiUI.openSidebar = openSidebar;
    AptiUI.closeSidebar = closeSidebar;

    ham.addEventListener('click', function () {
      if (sidebar.classList.contains('is-open') || sidebar.classList.contains('show')) {
        closeSidebar();
      } else { openSidebar(); }
    });
    overlay.addEventListener('click', closeSidebar);

    // Close on ESC
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && (sidebar.classList.contains('is-open') || sidebar.classList.contains('show'))) {
        closeSidebar();
        ham.focus();
      }
    });

    // Close after navigating via a sidebar link (data-page or href)
    sidebar.addEventListener('click', function (e) {
      var link = e.target.closest('[data-page], a[href], [data-action]');
      if (link) { closeSidebar(); }
    });

    // If the page provides its own #menu-btn / #close-btn (test-page), keep them in sync
    var legacyMenuBtn = document.getElementById('menu-btn');
    var legacyCloseBtn = document.getElementById('close-btn');
    if (legacyMenuBtn) { legacyMenuBtn.addEventListener('click', openSidebar); }
    if (legacyCloseBtn) { legacyCloseBtn.addEventListener('click', closeSidebar); }

    // Close sidebar when resizing up to desktop (prevents a stuck overlay)
    var resizeTimer;
    window.addEventListener('resize', function () {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(function () {
        if (window.innerWidth >= 992) closeSidebar();
      }, 150);
    });

    // Highlight the active sidebar item based on current path
    var path = window.location.pathname.replace(/\/$/, '');
    sidebar.querySelectorAll('[data-page]').forEach(function (item) {
      var target = (item.getAttribute('data-page') || '').replace(/\/$/, '');
      if (target && (path === target || path.indexOf(target + '/') === 0)) {
        // Remove any pre-set active, set on the matching one
        var wasActive = item.classList.contains('active');
        if (!wasActive) {
          // Don't override an explicit .active in markup for the same page
          var alreadyActive = sidebar.querySelector('[data-page="' + item.getAttribute('data-page') + '"].active');
          if (!alreadyActive) item.classList.add('active');
        }
      }
    });
  });

  /* ── Reveal-on-scroll for cards (progressive enhancement) ─────────────── */
  ready(function () {
    var revealTargets =
      '.card, .task-card, .reward-card, .stat-card, .category-card, ' +
      '.profile-card, .stats-section, .activity-section, .chart-card, ' +
      '.feature, .feature-box, .progress-item, .focus-pill';
    var els = Array.prototype.slice.call(document.querySelectorAll(revealTargets));
    if (!els.length) return;
    els.forEach(function (el) { el.classList.add('apti-reveal'); });

    if (!('IntersectionObserver' in window)) {
      els.forEach(function (el) { el.classList.add('apti-reveal--in'); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry, i) {
        if (entry.isIntersecting) {
          // small stagger
          setTimeout(function () { entry.target.classList.add('apti-reveal--in'); }, (i % 6) * 60);
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08, rootMargin: '0px 0px -40px 0px' });
    els.forEach(function (el) { io.observe(el); });
  });
})();
