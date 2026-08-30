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

    // Prevent accidental full-page reloads from generic buttons that are meant to trigger JS only.
    document.querySelectorAll('button:not([type])').forEach(function (button) {
      button.type = 'button';
    });

    var sidebar = document.querySelector('.sidebar, .shared-sidebar, .admin-sidebar');
    if (!sidebar) { return; } // landing/auth pages have no sidebar

    // Keep all injected mobile UI for mobile only. Desktop nav should keep native layout.
    var isMobileLayout = window.matchMedia('(max-width: 991.98px)').matches;
    if (!isMobileLayout) {
      return;
    }

    // Hydrate the common sidebar on pages without a dedicated profile script.
    try {
      var storedUser = JSON.parse(localStorage.getItem('user') || 'null');
      if (storedUser && storedUser.username) {
        var username = document.getElementById('sidebar-username');
        var avatar = document.getElementById('sidebar-avatar');
        if (username) username.textContent = storedUser.username;
        if (avatar) avatar.alt = storedUser.username;
      }
    } catch (e) {}

    var isAdmin = sidebar.classList.contains('admin-sidebar');
    if (isAdmin) document.body.classList.add('admin-body');

    // Build top bar
    var topbar = document.createElement('header');
    topbar.className = 'app-topbar';

    var brand = document.createElement('div');
    brand.className = 'app-topbar__brand';
    var brandLogo = document.querySelector('.sidebar .logo img, .shared-sidebar .logo img, .admin-sidebar .admin-logo');
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

    // Beginner-friendly: add a persistent Help button to the topbar
    var helpBtn = document.createElement('button');
    helpBtn.type = 'button';
    helpBtn.className = 'topbar-help';
    helpBtn.setAttribute('aria-label', 'Open getting started guide');
    helpBtn.innerHTML = '<i class="fa-solid fa-circle-question" aria-hidden="true"></i> <span class="help-label">Help</span>';
    topbar.appendChild(helpBtn);

    // Improve mobile touch interactions: prefer touchstart to avoid 300ms delays
    ham.addEventListener('touchstart', function (ev) {
      ev.stopPropagation();
    }, { passive: true });
    helpBtn.addEventListener('touchstart', function (ev) {
      ev.stopPropagation();
    }, { passive: true });

    // Insert topbar as the first child of <body>
    document.body.insertBefore(topbar, document.body.firstChild);

    // Determine page id for per-page help and pin storage
    var pageId = document.body.getAttribute('data-page') || (document.querySelector('meta[name="page"]') && document.querySelector('meta[name="page"]').content) || 'default';

    // Beginner guide modal (injected globally so every page has quick help)
    var guideModal = document.createElement('div');
    guideModal.className = 'apti-help-modal';
    guideModal.setAttribute('role', 'dialog');
    guideModal.setAttribute('aria-hidden', 'true');
    guideModal.innerHTML = '\n      <div class="apti-help-modal__backdrop" tabindex="-1"></div>\n      <div class="apti-help-modal__panel" role="document" tabindex="-1">\n        <div style="display:flex;align-items:center;justify-content:flex-end;gap:8px;margin-bottom:8px;">\n          <button class="apti-help-pin" aria-pressed="true" title="Keep help open">📌</button>\n          <button class="apti-help-close" aria-label="Close help">✕</button>\n        </div>\n        <div class="apti-help-modal__content" aria-live="polite">Loading help…</div>\n        <div style="text-align:right;margin-top:12px;"><button class="primary-btn apti-help-gotit">Got it</button></div>\n      </div>';
    document.body.appendChild(guideModal);

    // Load per-page help file (falls back to default)
    (function loadPerPageHelp() {
      var contentEl = guideModal.querySelector('.apti-help-modal__content');
      if (!contentEl) return;
      var helpPath = '/static/help/' + pageId + '.html';
      function fallback() {
        // try default
        fetch('/static/help/default.html', { cache: 'no-cache' }).then(function (r) {
          if (!r.ok) throw new Error('no default');
          return r.text();
        }).then(function (html) { contentEl.innerHTML = html; }).catch(function () {
          contentEl.innerHTML = '<h3>Quick Help</h3><p>Use the menu to navigate. Click Help again for more tips.</p>';
        });
      }
      fetch(helpPath, { cache: 'no-cache' }).then(function (resp) {
        if (!resp.ok) throw new Error('not found');
        return resp.text();
      }).then(function (html) {
        contentEl.innerHTML = html;
      }).catch(function () {
        fallback();
      });
    })();

    // Help button open/close handlers and pin behaviour
    var pinned = (localStorage.getItem('apti_help_pin_' + pageId) !== 'false'); // default true
    function updatePinButton() {
      var pinBtn = guideModal.querySelector('.apti-help-pin');
      if (!pinBtn) return;
      pinBtn.setAttribute('aria-pressed', pinned ? 'true' : 'false');
      pinBtn.classList.toggle('is-pinned', pinned);
      try { localStorage.setItem('apti_help_pin_' + pageId, pinned ? 'true' : 'false'); } catch (e) {}
    }

    function openHelp() {
      guideModal.setAttribute('aria-hidden', 'false');
      guideModal.classList.add('is-open');
      var panel = guideModal.querySelector('.apti-help-modal__panel');
      try { panel.focus(); } catch (e) {}
      try { localStorage.setItem('apti_help_open_' + pageId, 'true'); } catch (e) {}
    }
    function closeHelp() {
      guideModal.setAttribute('aria-hidden', 'true');
      guideModal.classList.remove('is-open');
      ham.focus();
      try { localStorage.setItem('apti_help_open_' + pageId, 'false'); } catch (e) {}
    }
    helpBtn.addEventListener('click', openHelp);
    guideModal.querySelector('.apti-help-close').addEventListener('click', closeHelp);
    guideModal.querySelector('.apti-help-gotit').addEventListener('click', closeHelp);
    // Backdrop click only closes when not pinned
    guideModal.querySelector('.apti-help-modal__backdrop').addEventListener('click', function () { if (!pinned) closeHelp(); });
    // Pin toggle
    var pinBtn = guideModal.querySelector('.apti-help-pin');
    if (pinBtn) {
      pinBtn.addEventListener('click', function () { pinned = !pinned; updatePinButton(); });
      updatePinButton();
    }
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && guideModal.classList.contains('is-open') && !pinned) closeHelp(); });

    // Auto-open help if pinned for this page — skip on interactive pages
    try {
      var openState = localStorage.getItem('apti_help_open_' + pageId);
      var interactivePages = ['mock-interview', 'test-page', 'coding-challenges'];
      if (pinned && (openState === 'true' || openState === null) && interactivePages.indexOf(pageId) === -1) {
        // If user hasn't explicitly closed it, open automatically so they can read
        openHelp();
      }
    } catch (e) {}

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
      if (link) {
        closeSidebar();
      }
    });

    // Central navigation for all sidebar variants (shared sidebar, legacy sidebar, admin sidebar).
    sidebar.addEventListener('click', function (e) {
      var pageItem = e.target.closest('[data-page]');
      if (pageItem && sidebar.contains(pageItem)) {
        e.preventDefault();
        var targetHref = pageItem.getAttribute('data-page');
        if (targetHref) {
          window.location.href = targetHref;
          return;
        }
      }

      var actionItem = e.target.closest('[data-action="logout"]');
      if (actionItem && sidebar.contains(actionItem)) {
        e.preventDefault();
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
        window.location.href = '/login';
        return;
      }

      var anchorLink = e.target.closest('a[href]');
      if (anchorLink && sidebar.contains(anchorLink)) {
        e.preventDefault();
        window.location.href = anchorLink.getAttribute('href');
      }
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
