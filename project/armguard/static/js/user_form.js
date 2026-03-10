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

  // ── Scan / type Personnel ID ────────────────────────────────────────────────
  if (!scanEl) return;
  scanEl.classList.add('form-control');
  var _scanTimer = null;

  scanEl.addEventListener('input', function () {
    clearTimeout(_scanTimer);
    var val = this.value.trim();
    if (!val) { statusEl.style.display = 'none'; return; }

    // Immediate match — QR scanner typically pastes the full ID at once
    var pk = PID_MAP[val];
    if (pk) {
      applyByPk(pk);
      statusEl.textContent = '\u2713';   // ✓
      statusEl.style.color = 'var(--success, #22c55e)';
      statusEl.style.display = '';
      scanEl.value = '';
      return;
    }

    // Debounce for hand-typed partial input
    _scanTimer = setTimeout(function () {
      var pk2 = PID_MAP[val];
      if (pk2) {
        applyByPk(pk2);
        statusEl.textContent = '\u2713';
        statusEl.style.color = 'var(--success, #22c55e)';
        scanEl.value = '';
      } else {
        statusEl.textContent = '\u2717';   // ✗
        statusEl.style.color = 'var(--red, #ef4444)';
      }
      statusEl.style.display = '';
    }, 600);
  });

  // Enter key triggers immediate lookup
  scanEl.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    clearTimeout(_scanTimer);
    var pk = PID_MAP[this.value.trim()];
    if (pk) {
      applyByPk(pk);
      statusEl.textContent = '\u2713';
      statusEl.style.color = 'var(--success, #22c55e)';
      scanEl.value = '';
    } else {
      statusEl.textContent = '\u2717';
      statusEl.style.color = 'var(--red, #ef4444)';
    }
    statusEl.style.display = '';
  });
}());
