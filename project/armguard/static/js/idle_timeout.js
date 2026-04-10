/**
 * idle_timeout.js — ArmGuard RDS
 *
 * Tracks user activity (mouse, keyboard, touch, scroll).
 * After IDLE_TIMEOUT seconds of inactivity, shows a warning modal
 * with a 60-second countdown.  If the user does not interact before
 * the countdown reaches zero, the browser is redirected to the logout
 * URL — no page refresh required.
 *
 * Configuration is read from <body> attributes set by base.html:
 *   data-idle-timeout  — inactivity limit in seconds (default 1800)
 *   data-logout-url    — URL to POST logout to (default /logout/)
 */
(function () {
  'use strict';

  var body       = document.body;
  var IDLE_LIMIT = parseInt(body.getAttribute('data-idle-timeout') || '1800', 10) * 1000;
  var LOGOUT_URL = body.getAttribute('data-logout-url') || '/logout/';
  var WARN_BEFORE = 60 * 1000;   // show warning 60 s before forced logout
  var TICK_MS     = 1000;

  // Only run when a user is actually logged in
  if (!body.hasAttribute('data-idle-timeout')) return;

  var idleTimer    = null;
  var warnTimer    = null;
  var countdownInt = null;
  var modalShown   = false;

  // ── Build modal HTML (injected once) ──────────────────────────────────────
  var modal = document.createElement('div');
  modal.id  = 'idle-timeout-modal';
  modal.setAttribute('role', 'alertdialog');
  modal.setAttribute('aria-modal', 'true');
  modal.setAttribute('aria-labelledby', 'idle-modal-title');
  modal.style.cssText = [
    'display:none',
    'position:fixed',
    'inset:0',
    'z-index:9999',
    'background:rgba(0,0,0,.65)',
    'align-items:center',
    'justify-content:center',
  ].join(';');

  modal.innerHTML =
    '<div style="background:var(--surface,#1e2128);border:1px solid var(--border,rgba(255,255,255,.1));border-radius:10px;padding:2rem;width:100%;max-width:380px;box-shadow:0 8px 32px rgba(0,0,0,.5)">' +
      '<div style="display:flex;align-items:center;gap:.75rem;margin-bottom:1rem">' +
        '<i class="fa-solid fa-clock" style="font-size:1.4rem;color:var(--warning,#f59e0b)"></i>' +
        '<h3 id="idle-modal-title" style="margin:0;font-size:1rem;font-weight:600;color:var(--text,#e2e8f0)">Session Expiring Soon</h3>' +
      '</div>' +
      '<p style="margin:0 0 1.25rem;color:var(--text-secondary,#94a3b8);font-size:.88rem;line-height:1.5">' +
        'You have been inactive. You will be automatically logged out in ' +
        '<strong id="idle-countdown" style="color:var(--danger,#ef4444)">60</strong> seconds.' +
      '</p>' +
      '<div style="display:flex;gap:.75rem">' +
        '<button id="idle-stay-btn" class="btn btn-primary" style="flex:1">' +
          '<i class="fa-solid fa-rotate-right"></i> Stay Logged In' +
        '</button>' +
        '<button id="idle-logout-btn" class="btn btn-secondary" style="flex:1;color:var(--danger,#ef4444)">' +
          '<i class="fa-solid fa-arrow-right-from-bracket"></i> Log Out Now' +
        '</button>' +
      '</div>' +
    '</div>';

  document.body.appendChild(modal);

  var countdownEl = document.getElementById('idle-countdown');
  var stayBtn     = document.getElementById('idle-stay-btn');
  var logoutBtn   = document.getElementById('idle-logout-btn');

  // ── Actions ───────────────────────────────────────────────────────────────
  function getCsrf() {
    var el = document.querySelector('[name=csrfmiddlewaretoken]');
    if (el) return el.value;
    var m = document.cookie.match('(?:^|;)\\s*csrftoken=([^;]+)');
    return m ? decodeURIComponent(m[1]) : '';
  }

  function doLogout() {
    // POST to logout so the session is properly terminated server-side
    var form = document.createElement('form');
    form.method = 'post';
    form.action = LOGOUT_URL;
    var csrf = document.createElement('input');
    csrf.type  = 'hidden';
    csrf.name  = 'csrfmiddlewaretoken';
    csrf.value = getCsrf();
    form.appendChild(csrf);
    document.body.appendChild(form);
    form.submit();
  }

  function hideModal() {
    modal.style.display = 'none';
    modalShown = false;
    clearInterval(countdownInt);
    countdownInt = null;
  }

  function showWarning() {
    if (modalShown) return;
    modalShown = true;
    modal.style.display = 'flex';

    var remaining = Math.round(WARN_BEFORE / 1000);
    countdownEl.textContent = remaining;

    countdownInt = setInterval(function () {
      remaining -= 1;
      countdownEl.textContent = Math.max(remaining, 0);
      if (remaining <= 0) {
        clearInterval(countdownInt);
        countdownInt = null;
        doLogout();
      }
    }, TICK_MS);
  }

  function resetIdle() {
    // If warning is showing, dismiss it and restart the timers
    if (modalShown) {
      hideModal();
    }
    clearTimeout(idleTimer);
    clearTimeout(warnTimer);

    // Schedule the warning WARN_BEFORE ms before the limit
    var warnDelay = IDLE_LIMIT - WARN_BEFORE;
    if (warnDelay > 0) {
      warnTimer = setTimeout(showWarning, warnDelay);
    }
    // Schedule forced logout at the full limit
    idleTimer = setTimeout(doLogout, IDLE_LIMIT);
  }

  // ── Activity listeners ────────────────────────────────────────────────────
  var ACTIVITY_EVENTS = ['mousemove', 'mousedown', 'keydown', 'touchstart', 'scroll', 'click'];
  var _resetThrottle = null;

  function onActivity() {
    // Throttle resets to once per second to avoid hammering setTimeout/clearTimeout
    if (_resetThrottle) return;
    _resetThrottle = setTimeout(function () {
      _resetThrottle = null;
      if (!modalShown) resetIdle();
    }, 1000);
  }

  ACTIVITY_EVENTS.forEach(function (evt) {
    document.addEventListener(evt, onActivity, { passive: true, capture: true });
  });

  // ── Button handlers ───────────────────────────────────────────────────────
  stayBtn.addEventListener('click', function () {
    hideModal();
    resetIdle();
    // Ping server to refresh session cookie expiry
    fetch('/users/ping/', { method: 'POST', credentials: 'same-origin',
      headers: { 'X-CSRFToken': getCsrf(), 'X-Requested-With': 'XMLHttpRequest' }
    }).catch(function () {});
  });

  logoutBtn.addEventListener('click', doLogout);

  // ── Start ─────────────────────────────────────────────────────────────────
  resetIdle();
})();
