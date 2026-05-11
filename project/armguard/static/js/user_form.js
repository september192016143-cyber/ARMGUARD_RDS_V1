/**
 * user_form.js — CSP-safe replacement for the inline <script> block
 * previously embedded in user_form.html.
 *
 * Data is passed via <script type="application/json"> elements:
 *   #personnel-map-data     — JSON object: pk → {first, last, pid}
 *   #personnel-pid-map-data — JSON object: Personnel_ID → pk
 *
 * These are not treated as executable scripts by the browser so they are
 * never blocked by script-src CSP directives.
 */
(function () {
  'use strict';

  // ── Add form-control class to all plain inputs ──────────────────────────────
  document.querySelectorAll(
    'input[type=text],input[type=email],input[type=password],select'
  ).forEach(function (el) {
    el.classList.add('form-control');
  });

  // ── Administrator permission flags — show/hidden based on role ──────────────
  var roleSelect   = document.getElementById('id_role');
  var adminPerms   = document.getElementById('admin-perm-section');

  var ADMIN_ROLES = ['System Administrator', 'Armorer', 'Administrator \u2014 View Only', 'Administrator \u2014 Edit & Add'];

  // Default flag sets matching _GROUP_ROLE_MAP
  var ROLE_DEFAULTS = {
    'System Administrator': {
      id_perm_inventory_view: true,  id_perm_inventory_add: true,
      id_perm_inventory_edit: true,  id_perm_inventory_delete: true,
      id_perm_personnel_view: true,  id_perm_personnel_add: true,
      id_perm_personnel_edit: true,  id_perm_personnel_delete: true,
      id_perm_transaction_view: true, id_perm_transaction_create: true,
      id_perm_reports: true, id_perm_print: true, id_perm_users_manage: true,
    },
    'Armorer': {
      id_perm_inventory_view: true,  id_perm_inventory_add: false,
      id_perm_inventory_edit: false, id_perm_inventory_delete: false,
      id_perm_personnel_view: true,  id_perm_personnel_add: false,
      id_perm_personnel_edit: false, id_perm_personnel_delete: false,
      id_perm_transaction_view: true, id_perm_transaction_create: true,
      id_perm_reports: true, id_perm_print: true, id_perm_users_manage: false,
    },
    'Administrator \u2014 View Only': {
      id_perm_inventory_view: true,  id_perm_inventory_add: false,
      id_perm_inventory_edit: false, id_perm_inventory_delete: false,
      id_perm_personnel_view: true,  id_perm_personnel_add: false,
      id_perm_personnel_edit: false, id_perm_personnel_delete: false,
      id_perm_transaction_view: true, id_perm_transaction_create: false,
      id_perm_reports: true, id_perm_print: true, id_perm_users_manage: false,
    },
    'Administrator \u2014 Edit & Add': {
      id_perm_inventory_view: true,  id_perm_inventory_add: true,
      id_perm_inventory_edit: true,  id_perm_inventory_delete: false,
      id_perm_personnel_view: true,  id_perm_personnel_add: true,
      id_perm_personnel_edit: true,  id_perm_personnel_delete: false,
      id_perm_transaction_view: true, id_perm_transaction_create: true,
      id_perm_reports: true, id_perm_print: true, id_perm_users_manage: true,
    },
  };

  if (roleSelect && adminPerms) {
    function toggleAdminPerms() {
      adminPerms.style.display = ADMIN_ROLES.indexOf(roleSelect.value) !== -1 ? '' : 'none';
    }
    toggleAdminPerms();  // run on page load
    roleSelect.addEventListener('change', function () {
      toggleAdminPerms();
      // Auto-apply flag defaults when switching to a specific sub-type
      var defaults = ROLE_DEFAULTS[roleSelect.value];
      if (defaults) {
        Object.keys(defaults).forEach(function (id) {
          var el = document.getElementById(id);
          if (el) el.checked = defaults[id];
        });
      }
    });
  }

  // ── Personnel auto-fill ─────────────────────────────────────────────────────
  var mapEl    = document.getElementById('personnel-map-data');
  var pidMapEl = document.getElementById('personnel-pid-map-data');
  if (!mapEl) return;   // no personnel data on this page — nothing more to do

  var MAP     = JSON.parse(mapEl.textContent || '{}');
  var PID_MAP = pidMapEl ? JSON.parse(pidMapEl.textContent || '{}') : {};

  var sel      = document.getElementById('id_linked_personnel');
  var fnEl     = document.getElementById('id_first_name');
  var lnEl     = document.getElementById('id_last_name');
  var scanEl   = document.getElementById('personnelIdScan');
  var statusEl = document.getElementById('personnelIdScanStatus');
  if (!sel) return;

  function applyByPk(pk) {
    var p = MAP[String(pk)];
    if (!p) return false;
    sel.value = pk;
    if (fnEl) fnEl.value = p.first;
    if (lnEl) lnEl.value = p.last;
    return true;
  }

  // Dropdown changed manually
  sel.addEventListener('change', function () {
    applyByPk(this.value);
  });

  // Auto-fill on page load from pre-selected dropdown value
  if (sel.value) applyByPk(sel.value);

  // ── Scan / type Personnel ID (supports ID, surname, first name, AFSN) ───────
  if (!scanEl) return;
  scanEl.classList.add('form-control');
  var _scanTimer = null;
  var resultsEl  = document.getElementById('personnelScanResults');

  function escHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function closeScanResults() {
    if (resultsEl) { resultsEl.style.display = 'none'; resultsEl.innerHTML = ''; }
  }

  function selectPersonnel(pk) {
    applyByPk(pk);
    var p = MAP[String(pk)];
    statusEl.textContent = '\u2713';
    statusEl.style.color = 'var(--success, #22c55e)';
    statusEl.style.display = '';
    scanEl.value = p ? p.last + ', ' + p.first : '';
    closeScanResults();
  }

  function doSearch(val) {
    if (!resultsEl) return;
    var q = val.toLowerCase();
    var hits = Object.keys(MAP).filter(function (pk) {
      var p = MAP[pk];
      return p.first.toLowerCase().indexOf(q) !== -1
          || p.last.toLowerCase().indexOf(q) !== -1
          || p.afsn.toLowerCase().indexOf(q) !== -1
          || p.pid.toLowerCase().indexOf(q) !== -1;
    }).slice(0, 10);

    if (!hits.length) {
      resultsEl.innerHTML = '<div style="padding:.4rem .75rem;font-size:.78rem;color:var(--muted,#64748b)">No results</div>';
      resultsEl.style.display = 'block';
      statusEl.textContent = '\u2717';
      statusEl.style.color = 'var(--red, #ef4444)';
      statusEl.style.display = '';
      return;
    }

    statusEl.style.display = 'none';
    resultsEl.innerHTML = hits.map(function (pk) {
      var p = MAP[pk];
      return '<div class="uf-scan-item" data-pk="' + escHtml(pk) + '"'
        + ' style="padding:.38rem .75rem;font-size:.78rem;cursor:pointer;border-bottom:1px solid var(--border,#334155)">'
        + '<span style="font-weight:600">' + escHtml(p.last) + ', ' + escHtml(p.first) + '</span>'
        + ' &mdash; <span style="color:var(--muted,#64748b)">' + escHtml(p.pid) + '</span>'
        + (p.afsn ? ' <span style="font-size:.7rem;color:var(--muted,#64748b)">(AFSN: ' + escHtml(p.afsn) + ')</span>' : '')
        + '</div>';
    }).join('');
    resultsEl.style.display = 'block';
  }

  if (resultsEl) {
    resultsEl.addEventListener('mouseover', function (e) {
      var item = e.target.closest('.uf-scan-item');
      if (item) item.style.background = 'var(--hover-bg,#334155)';
    });
    resultsEl.addEventListener('mouseout', function (e) {
      var item = e.target.closest('.uf-scan-item');
      if (item) item.style.background = '';
    });
    resultsEl.addEventListener('click', function (e) {
      var item = e.target.closest('.uf-scan-item');
      if (item) selectPersonnel(item.dataset.pk);
    });
  }

  document.addEventListener('click', function (e) {
    if (!scanEl.contains(e.target) && !(resultsEl && resultsEl.contains(e.target))) closeScanResults();
  }, window.pjaxController ? { signal: window.pjaxController.signal } : {});

  scanEl.addEventListener('input', function () {
    clearTimeout(_scanTimer);
    var val = this.value.trim();
    if (!val) { statusEl.style.display = 'none'; closeScanResults(); return; }

    // Immediate exact Personnel_ID match (QR scanner burst)
    var pk = PID_MAP[val];
    if (pk) { selectPersonnel(pk); scanEl.value = ''; return; }

    // Debounce for hand-typed input — search by name / AFSN / ID
    _scanTimer = setTimeout(function () {
      var pk2 = PID_MAP[val];
      if (pk2) { selectPersonnel(pk2); scanEl.value = ''; return; }
      doSearch(val);
    }, 400);
  });

  // Enter key: confirm single result or trigger immediate search
  scanEl.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    clearTimeout(_scanTimer);
    var val = this.value.trim();
    var pk = PID_MAP[val];
    if (pk) { selectPersonnel(pk); scanEl.value = ''; return; }
    doSearch(val);
    // If exactly one result, auto-select it
    var items = resultsEl ? resultsEl.querySelectorAll('.uf-scan-item') : [];
    if (items.length === 1) selectPersonnel(items[0].dataset.pk);
  });
}());
