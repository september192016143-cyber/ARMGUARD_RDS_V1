/**
 * camera_pair.js
 * F-CSP: Extracted from pair.html inline <script> to comply with CSP script-src 'self'.
 * Handles: live device status polling, recent-uploads log feed, rotating PIN display.
 *
 * Page data is passed via <script type="application/json" id="pair-page-data">
 * so no Django template tags are needed in this file.
 */
(function () {
  var dataEl = document.getElementById('pair-page-data');
  if (!dataEl) return;
  var cfg;
  try { cfg = JSON.parse(dataEl.textContent); } catch (e) { return; }

  var statusUrl  = cfg.statusUrl;
  var logsUrl    = cfg.logsUrl;
  var pinUrl     = cfg.pinUrl;
  var pairUrl    = cfg.pairUrl;
  var wasActive  = cfg.wasActive;

  var statusEl      = document.getElementById('dev-info-status');
  var activatedEl   = document.getElementById('dev-info-activated');
  var seenEl        = document.getElementById('dev-info-seen');
  var lockRow       = document.getElementById('dev-info-lock-row');
  var lockUntilEl   = document.getElementById('dev-info-locked-until');
  var qrBadgeEl     = document.getElementById('qr-status-badge');
  var pinBoxEl      = document.getElementById('pin-box');
  var labelFormEl  = document.getElementById('label-form');
  var labelInputEl = document.getElementById('label-input');
  var labelSaveBtn = document.getElementById('label-save-btn');
  var labelDisplay = document.getElementById('label-display');
  var labelInfoEl  = document.getElementById('dev-info-label');
  var logsTbody     = document.getElementById('pair-logs-tbody');
  var logsCountEl   = document.getElementById('pair-logs-count');
  var liveEl        = document.getElementById('pair-live');
  var logsEmpty     = document.getElementById('pair-logs-empty');
  var knownPks      = {};
  var pollTimer     = null;

  // ── PIN display ──────────────────────────────────────────────────────────
  var pinDisplay   = document.getElementById('pin-display');
  var pinBar       = document.getElementById('pin-bar');
  var pinCountEl   = document.getElementById('pin-countdown');
  // Pre-seed expiry from server-rendered value — countdown starts immediately, no fetch needed on load
  var pinExpiresAt  = cfg.initialPinExpiresMs || 0;
  var pinRefreshing = false;  // guard: only one in-flight fetch at a time

  function refreshPin() {
    if (!pinDisplay || pinRefreshing) return;
    pinRefreshing = true;
    // Optimistically push expiry forward so tickPin stops firing during the fetch
    pinExpiresAt = Date.now() + 30000;
    fetch(pinUrl, { credentials: 'same-origin' })
      .then(function (r) {
        if (!r.ok) {
          console.error('PIN API returned HTTP ' + r.status + ' for ' + pinUrl);
          pinDisplay.textContent = 'HTTP\u00a0' + r.status;
          if (pinCountEl) pinCountEl.textContent = 'err';
          return null;
        }
        return r.json();
      })
      .then(function (json) {
        if (!json || !json.pin) return;
        pinDisplay.textContent = json.pin;
        pinExpiresAt = json.expires_ms;
      })
      .catch(function (err) {
        console.error('PIN fetch error:', err);
        if (pinDisplay) pinDisplay.textContent = 'err';
        pinExpiresAt = Date.now() + 3000;  // retry in 3s via tickPin
      })
      .finally(function () { pinRefreshing = false; });
  }

  function tickPin() {
    if (!pinDisplay) return;
    var now       = Date.now();
    var remaining = pinExpiresAt ? Math.max(0, (pinExpiresAt - now) / 1000) : 30;
    if (pinCountEl) pinCountEl.textContent = Math.ceil(remaining) + 's';
    if (pinBar)     pinBar.style.width = (Math.min(remaining, 30) / 30 * 100).toFixed(1) + '%';
    if (remaining <= 0) refreshPin();
  }

  if (pinDisplay) {
    setInterval(tickPin, 250);
  }

  // ── Toast notification ───────────────────────────────────────────────────
  function showToast(msg, color) {
    var t = document.createElement('div');
    t.textContent = msg;
    t.style.cssText = 'position:fixed;top:1.2rem;right:1.2rem;z-index:9999;' +
      'background:' + (color || '#052e16') + ';color:#4ade80;border:1px solid #166534;' +
      'border-radius:.6rem;padding:.65rem 1.1rem;font-size:.85rem;font-weight:600;' +
      'box-shadow:0 4px 16px rgba(0,0,0,.4);transition:opacity .5s;';
    document.body.appendChild(t);
    setTimeout(function () { t.style.opacity = '0'; }, 2800);
    setTimeout(function () { t.remove(); }, 3300);
  }

  // ── Adaptive polling control ─────────────────────────────────────────────
  function setAdaptivePoll(isActive) {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(pollStatus, isActive ? 5000 : 2000);
  }

  function flash() {
    if (!liveEl) return;
    liveEl.style.opacity = '1';
    setTimeout(function () { liveEl.style.opacity = '.4'; }, 600);
  }

  // ── Device status poll ───────────────────────────────────────────────────
  function pollStatus() {
    fetch(statusUrl, { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.found) return;
        flash();

        // Device just became active — update everything in-place (no reload)
        if (d.is_active && !wasActive) {
          wasActive = true;
          setAdaptivePoll(true);  // slow down to 5s now that it's active

          // Update QR status badge
          if (qrBadgeEl) {
            qrBadgeEl.style.cssText = 'background:#052e16;border-radius:.6rem;padding:.6rem;margin-bottom:1rem;font-size:.82rem;color:#4ade80;';
            qrBadgeEl.innerHTML = '&#9679; Active &mdash; last seen ' + (d.last_seen || 'just now');
          }
          // Show PIN box and start displaying the PIN
          if (pinBoxEl) {
            pinBoxEl.style.display = 'block';
            pinBoxEl.style.animation = 'cam-fadein .4s ease';
            if (pinDisplay) refreshPin();
          }
          // Show success toast
          showToast('\u2713 Device activated!');
        }

        if (statusEl) {
          if (d.revoked) { statusEl.style.color = '#f87171'; statusEl.textContent = 'Revoked'; }
          else if (d.is_active) { statusEl.style.color = '#4ade80'; statusEl.textContent = 'Active'; }
          else { statusEl.style.color = '#fbbf24'; statusEl.textContent = 'Pending activation'; }
        }
        if (activatedEl) activatedEl.textContent = d.activated_at || '\u2014';
        if (seenEl)      seenEl.textContent = d.last_seen || '\u2014';
        if (lockRow)     lockRow.style.display = d.locked ? 'table-row' : 'none';
        if (lockUntilEl && d.locked_until) lockUntilEl.textContent = d.locked_until;
      })
      .catch(function () {});
  }

  // ── Upload log feed ──────────────────────────────────────────────────────
  function formatBytes(b) {
    return b < 1024 ? b + ' B' : b < 1048576 ? (b / 1024).toFixed(1) + ' KB' : (b / 1048576).toFixed(1) + ' MB';
  }

  function refreshLogs() {
    if (!logsTbody) return;
    fetch(logsUrl, { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (json) {
        if (logsCountEl) logsCountEl.textContent = json.count;
        if (json.count === 0) {
          if (logsEmpty) logsEmpty.querySelector('td').textContent = 'No uploads yet.';
          return;
        }
        var added = 0;
        json.logs.forEach(function (log) {
          if (knownPks[log.pk]) return;
          knownPks[log.pk] = true;
          added++;
          if (logsEmpty) { logsEmpty.remove(); logsEmpty = null; }
          var tr = document.createElement('tr');
          tr.style.cssText = 'border-bottom:1px solid #1e293b;animation:cam-fadein .4s ease;';
          tr.innerHTML =
            '<td style="padding:.5rem .75rem;color:#94a3b8;font-size:.78rem;white-space:nowrap;">' + log.uploaded_at + '</td>' +
            '<td style="padding:.5rem .75rem;color:#94a3b8;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="' + log.original_name + '">' + log.original_name + '</td>' +
            '<td style="padding:.5rem .75rem;color:#94a3b8;white-space:nowrap;">' + formatBytes(log.file_size_bytes) + '</td>' +
            '<td style="padding:.5rem .75rem;"><a href="' + log.file_url + '" target="_blank" rel="noopener" style="color:#93c5fd;font-size:.78rem;text-decoration:none;">View</a></td>' +
            '<td style="padding:.5rem .75rem;color:#64748b;font-size:.72rem;">' + log.ip_address + '</td>';
          logsTbody.insertBefore(tr, logsTbody.firstChild);
        });
        if (added > 0) flash();
      })
      .catch(function () {});
  }

  // ── CSRF helper ──────────────────────────────────────────────────────────
  function getCsrf() {
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? match[1] : '';
  }

  // ── Device Label AJAX save ────────────────────────────────────────────────
  if (labelFormEl && labelInputEl) {
    labelFormEl.addEventListener('submit', function (e) {
      e.preventDefault();
      var newLabel = labelInputEl.value.trim().slice(0, 100);
      if (labelSaveBtn) { labelSaveBtn.disabled = true; labelSaveBtn.textContent = 'Saving…'; }

      var body = new URLSearchParams();
      body.append('action', 'set_name');
      body.append('device_name', newLabel);
      body.append('csrfmiddlewaretoken', getCsrf());

      fetch(pairUrl, {
        method:      'POST',
        credentials: 'same-origin',
        headers:     { 'Content-Type': 'application/x-www-form-urlencoded',
                       'X-CSRFToken':  getCsrf() },
        body:        body.toString(),
      })
        .then(function (r) {
          if (r.ok || r.redirected) {
            // Update all label display elements in-place
            var display = newLabel || '—';
            if (labelInfoEl) labelInfoEl.textContent = display;
            if (labelDisplay) {
              if (newLabel) {
                labelDisplay.textContent = '\uD83C\uDFF7\uFE0F ' + newLabel;
                labelDisplay.style.display = '';
              } else {
                labelDisplay.style.display = 'none';
              }
            }
            showToast('\u2713 Label saved');
          } else {
            showToast('Save failed (' + r.status + ')', '#450a0a');
          }
        })
        .catch(function () { showToast('Save failed — network error', '#450a0a'); })
        .finally(function () {
          if (labelSaveBtn) { labelSaveBtn.disabled = false; labelSaveBtn.textContent = 'Save'; }
        });
    });
  }

  // ── Boot ─────────────────────────────────────────────────────────────────
  pollStatus();
  refreshLogs();
  setAdaptivePoll(wasActive);   // 2s if pending, 5s if already active
  setInterval(refreshLogs, 5000);
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') {
      pollStatus();
      refreshLogs();
      // Refresh PIN if it has expired or is about to while the tab was hidden
      if (pinDisplay && pinExpiresAt && Date.now() >= pinExpiresAt - 500) {
        pinExpiresAt = 0;  // force tickPin to call refreshPin immediately
      }
    }
  });
  // bfcache restore (browser Back/Forward)
  window.addEventListener('pageshow', function (e) {
    if (e.persisted) {
      pinExpiresAt = 0;  // force a fresh fetch — PIN may have expired while frozen
      pinRefreshing = false;
      pollStatus();
      refreshLogs();
      refreshPin();
    }
  });
})();
