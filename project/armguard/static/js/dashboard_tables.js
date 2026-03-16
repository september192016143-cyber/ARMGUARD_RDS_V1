/* dashboard_tables.js — Real-time analytics table poller.
 *
 * Polls /dashboard/tables-json/ every 30 seconds and rebuilds the
 * four analytics table tbodies + tfoot subtotals in-place.
 * No page reload required.
 */
(function () {
  'use strict';

  var meta = document.getElementById('dashboard-tables-poll-meta');
  if (!meta) { return; }
  var POLL_URL = meta.getAttribute('data-url');
  if (!POLL_URL) { return; }

  var INTERVAL = 30000; // 30 seconds

  function fmt(n) {
    return Number(n).toLocaleString();
  }

  /* ── Firearm / Inventory table ─────────────────────────────────────── */
  function renderInventory(data) {
    var body = document.getElementById('tbl-inventory-body');
    var foot = document.getElementById('tbl-inventory-foot');
    if (!body || !foot) { return; }

    var rows = data.rows || [];
    var html = '';
    rows.forEach(function (r, i) {
      var bg = (i % 2 === 1) ? 'rgba(24,103,212,.04)' : 'transparent';
      html += '<tr style="border-bottom:1px solid rgba(24,103,212,.1);background:' + bg + ';transition:background .15s">'
        + '<td style="padding:5px 8px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + r.nomenclature + '">' + r.nomenclature + '</td>'
        + '<td style="padding:5px 4px;text-align:center">' + fmt(r.possessed) + '</td>'
        + '<td style="padding:5px 4px;text-align:center">' + fmt(r.on_stock) + '</td>'
        + '<td style="padding:5px 4px;text-align:center">' + fmt(r.issued_par) + '</td>'
        + '<td style="padding:5px 4px;text-align:center">' + fmt(r.issued_tr) + '</td>'
        + '<td style="padding:5px 4px;text-align:center">' + fmt(r.serviceable) + '</td>'
        + '<td style="padding:5px 4px;text-align:center' + (r.unserviceable ? ';color:#d97706;font-weight:700' : '') + '">' + fmt(r.unserviceable) + '</td>'
        + '<td style="padding:5px 4px;text-align:center' + (r.lost ? ';color:#dc2626;font-weight:700' : '') + '">' + fmt(r.lost) + '</td>'
        + '<td style="padding:5px 4px;text-align:center' + (r.tampered ? ';color:#dc2626;font-weight:700' : '') + '">' + fmt(r.tampered) + '</td>'
        + '<td></td>'
        + '</tr>';
    });
    body.innerHTML = html;

    var t = data.totals || {};
    var ftr = foot.querySelector('tr');
    if (ftr) {
      var cells = ftr.querySelectorAll('td');
      if (cells.length >= 9) {
        cells[1].textContent = fmt(t.possessed);
        cells[2].textContent = fmt(t.on_stock);
        cells[3].textContent = fmt(t.issued_par);
        cells[4].textContent = fmt(t.issued_tr);
        cells[5].textContent = fmt(t.serviceable);
        cells[6].textContent = fmt(t.unserviceable);
        cells[6].style.color = t.unserviceable ? '#fcd34d' : '';
        cells[7].textContent = fmt(t.lost);
        cells[7].style.color = t.lost ? '#fca5a5' : '';
        cells[8].textContent = fmt(t.tampered);
        cells[8].style.color = t.tampered ? '#fca5a5' : '';
      }
    }
  }

  /* ── Accessories table ─────────────────────────────────────────────── */
  function renderAccessory(data) {
    var body = document.getElementById('tbl-accessory-body');
    var foot = document.getElementById('tbl-accessory-foot');
    if (!body || !foot) { return; }

    var rows = data.rows || [];
    var html = '';
    rows.forEach(function (r, i) {
      var bg = (i % 2 === 1) ? 'rgba(124,58,237,.04)' : 'transparent';
      html += '<tr style="border-bottom:1px solid rgba(124,58,237,.1);background:' + bg + ';transition:background .15s">'
        + '<td style="padding:5px 8px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + r.nomenclature + '">' + r.nomenclature + '</td>'
        + '<td style="padding:5px 4px;text-align:center">' + fmt(r.on_stock) + '</td>'
        + '<td style="padding:5px 4px;text-align:center">' + fmt(r.issued_par) + '</td>'
        + '<td style="padding:5px 4px;text-align:center">' + fmt(r.issued_tr) + '</td>'
        + '<td></td>'
        + '</tr>';
    });
    body.innerHTML = html;

    var t = data.totals || {};
    var ftr = foot.querySelector('tr');
    if (ftr) {
      var cells = ftr.querySelectorAll('td');
      if (cells.length >= 4) {
        cells[1].textContent = fmt(t.on_stock);
        cells[2].textContent = fmt(t.issued_par);
        cells[3].textContent = fmt(t.issued_tr);
      }
    }
  }

  /* ── Ammunition table ──────────────────────────────────────────────── */
  function renderAmmo(data) {
    var body = document.getElementById('tbl-ammo-body');
    var foot = document.getElementById('tbl-ammo-foot');
    if (!body || !foot) { return; }

    var rows = data.rows || [];
    var html = '';
    rows.forEach(function (r, i) {
      var bg = (i % 2 === 1) ? 'rgba(12,166,120,.04)' : 'transparent';
      html += '<tr style="border-bottom:1px solid rgba(12,166,120,.1);background:' + bg + ';transition:background .15s">'
        + '<td style="padding:5px 8px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + r.nomenclature + '">' + r.nomenclature + '</td>'
        + '<td style="padding:5px 4px;text-align:center">' + fmt(r.basic_load) + '</td>'
        + '<td style="padding:5px 4px;text-align:center">' + fmt(r.on_hand) + '</td>'
        + '<td style="padding:5px 4px;text-align:center">' + fmt(r.issued) + '</td>'
        + '<td style="padding:5px 4px;text-align:center">' + fmt(r.issued_par) + '</td>'
        + '<td style="padding:5px 4px;text-align:center">' + fmt(r.issued_tr) + '</td>'
        + '<td style="padding:5px 4px;text-align:center">' + fmt(r.expenditures) + '</td>'
        + '<td style="padding:5px 4px;text-align:center' + (r.unserviceable ? ';color:#d97706;font-weight:700' : '') + '">' + fmt(r.unserviceable) + '</td>'
        + '<td style="padding:5px 4px;text-align:center' + (r.lost ? ';color:#dc2626;font-weight:700' : '') + '">' + fmt(r.lost) + '</td>'
        + '<td></td>'
        + '</tr>';
    });
    body.innerHTML = html;

    var t = data.totals || {};
    var ftr = foot.querySelector('tr');
    if (ftr) {
      var cells = ftr.querySelectorAll('td');
      if (cells.length >= 9) {
        cells[1].textContent = fmt(t.basic_load);
        cells[2].textContent = fmt(t.on_hand);
        cells[3].textContent = fmt(t.issued);
        cells[4].textContent = fmt(t.issued_par);
        cells[5].textContent = fmt(t.issued_tr);
        cells[6].textContent = fmt(t.expenditures);
        cells[6].style.color = '';
        cells[7].textContent = fmt(t.unserviceable);
        cells[7].style.color = t.unserviceable ? '#fcd34d' : '';
        cells[8].textContent = fmt(t.lost);
        cells[8].style.color = t.lost ? '#fca5a5' : '';
      }
    }
  }

  /* ── Magazine table ────────────────────────────────────────────────── */
  function renderMagazine(data) {
    var body = document.getElementById('tbl-magazine-body');
    var foot = document.getElementById('tbl-magazine-foot');
    if (!body || !foot) { return; }

    var rows = data.rows || [];
    var html = '';
    rows.forEach(function (r, i) {
      var bg = (i % 2 === 1) ? 'rgba(29,78,216,.04)' : 'transparent';
      html += '<tr style="border-bottom:1px solid rgba(29,78,216,.1);background:' + bg + ';transition:background .15s">'
        + '<td style="padding:5px 8px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + r.nomenclature + '">' + r.nomenclature + '</td>'
        + '<td style="padding:5px 4px;text-align:center">' + fmt(r.on_stock) + '</td>'
        + '<td style="padding:5px 4px;text-align:center">' + fmt(r.issued_par) + '</td>'
        + '<td style="padding:5px 4px;text-align:center">' + fmt(r.issued_tr) + '</td>'
        + '<td></td>'
        + '</tr>';
    });
    body.innerHTML = html;

    var t = data.totals || {};
    var ftr = foot.querySelector('tr');
    if (ftr) {
      var cells = ftr.querySelectorAll('td');
      if (cells.length >= 4) {
        cells[1].textContent = fmt(t.on_stock);
        cells[2].textContent = fmt(t.issued_par);
        cells[3].textContent = fmt(t.issued_tr);
      }
    }
  }

  /* ── Poll ──────────────────────────────────────────────────────────── */
  function poll() {
    fetch(POLL_URL, { credentials: 'same-origin' })
      .then(function (r) { if (r.ok) { return r.json(); } })
      .then(function (data) {
        if (!data) { return; }
        renderInventory(data.inventory  || {});
        renderAccessory(data.accessory  || {});
        renderAmmo(data.ammo            || {});
        renderMagazine(data.magazine    || {});
      })
      .catch(function () {});
  }

  setInterval(poll, INTERVAL);
}());
