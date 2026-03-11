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

// ── 1b. Anti-FOUC: restore light/dark theme BEFORE paint ─────────────────────
// Reads the stored preference and sets data-theme on <html> immediately so the
// page renders with the correct colours without a flash.
(function () {
  var t = localStorage.getItem('armguardTheme');
  if (t === 'light') document.documentElement.setAttribute('data-theme', 'light');
})();

// ── 2 & 3. Sidebar + Notifications (after DOM is ready) ──────────────────────
document.addEventListener('DOMContentLoaded', function () {

  // Active nav-group auto-open
  document.querySelectorAll('.nav-group').forEach(function (g) {
    if (g.querySelector('.nav-item.active')) g.classList.add('open');
  });

  // ── Theme toggle ────────────────────────────────────────────────────────
  (function () {
    var btn = document.getElementById('theme-toggle-btn');
    if (!btn) return;

    function applyTheme(theme) {
      if (theme === 'light') {
        document.documentElement.setAttribute('data-theme', 'light');
      } else {
        document.documentElement.removeAttribute('data-theme');
      }
      localStorage.setItem('armguardTheme', theme);
    }

    btn.addEventListener('click', function () {
      var current = document.documentElement.getAttribute('data-theme');
      applyTheme(current === 'light' ? 'dark' : 'light');
    });
  })();

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
          var isSsl = actionUrl === '#ssl-install';
          btn.href = isSsl ? '#' : actionUrl;
          btn.className = 'notif-action-btn';
          btn.textContent = isSsl ? 'View Install Guide' : 'View';
          btn.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation(); // prevent item click from double-firing
            markNotifRead(notifId, null);
            if (isSsl && typeof window.openSslModal === 'function') {
              window.openSslModal();
            } else if (!isSsl) {
              window.location.href = actionUrl;
            }
          });
          el.querySelector('.notif-body').appendChild(btn);
        })(n.id, n.actionUrl);
      }
      // Clicking the item opens the detail modal and marks it as read
      (function (notif) {
        el.addEventListener('click', function (e) {
          if (e.target.classList.contains('notif-action-btn')) return;
          markNotifRead(notif.id, notif.time);
          if (typeof window.openNotifDetail === 'function') window.openNotifDetail(notif);
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

    var installedBtn = document.getElementById('ssl-modal-installed');
    closeBtn.addEventListener('click', closeModal);
    cancelBtn.addEventListener('click', closeModal);
    if (installedBtn) {
      installedBtn.addEventListener('click', function () {
        if (typeof window.ackSslCert === 'function') window.ackSslCert();
        else window.removeNotifById('ssl-cert');
        setTimeout(closeModal, 300);
      });
    }
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

  // ── Notification Detail Modal ───────────────────────────────────────────
  (function () {
    var overlay    = document.getElementById('notif-detail-overlay');
    var titleEl    = document.getElementById('notif-detail-title');
    var iconEl     = document.getElementById('notif-detail-icon');
    var msgEl      = document.getElementById('notif-detail-msg');
    var timeEl     = document.getElementById('notif-detail-time');
    var actionBtn  = document.getElementById('notif-detail-action');
    var dismissBtn = document.getElementById('notif-detail-dismiss');
    var closeBtn   = document.getElementById('notif-detail-close');
    if (!overlay) return;

    var _cur = null;

    function openDetail(notif) {
      _cur = notif;
      titleEl.textContent = notif.title;
      iconEl.className = 'notif-detail-icon ' + (notif.type || 'info');
      iconEl.innerHTML = '<i class="fa-solid ' + (notif.icon || 'fa-info') + '"></i>';
      msgEl.textContent = notif.msg;
      timeEl.textContent = notif.time;
      if (notif.actionUrl) {
        actionBtn.textContent = notif.actionUrl === '#ssl-install' ? 'View Install Guide' : 'Open';
        actionBtn.style.display = 'inline-block';
      } else {
        actionBtn.style.display = 'none';
      }
      // Close the notif panel so the modal is visible
      var panel = document.getElementById('notif-panel');
      if (panel) panel.classList.remove('open');
      overlay.style.display = 'flex';
    }

    function closeDetail() { overlay.style.display = 'none'; _cur = null; }

    closeBtn.addEventListener('click', closeDetail);
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) closeDetail();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && overlay.style.display !== 'none') closeDetail();
    });
    actionBtn.addEventListener('click', function (e) {
      e.preventDefault();
      closeDetail();
      if (_cur && _cur.actionUrl === '#ssl-install') {
        if (typeof window.openSslModal === 'function') window.openSslModal();
      }
    });
    dismissBtn.addEventListener('click', function () {
      if (_cur) {
        // For the SSL cert notification, ack the mtime so the poll won't re-add it
        if (_cur.id === 'ssl-cert' && typeof window.ackSslCert === 'function') {
          window.ackSslCert();
        } else if (_cur.id) {
          window.removeNotifById(_cur.id);
        } else {
          var t = _cur.time;
          saveNotifs(getNotifs().filter(function (x) { return x.time !== t; }));
          renderNotifs();
        }
      }
      closeDetail();
    });

    window.openNotifDetail = openDetail;
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

    function hideSidebarBtn() {
      var btn = document.getElementById('ssl-cert-sidebar-btn');
      if (btn) btn.style.display = 'none';
    }

    window.ackSslCert = function () {
      if (_lastCertMtime) localStorage.setItem(LS_KEY, _lastCertMtime);
      window.removeNotifById('ssl-cert');
      hideSidebarBtn();
    };

    // Hide sidebar button immediately if already acked on this device
    (function () {
      var acked = parseFloat(localStorage.getItem(LS_KEY) || '0');
      if (acked > 0) hideSidebarBtn();
    })();

    setTimeout(checkSslCert, 2000);
    setInterval(checkSslCert, SSL_POLL_MS);
  })();

  // ── TR Overdue Notifications ──────────────────────────────────────────────
  // Polls every 5 minutes for TR withdrawals not returned within 24 hours.
  // Notifications stay red (unread) while items remain outstanding.
  // Auto-removed as soon as items are returned (log status → Closed).
  if (document.body.dataset.poll === '1') {
    (function () {
      var TR_OVERDUE_URL    = '/transactions/api/overdue-tr/';
      var TR_POLL_MS        = 5 * 60 * 1000; // 5 minutes
      var TR_PREFIX         = 'tr-overdue-';

      function pollOverdueTR() {
        fetch(TR_OVERDUE_URL, {
          credentials: 'same-origin',
          headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          if (!data) return;

          var currentIds = data.overdue.map(function (o) { return TR_PREFIX + o.id; });

          // Remove notifications for logs that are now resolved (returned)
          getNotifs().filter(function (n) {
            return n.id && n.id.indexOf(TR_PREFIX) === 0 && currentIds.indexOf(n.id) === -1;
          }).forEach(function (n) { window.removeNotifById(n.id); });

          // Add or refresh each overdue log
          data.overdue.forEach(function (log) {
            var nid = TR_PREFIX + log.id;
            var msg = log.personnel + ' \u2014 ' + log.items.join(', ') +
                      ' \u00b7 ' + log.hours_overdue + 'h overdue (\u00b7' + log.status + ')';

            var stored = getNotifs().filter(function (n) { return n.id === nid; });
            if (stored.length) {
              // Item still not returned — keep/refresh the notification as unread (red)
              saveNotifs(getNotifs().map(function (n) {
                return n.id === nid
                  ? Object.assign({}, n, { unread: true, msg: msg })
                  : n;
              }));
              window.renderNotifs();
            } else {
              window.addNotif(
                'TR Overdue \u2014 Return Required',
                msg,
                'danger', 'fa-circle-exclamation',
                nid,
                '/transactions/?search=' + encodeURIComponent(log.personnel)
              );
            }
          });
        })
        .catch(function () { /* network error — silently skip */ });
      }

      // First check after 10 s, then every 5 min
      setTimeout(function () { pollOverdueTR(); setInterval(pollOverdueTR, TR_POLL_MS); }, 10000);
    })();
  }

}); // end DOMContentLoaded
