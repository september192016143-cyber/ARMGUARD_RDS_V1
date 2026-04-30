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
// document.body is null when this script runs from <head>, so we apply the
// class to <html> (documentElement) which IS available. The DOMContentLoaded
// handler below syncs it to <body> and removes it from <html>.
if (localStorage.getItem('sidebarCollapsed') === 'true') {
  document.documentElement.classList.add('sidebar-collapsed');
}

// ── 1b. Anti-FOUC: restore light/dark theme BEFORE paint ─────────────────────
// Reads the stored preference and sets data-theme on <html> immediately so the
// page renders with the correct colours without a flash.
(function () {
  var t = localStorage.getItem('armguardTheme');
  if (t === 'light') document.documentElement.setAttribute('data-theme', 'light');
})();

// ── 1c. PJAX: AbortController for page-script event listener lifecycle ────────
// Page scripts that add document-level listeners (QR scanner keydown, etc.)
// should register them with { signal: window.pjaxController.signal } so they
// are automatically removed when PJAX navigates to the next page.
window.pjaxController = new AbortController();

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

  // ── Sync sidebar: move anti-FOUC class from <html> to <body> ────────────────
  // The head script applied sidebar-collapsed to <html>; move it to <body> now.
  if (document.documentElement.classList.contains('sidebar-collapsed')) {
    document.body.classList.add('sidebar-collapsed');
    document.documentElement.classList.remove('sidebar-collapsed');
  }
  // transaction-create: auto-collapse if the user currently has it expanded.
  // We do NOT save this to localStorage so the user's own preference is preserved
  // when they navigate away from this page.
  if (document.body.dataset.collapseSidebar === '1' &&
      !document.body.classList.contains('sidebar-collapsed')) {
    document.body.classList.add('sidebar-collapsed');
  }

  // Sidebar toggle button (replaces CSP-blocked onclick="toggleSidebar()")
  window.toggleSidebar = function () {
    var c = document.body.classList.toggle('sidebar-collapsed');
    localStorage.setItem('sidebarCollapsed', c);
  };
  var sidebarToggleBtn = document.getElementById('sidebar-toggle');
  if (sidebarToggleBtn) sidebarToggleBtn.addEventListener('click', window.toggleSidebar);

  // ── Mobile sidebar drawer (≤768 px) ─────────────────────────────────────
  var mobileMenuBtn    = document.getElementById('mobile-menu-btn');
  var sidebarOverlay   = document.getElementById('sidebar-overlay');
  var sidebarEl        = document.querySelector('.sidebar');

  function openMobileSidebar() {
    if (sidebarEl)      sidebarEl.classList.add('mobile-open');
    if (sidebarOverlay) sidebarOverlay.classList.add('active');
    document.body.classList.add('sidebar-open');
  }

  function closeMobileSidebar() {
    if (sidebarEl)      sidebarEl.classList.remove('mobile-open');
    if (sidebarOverlay) sidebarOverlay.classList.remove('active');
    document.body.classList.remove('sidebar-open');
  }

  if (mobileMenuBtn) {
    mobileMenuBtn.addEventListener('click', function () {
      if (sidebarEl && sidebarEl.classList.contains('mobile-open')) {
        closeMobileSidebar();
      } else {
        openMobileSidebar();
      }
    });
  }

  if (sidebarOverlay) {
    sidebarOverlay.addEventListener('click', closeMobileSidebar);
  }

  // Close drawer with Escape key
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && sidebarEl && sidebarEl.classList.contains('mobile-open')) {
      closeMobileSidebar();
    }
  });

  // Close drawer when viewport grows beyond mobile breakpoint
  window.addEventListener('resize', function () {
    if (window.innerWidth > 768 && sidebarEl && sidebarEl.classList.contains('mobile-open')) {
      closeMobileSidebar();
    }
  });

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
        var isTR = notif.id && (notif.id.indexOf('tr-overdue-') === 0 || notif.id.indexOf('tr-warning-') === 0);
        actionBtn.textContent = notif.actionUrl === '#ssl-install' ? 'View Install Guide'
                              : isTR ? 'View Transaction' : 'Open';
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
      } else if (_cur && _cur.actionUrl && _cur.actionUrl !== '#') {
        window.location.href = _cur.actionUrl;
      }
    });
    dismissBtn.addEventListener('click', function () {
      if (_cur) {
        var isTRNotif = _cur.id && (
          _cur.id.indexOf('tr-overdue-') === 0 || _cur.id.indexOf('tr-warning-') === 0
        );
        if (isTRNotif || _cur.id === 'ssl-cert') {
          // TR overdue/warning: only cleared when firearm is returned.
          // ssl-cert: only cleared when user confirms installation via the install guide modal.
          // In both cases just close the detail — do NOT remove the notification.
          closeDetail();
          return;
        }
        if (_cur.id) {
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
      var onHttps = window.location.protocol === 'https:';

      // If on HTTPS and this device has already acked the current cert, we're done.
      // Check acked value before the network call to avoid a flicker.
      if (onHttps) {
        var ackedEarly = parseFloat(localStorage.getItem(LS_KEY) || '0');
        if (ackedEarly > 0) {
          // Still need to verify the cert hasn't been renewed — do a lightweight
          // fetch but only to detect renewal; if no cert file it's mtime=0 so
          // acked(>0) >= 0 still passes the renewal check below.
          // Fall through to fetch so renewal is caught.
        } else {
          // On HTTPS, acked=0: might be self-signed not yet installed on this device.
          // Fall through to fetch and notify if needed.
        }
      }

      fetch(SSL_STATUS_URL, {
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) return;
        _lastCertMtime = data.cert_mtime || 0;
        var noCert = _lastCertMtime === 0;

        if (onHttps && noCert) {
          // Server has no cert and we're somehow on HTTPS — nothing to install.
          hideSidebarBtn();
          return;
        }

        if (!noCert) {
          // Cert file exists on server — check if this device has already acked it
          var acked = parseFloat(localStorage.getItem(LS_KEY) || '0');
          if (acked >= _lastCertMtime) {
            // Cert is installed and current → hide sidebar and clear any stale notif
            hideSidebarBtn();
            window.removeNotifById('ssl-cert');
            return;
          }
        }
        // noCert === true and on HTTP: no cert → always warn
        // noCert === false and not acked: self-signed not yet installed → warn

        var acked2 = _lastCertMtime > 0 ? parseFloat(localStorage.getItem(LS_KEY) || '0') : 0;
        var isRenewal = !noCert && acked2 > 0;
        var title = noCert   ? 'Connection Not Secured'
                  : isRenewal ? 'SSL Certificate Renewed'
                  :             'Install SSL Certificate';
        var msg = noCert
          ? 'This server does not have an SSL certificate. All data is transmitted unencrypted. Contact the administrator to configure SSL.'
          : isRenewal
          ? 'A new security certificate was issued for this server. Reinstall it on this device to keep the secure padlock.'
          : 'This server uses a self-signed certificate. Install it on this device to remove the \u201cNot secure\u201d warning.';
        var actionUrl = noCert ? null : '#ssl-install';
        // Update existing ssl-cert notif if already present (e.g. renewal updates the message)
        var existing = getNotifs().filter(function (n) { return n.id === 'ssl-cert'; });
        if (existing.length > 0) {
          saveNotifs(getNotifs().map(function (n) {
            return n.id === 'ssl-cert'
              ? Object.assign({}, n, { title: title, msg: msg, unread: true })
              : n;
          }));
          renderNotifs();
          return;
        }
        var added = window.addNotif(
          title, msg, 'warning', 'fa-certificate', 'ssl-cert', actionUrl
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

    // Hide sidebar button immediately only when cert is acked AND on HTTPS
    // (cert already installed — no action needed). On HTTP or unacked HTTPS,
    // leave it visible until the async cert-status fetch decides.
    (function () {
      if (window.location.protocol === 'https:') {
        var acked = parseFloat(localStorage.getItem(LS_KEY) || '0');
        if (acked > 0) hideSidebarBtn(); // may be overridden after fetch if cert renewed
      }
      // On HTTP: never hide the sidebar button upfront — always leave it accessible
    })();

    setTimeout(checkSslCert, 2000);
    setInterval(checkSslCert, SSL_POLL_MS);
  })();

  // ── TR Overdue / Warning Notifications ───────────────────────────────────
  // Polls every 5 minutes.
  // overdue  → return_by has passed       → red  danger notification
  // warning  → return_by within 2 hours   → amber warning notification
  // Auto-removed when the log is resolved (status → Closed).
  if (document.body.dataset.poll === '1') {
    (function () {
      var TR_OVERDUE_URL  = '/transactions/api/overdue-tr/';
      var TR_POLL_MS      = 5 * 60 * 1000; // 5 minutes
      var OVERDUE_PREFIX  = 'tr-overdue-';
      var WARNING_PREFIX  = 'tr-warning-';

      function fmtDeadline(iso) {
        if (!iso) return '';
        var d = new Date(iso);
        var mo = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][d.getMonth()];
        return mo + ' ' + d.getDate() + ', ' + d.getFullYear() + ' ' +
               String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
      }

      function updateNotif(nid, msg) {
        saveNotifs(getNotifs().map(function (n) {
          return n.id === nid ? Object.assign({}, n, { unread: true, msg: msg }) : n;
        }));
        window.renderNotifs();
      }

      function pollOverdueTR() {
        fetch(TR_OVERDUE_URL, {
          credentials: 'same-origin',
          headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          if (!data) return;

          var overdueIds = (data.overdue || []).map(function (o) { return OVERDUE_PREFIX + o.id; });
          var warningIds = (data.warning || []).map(function (o) { return WARNING_PREFIX + o.id; });
          var allActive  = overdueIds.concat(warningIds);

          // Remove notifications for logs that are now resolved or no longer active
          getNotifs().filter(function (n) {
            return n.id &&
                   (n.id.indexOf(OVERDUE_PREFIX) === 0 || n.id.indexOf(WARNING_PREFIX) === 0) &&
                   allActive.indexOf(n.id) === -1;
          }).forEach(function (n) { window.removeNotifById(n.id); });

          // ── Overdue (red) ────────────────────────────────────────────────
          (data.overdue || []).forEach(function (log) {
            var nid = OVERDUE_PREFIX + log.id;
            var msg = log.personnel + ' \u2014 ' + log.items.join(', ') +
                      ' \u00b7 ' + log.hours_overdue + 'h overdue' +
                      ' \u00b7 Was due: ' + fmtDeadline(log.return_by) +
                      ' (' + log.status + ')';
            // If there was a warning notif for this log, replace it
            window.removeNotifById(WARNING_PREFIX + log.id);
            if (getNotifs().some(function (n) { return n.id === nid; })) {
              updateNotif(nid, msg);
            } else {
              window.addNotif(
                'TR Overdue \u2014 Return Required', msg,
                'danger', 'fa-circle-exclamation', nid,
                log.transaction_id ? ('/transactions/' + log.transaction_id + '/') : ('/transactions/?search=' + encodeURIComponent(log.personnel))
              );
            }
          });

          // ── Warning / approaching deadline (amber) ───────────────────────
          (data.warning || []).forEach(function (log) {
            var nid = WARNING_PREFIX + log.id;
            var msg = log.personnel + ' \u2014 ' + log.items.join(', ') +
                      ' \u00b7 Due in ' + log.minutes_left + ' min' +
                      ' \u00b7 Return by: ' + fmtDeadline(log.return_by) +
                      ' (' + log.status + ')';
            if (getNotifs().some(function (n) { return n.id === nid; })) {
              updateNotif(nid, msg);
            } else {
              window.addNotif(
                'TR Return Deadline Approaching', msg,
                'warning', 'fa-clock', nid,
                log.transaction_id ? ('/transactions/' + log.transaction_id + '/') : ('/transactions/?search=' + encodeURIComponent(log.personnel))
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

// ── 5. PJAX — smooth client-side navigation ──────────────────────────────────
// Intercepts same-origin link clicks, fetches the target page, and swaps only
// the changing parts of the DOM so the sidebar/notifications never reload.
// Page-specific scripts are removed and re-added on each navigation so they
// always initialise against fresh DOM nodes.
(function () {
  if (!window.fetch || !window.history || !window.DOMParser) return;

  var ORIGIN = window.location.origin;

  // ── Progress bar ────────────────────────────────────────────────────────
  var _bar = null, _barTimer = null;

  function _barEl() {
    if (_bar) return _bar;
    _bar = document.createElement('div');
    _bar.style.cssText =
      'position:fixed;top:0;left:0;height:3px;width:0;z-index:10000;pointer-events:none;' +
      'background:var(--primary,#4f8ef7);opacity:0;';
    document.body.appendChild(_bar);
    return _bar;
  }

  function showBar() {
    var b = _barEl();
    clearTimeout(_barTimer);
    b.style.transition = 'none';
    b.style.width = '0';
    b.style.opacity = '1';
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        b.style.transition = 'width 1.5s cubic-bezier(0.1,0.7,0.1,1)';
        b.style.width = '70%';
      });
    });
  }

  function doneBar() {
    var b = _barEl();
    clearTimeout(_barTimer);
    b.style.transition = 'width .1s ease-out';
    b.style.width = '100%';
    _barTimer = setTimeout(function () {
      b.style.transition = 'opacity .3s';
      b.style.opacity = '0';
      setTimeout(function () { b.style.width = '0'; b.style.transition = 'none'; }, 350);
    }, 100);
  }

  // ── Helpers ─────────────────────────────────────────────────────────────
  function isSameOrigin(url) {
    try { return new URL(url, ORIGIN).origin === ORIGIN; } catch (e) { return false; }
  }

  function shouldSkip(a) {
    var href = a.getAttribute('href') || '';
    if (!href || /^(#|javascript:|mailto:|tel:)/i.test(href)) return true;
    if (a.hasAttribute('download')) return true;
    var tgt = (a.getAttribute('target') || '').toLowerCase();
    if (tgt && tgt !== '_self') return true;
    if (!isSameOrigin(a.href)) return true;
    var path = new URL(a.href, ORIGIN).pathname;
    // Skip admin, media, static, API, auth, cert-download paths
    if (/^\/(admin|media|static|api)\//i.test(path)) return true;
    if (/^\/(logout|accounts|download)\//i.test(path)) return true;
    // Skip direct file downloads
    if (/\.(pdf|png|jpg|jpeg|gif|csv|zip|xlsx|docx|crt|pem|cer)$/i.test(path)) return true;
    return false;
  }

  // ── Slot swap ────────────────────────────────────────────────────────────
  // Replaces innerHTML of element #id in the live document with the matching
  // element from the freshly-parsed document (or clears it if absent).
  function swapSlot(id, newDoc) {
    var cur = document.getElementById(id);
    var nxt = newDoc.getElementById(id);
    if (!cur) return;
    cur.innerHTML = nxt ? nxt.innerHTML : '';
  }
  // Special swap for the extra-css slot: explicitly create <style> elements so
  // the browser reliably applies them (innerHTML style injection can be skipped
  // by some engines when the content is set synchronously alongside a DOM swap).
  function swapExtraCSS(newDoc) {
    var cur = document.getElementById('pjax-extra-css');
    if (!cur) return;
    // Remove existing injected styles
    cur.innerHTML = '';
    var nxt = newDoc.getElementById('pjax-extra-css');
    if (!nxt) return;
    nxt.querySelectorAll('style').forEach(function (orig) {
      var s = document.createElement('style');
      s.textContent = orig.textContent;
      cur.appendChild(s);
    });
  }
  // ── Script management ───────────────────────────────────────────────────
  // done() is called once every src-based script from newDoc has loaded and
  // executed (or errored).  Inline data-block scripts are injected synchronously
  // and do not count toward the pending total.
  function reloadBodyScripts(newDoc, done) {
    // Remove every <script> that lives as a direct child of <body>,
    // EXCEPT scripts marked data-pjax-permanent (e.g. hot_key.js) — those
    // must only ever execute once; re-executing them accumulates duplicate
    // event listeners that can never be cleaned up.
    document.querySelectorAll('body > script:not([data-pjax-permanent])').forEach(function (s) { s.remove(); });

    // Collect src-based scripts so we can track when each one has executed.
    // Dynamically inserted <script src> elements are always async regardless of
    // the async attribute — setting async=false only controls insertion order.
    // We therefore use onload/onerror to know when each script has actually run
    // before we call done() and mark the PJAX navigation complete.
    var pending = [];
    newDoc.querySelectorAll('body > script:not([data-pjax-permanent])').forEach(function (orig) {
      var src  = orig.getAttribute('src');
      var type = orig.getAttribute('type') || '';

      if (!src) {
        // Inline executable scripts (no type / type=text/javascript) violate
        // CSP script-src 'self' — skip them entirely.
        // Data blocks (type=application/json etc.) are safe: re-inject with
        // their original type so the browser never tries to execute them.
        if (!type || /^(text\/javascript|module)$/i.test(type)) return;
        var d = document.createElement('script');
        d.type = type;
        if (orig.id) d.id = orig.id;
        d.textContent = orig.textContent;
        document.body.appendChild(d);
        return;
      }

      var s = document.createElement('script');
      s.src = src;   // browser resolves relative src against current document
      s.async = false;
      pending.push(s);
    });

    if (!pending.length) { if (done) done(); return; }

    var remaining = pending.length;
    function onScriptDone() { if (--remaining === 0 && done) done(); }
    pending.forEach(function (s) {
      s.addEventListener('load',  onScriptDone);
      s.addEventListener('error', onScriptDone); // don't hang if a script 404s
      document.body.appendChild(s);
    });
  }

  // ── Sidebar active-state sync ───────────────────────────────────────────
  function updateSidebarActive(pathname) {
    // Top-level nav-item anchors (dashboard, personnel, transactions, print, etc.)
    document.querySelectorAll('.sidebar .nav-item[href]').forEach(function (a) {
      var aPath;
      try { aPath = new URL(a.href, ORIGIN).pathname; } catch (e) { return; }
      a.classList.toggle('active', aPath === pathname);
    });
    // Flyout pop-out links (shown on hover when sidebar is collapsed)
    document.querySelectorAll('.sidebar .nav-flyout a[href]').forEach(function (a) {
      var aPath;
      try { aPath = new URL(a.href, ORIGIN).pathname; } catch (e) { return; }
      a.classList.toggle('active', aPath === pathname);
    });
    // Inventory nav-sub rows — active class lives on the wrapper div, not the anchor
    document.querySelectorAll('.sidebar .nav-sub .nav-item-row').forEach(function (row) {
      var link = row.querySelector('a.nav-item-main[href]');
      if (!link) return;
      var linkPath;
      try { linkPath = new URL(link.href, ORIGIN).pathname; } catch (e) { return; }
      row.classList.toggle('active', linkPath === pathname);
    });
    // Open nav-groups whose sub/flyout contains the active link.
    document.querySelectorAll('.nav-group').forEach(function (g) {
      if (g.querySelector('a.active') || g.querySelector('.nav-item-row.active')) {
        g.classList.add('open');
      }
    });
    // User-block avatar link (profile pages)
    var userBlock = document.querySelector('.sidebar-footer .user-block');
    if (userBlock) {
      var ubPath;
      try { ubPath = new URL(userBlock.href, ORIGIN).pathname; } catch (e) { ubPath = ''; }
      userBlock.classList.toggle('active', pathname.startsWith('/profile'));
    }
  }

  // ── Navigate ─────────────────────────────────────────────────────────────
  var _busy = false;

  function navigate(url, pushState) {
    if (_busy) return;
    _busy = true;
    showBar();

    // Abort listeners from the current page's scripts, then arm a fresh signal
    // for the incoming page's scripts.
    var oldCtl = window.pjaxController;
    window.pjaxController = new AbortController();
    oldCtl.abort();

    fetch(url, {
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
    .then(function (res) {
      // Redirect to a different origin (e.g. login) → full navigation
      if (res.redirected && !res.url.startsWith(ORIGIN)) {
        window.location.href = res.url;
        return null;
      }
      // Same-origin redirect (e.g. session expired → /login/) → follow it
      if (res.redirected && res.url !== url) {
        window.location.href = res.url;
        return null;
      }
      var ct = res.headers.get('Content-Type') || '';
      if (!res.ok || ct.indexOf('text/html') === -1) {
        window.location.href = url;
        return null;
      }
      return res.text();
    })
    .then(function (html) {
      if (!html) { doneBar(); _busy = false; return; }

      var doc;
      try { doc = new DOMParser().parseFromString(html, 'text/html'); }
      catch (e) { window.location.href = url; doneBar(); _busy = false; return; }

      // If the new page is a standalone (no #main-content — e.g. print preview, PDF viewer),
      // fall back to full navigation so it renders correctly.
      if (!doc.getElementById('main-content')) {
        window.location.href = url;
        doneBar(); _busy = false; return;
      }

      // Update page title
      document.title = doc.title;

      // Swap the four topbar dynamic slots + the main content area
      swapSlot('pjax-title',     doc);
      swapSlot('pjax-sub',       doc);
      swapSlot('pjax-actions',   doc);
      swapSlot('pjax-submit',    doc);
      swapExtraCSS(doc);
      swapSlot('main-content',   doc);

      // Sync body data attributes (e.g. data-collapse-sidebar for txn form)
      var wasAutoCollapsed = document.body.dataset.collapseSidebar === '1';
      document.body.dataset.collapseSidebar = doc.body.dataset.collapseSidebar || '';
      if (doc.body.dataset.collapseSidebar === '1') {
        // Entering transaction form — auto-collapse sidebar
        if (!document.body.classList.contains('sidebar-collapsed')) {
          document.body.classList.add('sidebar-collapsed');
        }
      } else if (wasAutoCollapsed) {
        // Leaving transaction form — restore user's own saved preference
        if (localStorage.getItem('sidebarCollapsed') !== 'true') {
          document.body.classList.remove('sidebar-collapsed');
        }
      }

      // Sync sidebar active state
      try { updateSidebarActive(new URL(url, ORIGIN).pathname); } catch (e) {}

      // Re-initialise page-specific scripts for the new content.
      // doneBar() / _busy=false are deferred until all scripts have executed
      // so the form is fully interactive before the progress bar disappears
      // and before new PJAX navigations are allowed.
      reloadBodyScripts(doc, function () {
        if (pushState) history.pushState({ pjax: url }, doc.title, url);
        window.scrollTo(0, 0);
        doneBar();
        _busy = false;
      });
    })
    .catch(function () {
      window.location.href = url;
      doneBar();
      _busy = false;
    });
  }

  // Expose navigate so other scripts (e.g. calendar_widget.js) can trigger
  // PJAX navigation without a full reload.
  window.pjaxNavigate = navigate;

  // ── Intercept link clicks ───────────────────────────────────────────────
  document.addEventListener('click', function (e) {
    // Let modifier-key clicks open in new tab/window normally
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target.closest('a[href]');
    if (!a || shouldSkip(a)) return;
    e.preventDefault();
    var url = a.href;
    if (url === window.location.href) { window.scrollTo(0, 0); return; }
    // Check navigation guard (e.g. unsaved transaction form data).
    if (typeof window._pjaxNavigationGuard === 'function') {
      if (!window._pjaxNavigationGuard()) return;
      window._pjaxNavigationGuard = null;
    }
    navigate(url, true);
  });

  // ── Back / Forward ───────────────────────────────────────────────────────
  window.addEventListener('popstate', function (e) {
    if (e.state && e.state.pjax) {
      // Check navigation guard before PJAX Back/Forward navigation.
      if (typeof window._pjaxNavigationGuard === 'function') {
        if (!window._pjaxNavigationGuard()) {
          // User cancelled — push the current URL back into history to restore
          // the address bar to the transaction form URL.
          history.pushState({ pjax: e.state.pjax }, document.title, e.state.pjax);
          return;
        }
        window._pjaxNavigationGuard = null;
      }
      navigate(window.location.href, false);
    }
  });

  // Save initial state so popstate fires correctly on first back-navigation
  history.replaceState({ pjax: window.location.href }, document.title, window.location.href);
})();
