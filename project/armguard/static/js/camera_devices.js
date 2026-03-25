/* camera_devices.js — live-poll driver for /camera/admin/devices/
 *
 * Loaded via {% block extra_js %} so PJAX re-executes it on every
 * navigation (unlike inline scripts inside {% block content %} which
 * are swapped via innerHTML and never re-run).
 *
 * Config is read from a <script type="application/json" id="cam-device-list-data">
 * block rendered in {% block extra_js %} alongside this script.
 */
(function () {
  var cfgEl = document.getElementById('cam-device-list-data');
  if (!cfgEl) return;
  var cfg         = JSON.parse(cfgEl.textContent);
  var devFeedUrl  = cfg.devicesFeedUrl;
  var logsFeedUrl = cfg.logsFeedUrl;

  var liveEl      = document.getElementById('cam-live');
  var logsTbody   = document.getElementById('logs-table-body');
  var logsCountEl = document.getElementById('logs-count');
  var logsEmpty   = document.getElementById('logs-empty-row');
  var knownPks    = {};

  function flash() {
    if (!liveEl) return;
    liveEl.style.opacity = '1';
    setTimeout(function () { liveEl.style.opacity = '.4'; }, 600);
  }

  function statusHtml(d) {
    if (d.revoked)
      return '<span style="color:#f87171;">&#9632; Revoked</span>';
    if (d.is_active) {
      var h = '<span style="color:#4ade80;">&#9679; Active</span>';
      if (d.locked)
        h += '<br><span style="color:#fbbf24;font-size:.75rem;">&#128274; Locked until ' + d.locked_until + '</span>';
      return h;
    }
    return '<span style="color:#fbbf24;">&#9203; Pending</span>';
  }

  function refreshDevices() {
    fetch(devFeedUrl, { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (json) {
        flash();
        json.devices.forEach(function (d) {
          var row = document.querySelector('tr[data-dev-pk="' + d.pk + '"]');
          if (!row) return;
          var stTd = row.querySelector('td[data-cell="status"]');
          if (stTd) stTd.innerHTML = statusHtml(d);
          var seenTd = row.querySelector('td[data-cell="seen"]');
          if (seenTd) seenTd.innerHTML = d.last_seen
            ? '<span style="color:#94a3b8;">' + d.last_seen + '</span>'
            : '&mdash;';
          var failTd = row.querySelector('td[data-cell="failed"]');
          if (failTd) failTd.innerHTML = d.failed_attempts > 0
            ? '<span style="color:#f87171;">' + d.failed_attempts + '</span>'
            : '<span style="color:#4ade80;">0</span>';
        });
      })
      .catch(function () {});
  }

  function formatBytes(b) {
    return b < 1024 ? b + ' B' : b < 1048576 ? (b / 1024).toFixed(1) + ' KB' : (b / 1048576).toFixed(1) + ' MB';
  }

  function refreshLogs() {
    if (!logsTbody) return;
    fetch(logsFeedUrl, { credentials: 'same-origin' })
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
          var viewCell = log.file_purged
            ? '<span style="color:#475569;font-size:.78rem;">Purged</span>'
            : '<a href="' + log.file_url + '" target="_blank" rel="noopener" style="color:#93c5fd;font-size:.78rem;text-decoration:none;">View</a>';
          tr.innerHTML =
            '<td style="padding:.5rem .75rem;color:#94a3b8;font-size:.78rem;white-space:nowrap;">' + log.uploaded_at + '</td>' +
            '<td style="padding:.5rem .75rem;color:#f8fafc;font-weight:600;">' + log.uploaded_by + '</td>' +
            '<td style="padding:.5rem .75rem;color:#94a3b8;">' + (log.device_name || '\u2014') + '</td>' +
            '<td style="padding:.5rem .75rem;color:#94a3b8;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="' + log.original_name + '">' + log.original_name + '</td>' +
            '<td style="padding:.5rem .75rem;color:#94a3b8;white-space:nowrap;">' + formatBytes(log.file_size_bytes) + '</td>' +
            '<td style="padding:.5rem .75rem;">' + viewCell + '</td>' +
            '<td style="padding:.5rem .75rem;color:#64748b;font-size:.72rem;">' + log.ip_address + '</td>';
          logsTbody.insertBefore(tr, logsTbody.firstChild);
        });
        if (added > 0) flash();
      })
      .catch(function () {});
  }

  refreshDevices();
  refreshLogs();
  setInterval(refreshDevices, 5000);
  setInterval(refreshLogs,   5000);
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') { refreshDevices(); refreshLogs(); }
  });
})();
