/* dashboard_cards.js — Real-time stat card poller.
 *
 * Reads the poll endpoint URL from a data-url attribute on #dashboard-poll-meta
 * so no inline script (and no CSP 'unsafe-inline') is required.
 */
(function () {
  'use strict';

  var meta = document.getElementById('dashboard-poll-meta');
  if (!meta) { return; }
  var POLL_URL = meta.getAttribute('data-url');
  if (!POLL_URL) { return; }

  var INTERVAL = 10000; // 10 seconds

  function fmt(n) {
    return Number(n).toLocaleString();
  }

  function set(id, text) {
    var el = document.getElementById(id);
    if (el) { el.textContent = text; }
  }

  function updateCards(d) {
    // Personnel
    set('card-personnel-total',    fmt(d.total_personnel));
    set('card-personnel-officers', fmt(d.officers_count)           + ' Officers');
    set('card-personnel-enlisted', fmt(d.enlisted_count)           + ' Enlisted');
    // Firearms
    set('card-firearms-total',         fmt((d.total_pistols || 0) + (d.total_rifles || 0)));
    set('card-firearms-pistol-avail',  fmt(d.pistols_available)   + ' Pistol');
    set('card-firearms-rifle-avail',   fmt(d.rifles_available)    + ' Rifle');
    set('card-firearms-pistol-issued', fmt(d.pistols_issued)      + ' Pistol');
    set('card-firearms-rifle-issued',  fmt(d.rifles_issued)       + ' Rifle');
    // Issued Firearms
    set('card-issued-total', fmt(d.total_issued));
    set('card-issued-tr',    fmt(d.issued_TR)                      + ' TR');
    set('card-issued-par',   fmt(d.issued_PAR)                     + ' PAR');
    // Transactions Today
    set('card-txn-total',       fmt(d.total_transactions_today));
    set('card-txn-withdrawals', fmt(d.withdrawals_today)           + ' withdrawals');
    set('card-txn-returns',     fmt(d.returns_today)               + ' returns');
  }

  function poll() {
    fetch(POLL_URL, { credentials: 'same-origin' })
      .then(function (r) { if (r.ok) { return r.json(); } })
      .then(function (data) { if (data) { updateCards(data); } })
      .catch(function () {});
  }

  setInterval(poll, INTERVAL);
}());
