/**
 * print_id_cards.js — CSP-safe replacement for the inline <script> block
 * previously embedded in print_id_cards.html.
 *
 * Config is passed via a <script type="application/json" id="id-cards-config">
 * element (never executed by the browser, so never blocked by script-src CSP):
 *   regenUrlTemplate  — URL with __PID__ placeholder for per-card regen
 *   printViewUrl      — base URL for the print view
 *   genMissingUrl     — URL for generate-missing / regen-all endpoint
 *   csrfToken         — Django CSRF token value
 *
 * Inline onclick attributes are replaced by:
 *   - data-action="regen"  + data-pid + data-slug  on regen buttons
 *   - data-action="flip"   on .flip-scene containers
 *   - id-based listeners on toolbar buttons (#btn-print-selected etc.)
 */
(function () {
  'use strict';

  var configEl = document.getElementById('id-cards-config');
  if (!configEl) return;
  var cfg = JSON.parse(configEl.textContent);

  var REGEN_URL_TEMPLATE = cfg.regenUrlTemplate;   // contains __PID__
  var PRINT_VIEW_URL     = cfg.printViewUrl;
  var GEN_MISSING_URL    = cfg.genMissingUrl;
  var CSRF_TOKEN         = cfg.csrfToken;

  // ── Flip ─────────────────────────────────────────────────────────────────
  document.addEventListener('click', function (e) {
    var scene = e.target.closest('[data-action="flip"]');
    if (!scene) return;
    scene.querySelector('.flip-inner').classList.toggle('flipped');
  });

  // ── Select All ───────────────────────────────────────────────────────────
  var selectAllCb = document.getElementById('select-all');
  if (selectAllCb) {
    selectAllCb.addEventListener('change', function () {
      document.querySelectorAll('.card-checkbox').forEach(function (cb) {
        cb.checked = selectAllCb.checked;
        cb.closest('.card-wrapper').querySelector('.id-card-item')
          .classList.toggle('selected', selectAllCb.checked);
      });
      updatePrintBtn();
    });
  }

  document.addEventListener('change', function (e) {
    if (e.target.classList.contains('card-checkbox')) {
      e.target.closest('.card-wrapper').querySelector('.id-card-item')
        .classList.toggle('selected', e.target.checked);
      updatePrintBtn();
    }
  });

  function updatePrintBtn() {
    var count = document.querySelectorAll('.card-checkbox:checked').length;
    var btn = document.getElementById('btn-print-selected');
    if (!btn) return;
    btn.disabled = count === 0;
    btn.innerHTML = '<i class="fas fa-print"></i> Print Selected' + (count ? ' (' + count + ')' : '');
  }

  // ── Print Selected ────────────────────────────────────────────────────────
  var printSelBtn = document.getElementById('btn-print-selected');
  if (printSelBtn) {
    printSelBtn.addEventListener('click', function () {
      var ids = Array.from(document.querySelectorAll('.card-checkbox:checked'))
                     .map(function (cb) { return cb.value; });
      if (!ids.length) return;
      window.open(PRINT_VIEW_URL + '?ids=' + ids.join(','), '_blank');
    });
  }

  // ── Regen Single (event delegation on card grid) ──────────────────────────
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-action="regen"]');
    if (!btn) return;
    regenCard(btn.dataset.pid, btn.dataset.slug);
  });

  function regenCard(pid, slug) {
    var btn    = document.getElementById('regen-btn-' + slug);
    var iconEl = document.querySelector('.regen-icon-' + slug);
    var spinEl = document.querySelector('.regen-spinner-' + slug);

    btn.disabled = true;
    if (iconEl) iconEl.style.display = 'none';
    if (spinEl) spinEl.style.display = 'inline';

    var url = REGEN_URL_TEMPLATE.replace('__PID__', pid);

    fetch(url, {
      method: 'POST',
      headers: { 'X-CSRFToken': CSRF_TOKEN, 'Content-Type': 'application/json' }
    })
    .then(function (r) {
      var ct = r.headers.get('Content-Type') || '';
      if (!ct.includes('application/json')) {
        return r.text().then(function () {
          throw new Error('Server returned HTTP ' + r.status + ' (not JSON). Check server logs.');
        });
      }
      return r.json();
    })
    .then(function (data) {
      if (data.success) {
        var thumbEl = document.getElementById('thumb-' + slug);
        if (thumbEl && thumbEl.tagName === 'IMG') {
          thumbEl.src = data.thumb_url + '?t=' + Date.now();
          var cardItem = thumbEl.closest('.id-card-item');
          if (cardItem) {
            cardItem.querySelectorAll('.flip-face.back img').forEach(function (img) {
              img.src = img.src.split('?')[0] + '?t=' + Date.now();
            });
          }
        } else if (thumbEl) {
          setTimeout(function () { location.reload(); }, 400);
        }
        var statusEl = document.getElementById('status-' + slug);
        if (statusEl) {
          statusEl.className = 'status-badge badge-ok';
          statusEl.innerHTML = '<i class="fas fa-check-circle"></i> Generated';
          statusEl.id = '';
        }
      } else {
        alert('Error: ' + (data.error || 'Unknown error'));
      }
    })
    .catch(function (err) { alert('Regenerate failed: ' + err); })
    .finally(function () {
      btn.disabled = false;
      if (iconEl) iconEl.style.display = 'inline';
      if (spinEl) spinEl.style.display = 'none';
    });
  }

  // ── Regen All ─────────────────────────────────────────────────────────────
  var regenAllBtn = document.getElementById('btn-regen-all');
  if (regenAllBtn) {
    regenAllBtn.addEventListener('click', function () {
      var total = document.querySelectorAll('.card-wrapper').length;
      if (!confirm(
        'Regenerate ALL ' + total + ' ID cards?\n\n' +
        'Use this when profile photos have been uploaded or migrated since cards were last generated.\n' +
        'This may take 30\u201360 seconds.'
      )) return;

      regenAllBtn.disabled = true;
      regenAllBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Regenerating all\u2026';

      var form = new FormData();
      form.append('force', '1');

      fetch(GEN_MISSING_URL, {
        method: 'POST',
        headers: { 'X-CSRFToken': CSRF_TOKEN },
        body: form
      })
      .then(function (r) {
        var ct = r.headers.get('Content-Type') || '';
        if (!ct.includes('application/json')) {
          return r.text().then(function () {
            throw new Error('Server returned HTTP ' + r.status + ' (not JSON). Pull latest code and restart.');
          });
        }
        return r.json();
      })
      .then(function (data) {
        if (data.success) {
          var msg = 'Regenerated ' + data.generated + ' cards.';
          if (data.errors && data.errors.length) {
            msg += '\n\n' + data.errors.length + ' error(s):\n' +
                   data.errors.map(function (e) { return '\u2022 ' + e.id + ': ' + e.error; }).join('\n');
          }
          regenAllBtn.innerHTML = '<i class="fas fa-check"></i> Done (' + data.generated + ')';
          alert(msg);
          setTimeout(function () { location.reload(); }, 500);
        } else {
          alert('Error regenerating cards.');
          regenAllBtn.disabled = false;
          regenAllBtn.innerHTML = '<i class="fas fa-redo"></i> Regenerate All';
        }
      })
      .catch(function (err) {
        alert(err.message || ('Request failed: ' + err));
        regenAllBtn.disabled = false;
        regenAllBtn.innerHTML = '<i class="fas fa-redo"></i> Regenerate All';
      });
    });
  }

  // ── Regen Missing ─────────────────────────────────────────────────────────
  var regenMissingBtn = document.getElementById('btn-regen-missing');
  if (regenMissingBtn) {
    regenMissingBtn.addEventListener('click', function () {
      var missing = document.querySelectorAll('.card-wrapper[data-has-card="0"]');
      if (!missing.length) {
        alert('No missing cards \u2014 all personnel already have ID cards!');
        return;
      }
      if (!confirm(
        'Generate ID cards for ' + missing.length + ' personnel without cards?\n\n' +
        'This will run on the server and may take a moment.'
      )) return;

      regenMissingBtn.disabled = true;
      regenMissingBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Generating on server\u2026';

      fetch(GEN_MISSING_URL, {
        method: 'POST',
        headers: { 'X-CSRFToken': CSRF_TOKEN }
      })
      .then(function (r) {
        var ct = r.headers.get('Content-Type') || '';
        if (!ct.includes('application/json')) {
          return r.text().then(function (t) {
            throw new Error(
              'Server returned HTTP ' + r.status + ' instead of JSON.\n' +
              'Make sure the server has the latest code (git pull + restart).'
            );
          });
        }
        return r.json();
      })
      .then(function (data) {
        if (data.success) {
          var msg = 'Done \u2014 ' + data.generated + ' generated, ' + data.skipped + ' already existed.';
          if (data.errors && data.errors.length) {
            msg += '\n\n' + data.errors.length + ' error(s):\n' +
                   data.errors.map(function (e) { return '\u2022 ' + e.id + ': ' + e.error; }).join('\n');
          }
          regenMissingBtn.innerHTML = '<i class="fas fa-check"></i> Done (' + data.generated + ' generated)';
          alert(msg);
          setTimeout(function () { location.reload(); }, 500);
        } else {
          alert('Error generating cards.');
          regenMissingBtn.disabled = false;
          regenMissingBtn.innerHTML = '<i class="fas fa-sync-alt"></i> Generate Missing';
        }
      })
      .catch(function (err) {
        alert(err.message || ('Request failed: ' + err));
        regenMissingBtn.disabled = false;
        regenMissingBtn.innerHTML = '<i class="fas fa-sync-alt"></i> Generate Missing';
      });
    });
  }

}());
