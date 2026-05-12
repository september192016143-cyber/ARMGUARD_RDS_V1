/* dashboard_sim_status.js — OREX Simulation live-status poller.
 *
 * Reads the poll endpoint URL from data-url on #sim-status-meta.
 * Reads the reset endpoint URL from data-reset-url on #sim-status-meta.
 * No inline script required — fully CSP-compliant (script-src 'self').
 */
(function () {
  'use strict';

  var meta = document.getElementById('sim-status-meta');
  var body = document.getElementById('sim-status-body');
  if (!meta || !body) { return; }

  var apiUrl   = meta.getAttribute('data-url');
  var resetUrl = meta.getAttribute('data-reset-url');
  if (!apiUrl) { return; }

  var timer = null;

  /* Read CSRF token from any hidden input already on the page (most reliable),
     then fall back to the csrftoken cookie. */
  function getCsrf() {
    var inp = document.querySelector('[name=csrfmiddlewaretoken]');
    if (inp && inp.value) { return inp.value; }
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  /* POST to resetUrl using fetch so CSRF token is read fresh at click time. */
  function doReset(runId) {
    if (!resetUrl) { return; }
    if (!confirm('Cancel and clear this simulation run?')) { return; }
    var fd = new FormData();
    fd.append('csrfmiddlewaretoken', getCsrf());
    fd.append('run_id', runId || '');
    fetch(resetUrl, { method: 'POST', body: fd })
      .then(function () { window.location.reload(); })
      .catch(function () { window.location.reload(); });
  }

  function fmtDate(iso) {
    if (!iso) { return '\u2014'; }
    return new Date(iso).toLocaleString();
  }

  function badge(label, bg) {
    return (
      '<span style="background:' + bg + ';color:#fff;border-radius:4px;' +
      'padding:.1rem .45rem;font-size:.75rem;font-weight:700">' + label + '</span>'
    );
  }

  function render(d) {
    var html = '';

    if (d.status === 'none') {
      html = (
        '<p style="color:var(--muted);font-size:.87rem;margin:0">' +
        'No simulation runs yet. ' +
        '<a href="/users/settings/#sim-orex-form">Start one \u2192</a></p>'
      );

    } else if (d.status === 'queued' || d.status === 'running') {
      var pct = d.pct || 0;
      var resetBtn = resetUrl
        ? ('<button class="sim-reset-btn" data-run-id="' + d.run_id + '" ' +
           'style="font-size:.72rem;padding:.2rem .55rem;background:#c0392b;color:#fff;' +
           'border:none;border-radius:4px;cursor:pointer;margin-left:.5rem">Reset</button>')
        : '';

      html = (
        '<div style="display:flex;align-items:center;gap:.5rem;margin-bottom:.5rem">' +
          '<i class="fa-solid fa-spinner fa-spin" style="color:#1a6b3a"></i>' +
          '<strong style="font-size:.9rem">Simulation ' +
            (d.status === 'queued' ? 'queued\u2026' : 'running\u2026') +
          '</strong>' +
          '<span style="font-size:.82rem;color:var(--muted)">' +
            d.progress + ' / ' + d.total + '&nbsp;(' + pct + '%)' +
          '</span>' +
          resetBtn +
        '</div>' +
        '<div style="background:var(--surface-2,rgba(255,255,255,.06));border-radius:4px;' +
             'height:10px;overflow:hidden;margin-bottom:.6rem">' +
          '<div style="background:#1a6b3a;height:100%;width:' + pct + '%;transition:width .5s"></div>' +
        '</div>' +
        '<div style="font-size:.8rem;color:var(--muted);margin-bottom:.3rem">' +
          'Operator: <strong>' + d.operator + '</strong>' +
          ' &nbsp;\xb7&nbsp; Mode: <strong>' + (d.commit ? 'COMMIT' : 'DRY-RUN') + '</strong>' +
          ' &nbsp;\xb7&nbsp; Delay: <strong>' + d.delay_seconds + 's</strong>' +
          ' &nbsp;\xb7&nbsp; Started: ' + fmtDate(d.started_at) +
        '</div>' +
        '<div style="font-size:.8rem">' +
          '<span style="color:#1a6b3a">\u2713 ' + d.ok_count + ' ok</span>' +
          (d.err_count
            ? ' &nbsp;<span style="color:#c0392b">\u2717 ' + d.err_count + ' error(s)</span>'
            : '') +
        '</div>'
      );
      schedulePoll(5000);

    } else if (d.status === 'completed') {
      var elapsed   = (d.wall_time != null) ? d.wall_time.toFixed(1) + 's' : '\u2014';
      var modeBadge = d.commit ? badge('COMMITTED', '#1a6b3a') : badge('DRY-RUN', '#3498db');
      var resultsUrl = '/users/settings/simulate-orex/' + d.run_id + '/results/';
      html = (
        '<div style="display:flex;flex-wrap:wrap;align-items:center;gap:.5rem;margin-bottom:.45rem">' +
          modeBadge +
          '<span style="font-size:.88rem"><strong>' + d.ok_count + '</strong> ok' +
            (d.err_count
              ? ', <strong style="color:#c0392b">' + d.err_count + '</strong> errors'
              : '') +
            (d.skip_count ? ', ' + d.skip_count + ' skipped' : '') +
            ' \u2014 ' + d.total + ' personnel' +
          '</span>' +
          '<a href="' + resultsUrl + '" style="font-size:.75rem;padding:.25rem .65rem;' +
             'background:#1a6b3a;color:#fff;border-radius:5px;text-decoration:none">' +
             'View Results</a>' +
        '</div>' +
        '<div style="font-size:.8rem;color:var(--muted)">' +
          'Operator: <strong>' + d.operator + '</strong>' +
          ' &nbsp;\xb7&nbsp; Wall time: <strong>' + elapsed + '</strong>' +
          ' &nbsp;\xb7&nbsp; Delay: <strong>' + d.delay_seconds + 's</strong>' +
          ' &nbsp;\xb7&nbsp; Completed: ' + fmtDate(d.completed_at) +
        '</div>'
      );

    } else if (d.status === 'error') {
      html = (
        '<div style="color:#c0392b;font-size:.88rem">' +
          '<i class="fa-solid fa-xmark"></i> <strong>Simulation error:</strong> ' +
          (d.error_message || 'Unknown error') +
        '</div>'
      );
    }

    body.innerHTML = html;

    /* Attach Reset handler AFTER innerHTML so the button exists in the DOM.
       fetch+FormData reads the CSRF token fresh at click time. */
    var btn = body.querySelector('.sim-reset-btn');
    if (btn) {
      btn.addEventListener('click', function () {
        doReset(btn.getAttribute('data-run-id'));
      });
    }
  }

  function schedulePoll(ms) {
    if (timer) { clearTimeout(timer); }
    timer = setTimeout(poll, ms);
  }

  function poll() {
    /* Stop polling if PJAX navigated away from the settings page. */
    if (!document.body.contains(meta)) { timer = null; return; }
    fetch(apiUrl, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.json(); })
      .then(function (d) { render(d); })
      .catch(function ()  { schedulePoll(10000); });
  }

  poll();
}());
