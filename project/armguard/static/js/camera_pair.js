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

  var statusUrl = cfg.statusUrl;
  var logsUrl   = cfg.logsUrl;
  var pinUrl    = cfg.pinUrl;
  var wasActive = cfg.wasActive;
  var reloaded  = false;

  var statusEl    = document.getElementById('dev-info-status');
  var activatedEl = document.getElementById('dev-info-activated');
  var seenEl      = document.getElementById('dev-info-seen');
  var lockRow     = document.getElementById('dev-info-lock-row');
  var lockUntilEl = document.getElementById('dev-info-locked-until');
  var logsTbody   = document.getElementById('pair-logs-tbody');
  var logsCountEl = document.getElementById('pair-logs-count');
  var liveEl      = document.getElementById('pair-live');
  var logsEmpty   = document.getElementById('pair-logs-empty');
  var knownPks    = {};

  // ── PIN display ──────────────────────────────────────────────────────────
  var pinDisplay  = document.getElementById('pin-display');
  var pinBar      = document.getElementById('pin-bar');
  var pinCountEl  = document.getElementById('pin-countdown');
  var pinExpiresAt = 0;

  function refreshPin() {
    if (!pinDisplay) return;
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
        if (pinCountEl) pinCountEl.textContent = '30s';
      })
      .catch(function (err) {
        console.error('PIN fetch error:', err);
        if (pinDisplay) pinDisplay.textContent = 'err';
        setTimeout(refreshPin, 3000);
      });
  }

  function tickPin() {
    if (!pinDisplay) return;
    if (!pinExpiresAt) {
      if (pinBar) pinBar.style.width = '100%';
      return;
    }
    var now       = Date.now();
    var remaining = Math.max(0, (pinExpiresAt - now) / 1000);
    if (pinCountEl) pinCountEl.textContent = Math.ceil(remaining) + 's';
    if (pinBar)     pinBar.style.width = (remaining / 30 * 100).toFixed(1) + '%';
    if (remaining <= 0) refreshPin();
  }

  if (pinDisplay) {
    refreshPin();
    setInterval(tickPin, 250);
  }

  // ── Live flash ───────────────────────────────────────────────────────────
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
        if (d.is_active && !wasActive && !reloaded) {
          reloaded = true;
          window.location.reload();
          return;
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

  // ── Boot ─────────────────────────────────────────────────────────────────
  pollStatus();
  refreshLogs();
  setInterval(pollStatus,  5000);
  setInterval(refreshLogs, 5000);
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') { pollStatus(); refreshLogs(); refreshPin(); }
  });
})();
