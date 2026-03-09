/**
 * ArmGuard RDS — base.js
 *
 * C2 FIX: Extracted from base.html to eliminate 'unsafe-inline' from
 * Content-Security-Policy script-src.
 *
 * Contains:
 *   1. Sidebar anti-FOUC (runs immediately on parse, before DOMContentLoaded)
 *   2. Sidebar toggle + nav-group flyout + tooltip initialisation (on DOMContentLoaded)
 *   3. Notification panel logic
 *   4. G13: Inventory-change polling (activated via data-poll on <body>)
 */

// ── 1. Anti-FOUC: restore sidebar collapsed state BEFORE paint ────────────────
// Guard: document.body is null when this script executes from <head> on the
// very first parse; only add the class when body is already available.
if (document.body && localStorage.getItem('sidebarCollapsed') === 'true') {
  document.body.classList.add('sidebar-collapsed');
}

// ── 2 & 3. Sidebar + Notifications (after DOM is ready) ──────────────────────
document.addEventListener('DOMContentLoaded', function () {

  // Active nav-group auto-open
  document.querySelectorAll('.nav-group').forEach(function (g) {
    if (g.querySelector('.nav-item.active')) g.classList.add('open');
  });

  // Sidebar toggle button (replaces CSP-blocked onclick="toggleSidebar()")
  window.toggleSidebar = function () {
    var c = document.body.classList.toggle('sidebar-collapsed');
    localStorage.setItem('sidebarCollapsed', c);
  };
  var sidebarToggleBtn = document.getElementById('sidebar-toggle');
  if (sidebarToggleBtn) sidebarToggleBtn.addEventListener('click', window.toggleSidebar);

  // Nav-group expand/collapse (replaces CSP-blocked onclick="this.closest(...).classList.toggle('open')")
  document.querySelectorAll('.nav-group-header').forEach(function (header) {
    header.addEventListener('click', function () {
      var group = this.closest('.nav-group');
      if (group) group.classList.toggle('open');
    });
  });

  // Nav-group flyout (visible only when sidebar is collapsed)
  document.querySelectorAll('.nav-group').forEach(function (group) {
    var flyout = group.querySelector('.nav-flyout');
    if (!flyout) return;
    var hideTimer;

    function show() {
      if (!document.body.classList.contains('sidebar-collapsed')) return;
      clearTimeout(hideTimer);
      var rect = group.getBoundingClientRect();
      flyout.style.top = rect.top + 'px';
      flyout.style.left = '60px';
      flyout.style.display = 'block';
      flyout.offsetHeight; // force reflow
      flyout.classList.add('visible');
    }

    function hide() {
      clearTimeout(hideTimer);
      hideTimer = setTimeout(function () {
        flyout.classList.remove('visible');
        setTimeout(function () {
          if (!flyout.classList.contains('visible')) flyout.style.display = 'none';
        }, 150);
      }, 90);
    }

    group.addEventListener('mouseenter', show);
    group.addEventListener('mouseleave', hide);
    flyout.addEventListener('mouseenter', function () { clearTimeout(hideTimer); });
    flyout.addEventListener('mouseleave', hide);
  });

  // Tooltip overlay for collapsed sidebar
  (function () {
    var tip = document.createElement('div');
    tip.className = 'nav-tip';
    document.body.appendChild(tip);
    var tipHide;

    function showTip(el) {
      if (!document.body.classList.contains('sidebar-collapsed')) return;
      if (el.classList.contains('nav-group-header')) return;
      var label = el.getAttribute('title') || el.getAttribute('data-saved-title');
      if (!label) return;
      el.setAttribute('data-saved-title', label);
      el.removeAttribute('title');
      clearTimeout(tipHide);
      var rect = el.getBoundingClientRect();
      tip.textContent = label;
      tip.style.display = 'block';
      tip.style.top = (rect.top + rect.height / 2) + 'px';
      tip.style.left = '64px';
      tip.offsetHeight; // force reflow
      tip.classList.add('visible');
    }

    function hideTip(el) {
      var saved = el.getAttribute('data-saved-title');
      if (saved) { el.setAttribute('title', saved); el.removeAttribute('data-saved-title'); }
      tip.classList.remove('visible');
      clearTimeout(tipHide);
      tipHide = setTimeout(function () { tip.style.display = 'none'; }, 160);
    }

    document.querySelectorAll('.sidebar .nav-item,.sidebar .nav-group-header,.sidebar .logout-btn')
      .forEach(function (el) {
        el.addEventListener('mouseenter', function () { showTip(el); });
        el.addEventListener('mouseleave', function () { hideTip(el); });
      });
  })();

  // ── Notification panel ────────────────────────────────────────────────────
  var NOTIF_KEY = 'armguard_notifs';

  function getNotifs() {
    try { return JSON.parse(localStorage.getItem(NOTIF_KEY)) || []; } catch (e) { return []; }
  }

  function saveNotifs(n) { localStorage.setItem(NOTIF_KEY, JSON.stringify(n)); }

  window.renderNotifs = function () {
    var notifs = getNotifs();
    var list  = document.getElementById('notif-list');
    var empty = document.getElementById('notif-empty');
    var badge = document.getElementById('notif-badge');
    if (!list) return;
    var unread = notifs.filter(function (n) { return n.unread; }).length;
    badge.textContent = unread > 0 ? unread : '';
    badge.style.display = unread > 0 ? 'flex' : 'none';
    list.querySelectorAll('.notif-item').forEach(function (e) { e.remove(); });
    if (notifs.length === 0) { empty.style.display = 'block'; return; }
    empty.style.display = 'none';
    notifs.slice().reverse().forEach(function (n) {
      var el = document.createElement('div');
      el.className = 'notif-item' + (n.unread ? ' unread' : '');
      // Note: n.title, n.msg, n.type, n.icon, n.time are app-controlled strings
      // (not user-supplied), so innerHTML is safe here.
      el.innerHTML =
        '<div class="notif-icon ' + (n.type || 'info') + '">' +
          '<i class="fa-solid ' + (n.icon || 'fa-info') + '"></i>' +
        '</div>' +
        '<div class="notif-body">' +
          '<div class="notif-body-title">' + n.title + '</div>' +
          '<div class="notif-body-msg">' + n.msg + '</div>' +
          '<div class="notif-body-time">' + n.time + '</div>' +
        '</div>';
      list.insertBefore(el, empty);
    });
  };

  window.clearNotifs = function () {
    saveNotifs(getNotifs().map(function (n) { return Object.assign({}, n, { unread: false }); }));
    renderNotifs();
  };

  window.addNotif = function (title, msg, type, icon) {
    type = type || 'info';
    icon = icon || 'fa-info';
    var notifs = getNotifs();
    notifs.push({
      title: title, msg: msg, type: type, icon: icon, unread: true,
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    });
    saveNotifs(notifs);
    renderNotifs();
  };

  window.toggleNotif = function (e) {
    if (e) e.stopPropagation();
    document.getElementById('notif-panel').classList.toggle('open');
  };

  // Wire notification button and clear button via addEventListener
  // (replaces CSP-blocked onclick="toggleNotif(event)" / onclick="clearNotifs()")
  var notifBtn = document.getElementById('notif-btn');
  if (notifBtn) notifBtn.addEventListener('click', window.toggleNotif);
  var notifClearBtn = document.getElementById('notif-clear-btn');
  if (notifClearBtn) notifClearBtn.addEventListener('click', window.clearNotifs);

  document.addEventListener('click', function (e) {
    var wrap = document.getElementById('notif-wrap');
    if (wrap && !wrap.contains(e.target)) {
      document.getElementById('notif-panel').classList.remove('open');
    }
  });

  renderNotifs();

  // ── 4. G13: Inventory-change polling (only for authenticated users) ────────
  // Activated when <body data-poll="1"> is present.
  if (document.body.dataset.poll === '1') {
    (function () {
      var POLL_MS = 30000;
      var knownTs  = null;
      var notified = false;
      // F6 FIX: Read the poll URL from a data attribute so base.js never hardcodes it.
      var POLL_URL = document.body.dataset.lastModifiedUrl || '/api/v1/last-modified/';

      function poll() {
        fetch(POLL_URL, {
          credentials: 'same-origin',
          headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          if (!data || !data.last_modified) return;
          if (knownTs === null) { knownTs = data.last_modified; return; }
          if (data.last_modified !== knownTs && !notified) {
            notified = true;
            addNotif(
              'Inventory Updated',
              'Another user made a transaction. ' +
              '<a href="' + window.location.href + '" style="color:var(--primary)">Reload page</a>' +
              ' to see the latest data.',
              'warning', 'fa-triangle-exclamation'
            );
          }
        })
        .catch(function () { /* network error — silently skip */ });
      }

      setTimeout(function () { poll(); setInterval(poll, POLL_MS); }, 5000);
    })();
  }

}); // end DOMContentLoaded
