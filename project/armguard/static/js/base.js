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
      // Action button: open the install guide modal or navigate to actionUrl
      if (n.actionUrl && n.id) {
        (function (notifId, actionUrl) {
          var btn = document.createElement('a');
          btn.href = actionUrl === '#ssl-install' ? '#' : actionUrl;
          btn.className = 'notif-action-btn';
          btn.textContent = 'View Install Guide';
          btn.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation(); // prevent item click from double-firing
            markNotifRead(notifId, null);
            if (typeof window.openSslModal === 'function') window.openSslModal();
          });
          el.querySelector('.notif-body').appendChild(btn);
        })(n.id, n.actionUrl);
      }
      // Clicking the item itself marks it as read and clears the badge dot
      (function (notif) {
        el.addEventListener('click', function (e) {
          if (e.target.classList.contains('notif-action-btn')) return;
          markNotifRead(notif.id, notif.time);
        });
      })(n);
      list.insertBefore(el, empty);
    });
  };

  // Mark a single notification as read. Match by id (if set) else by time.
  function markNotifRead(id, time) {
    saveNotifs(getNotifs().map(function (x) {
      var match = id ? x.id === id : x.time === time;
      return match ? Object.assign({}, x, { unread: false }) : x;
    }));
    renderNotifs();
  }

  window.clearNotifs = function () {
    saveNotifs(getNotifs().map(function (n) { return Object.assign({}, n, { unread: false }); }));
    renderNotifs();
  };

  window.addNotif = function (title, msg, type, icon, id, actionUrl) {
    type = type || 'info';
    icon = icon || 'fa-info';
    var notifs = getNotifs();
    // Prevent duplicate for named (id-keyed) notifications.
    if (id && notifs.some(function (n) { return n.id === id; })) return false;
    notifs.push({
      id: id || null,
      actionUrl: actionUrl || null,
      title: title, msg: msg, type: type, icon: icon, unread: true,
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    });
    saveNotifs(notifs);
    renderNotifs();
    return true; // new notif was added
  };

  window.removeNotifById = function (id) {
    saveNotifs(getNotifs().filter(function (n) { return n.id !== id; }));
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

  // ── SSL Certificate Install Guide Modal ───────────────────────────────────
  (function () {
    var overlay   = document.getElementById('ssl-modal-overlay');
    var closeBtn  = document.getElementById('ssl-modal-close');
    var cancelBtn = document.getElementById('ssl-modal-cancel');
    var dlBtn     = document.getElementById('ssl-modal-download');
    var sidebarBtn = document.getElementById('ssl-cert-sidebar-btn');
    if (!overlay) return;

    function openModal() { overlay.style.display = 'flex'; }
    function closeModal() { overlay.style.display = 'none'; }

    // Sidebar link opens modal instead of directly downloading
    if (sidebarBtn) {
      sidebarBtn.addEventListener('click', function (e) {
        e.preventDefault();
        openModal();
      });
    }

    closeBtn.addEventListener('click', closeModal);
    cancelBtn.addEventListener('click', closeModal);
    // Close when clicking the dark backdrop (outside the modal box)
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) closeModal();
    });
    // Close on Escape key
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && overlay.style.display !== 'none') closeModal();
    });
    // Download button: ack in localStorage (removes notif) then close modal
    dlBtn.addEventListener('click', function () {
      if (typeof window.ackSslCert === 'function') window.ackSslCert();
      else window.removeNotifById('ssl-cert');
      setTimeout(closeModal, 400);
    });

    // Expose so the notification "Download & Install" button can also open the modal
    window.openSslModal = openModal;
  })();

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

  // ── SSL certificate renewal check (on load + every 6 hours) ─────────────
  // Runs for all authenticated users regardless of poll flag.
  // Polls the server to see if the cert has been renewed since this device
  // last downloaded it. If so, shows a notification with a download link.
  (function () {
    var SSL_STATUS_URL = '/download/ssl-cert-status/';
    var SSL_POLL_MS    = 6 * 60 * 60 * 1000; // re-check every 6 hours
    var LS_KEY         = 'armguard_ssl_cert_acked';
    var _lastCertMtime = 0;

    function checkSslCert() {
      fetch(SSL_STATUS_URL, {
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data || !data.cert_mtime) return;
        _lastCertMtime = data.cert_mtime;
        var acked = parseFloat(localStorage.getItem(LS_KEY) || '0');
        if (acked >= _lastCertMtime) return; // already installed this version
        var isRenewal = acked > 0;
        var added = window.addNotif(
          isRenewal ? 'SSL Certificate Renewed' : 'Install SSL Certificate',
          isRenewal
            ? 'A new security certificate was issued for this server. Reinstall it on this device to keep the secure padlock.'
            : 'This server uses a self-signed certificate. Install it on this device to remove the "Not secure" warning.',
          'warning', 'fa-certificate', 'ssl-cert', '#ssl-install'
        );
        if (added) {
          document.getElementById('notif-panel').classList.add('open');
        }
      })
      .catch(function () { /* network error — silently skip */ });
    }

    window.ackSslCert = function () {
      if (_lastCertMtime) localStorage.setItem(LS_KEY, _lastCertMtime);
      window.removeNotifById('ssl-cert');
    };

    setTimeout(checkSslCert, 2000);
    setInterval(checkSslCert, SSL_POLL_MS);
  })();

}); // end DOMContentLoaded
