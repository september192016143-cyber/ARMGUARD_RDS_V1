/**
 * settings.js — System Settings page interactions
 * Extracted from settings.html to comply with CSP script-src 'self'
 */
'use strict';

// ── MFA toggle live colour ───────────────────────────────────────────────────
(function () {
  var toggle = document.getElementById('id_mfa_required');
  if (!toggle) return;

  toggle.addEventListener('change', function () {
    var card  = this.closest('.form-group');
    var badge = document.getElementById('mfa-badge');
    var note  = card ? card.querySelector('span[style*="f59e0b"]') : null;
    if (this.checked) {
      if (card)  { card.style.background  = 'rgba(34,197,94,.07)'; card.style.borderColor = 'rgba(34,197,94,.25)'; }
      if (badge) { badge.style.background = 'rgba(34,197,94,.15)'; badge.style.color = '#22c55e'; badge.textContent = 'ON'; }
      if (note)  { note.remove(); }
    } else {
      if (card)  { card.style.background  = 'rgba(239,68,68,.07)'; card.style.borderColor = 'rgba(239,68,68,.25)'; }
      if (badge) { badge.style.background = 'rgba(239,68,68,.15)'; badge.style.color = '#ef4444'; badge.textContent = 'OFF'; }
    }
  });
})();

// ── Personnel Group management ───────────────────────────────────────────────
(function () {
  function showRename(pk, currentName) {
    document.getElementById('group-view-' + pk).style.display = 'none';
    document.getElementById('group-edit-' + pk).style.display = 'inline-flex';
    document.getElementById('group-name-' + pk).style.display = 'none';
    var disp = document.getElementById('group-input-display-' + pk);
    disp.value = currentName;
    disp.style.display = 'inline-block';
    document.getElementById('group-input-' + pk).value = currentName;
    disp.focus();
    disp.select();
  }

  function hideRename(pk) {
    document.getElementById('group-edit-' + pk).style.display = 'none';
    document.getElementById('group-view-' + pk).style.display = 'inline-flex';
    document.getElementById('group-name-' + pk).style.display = '';
    document.getElementById('group-input-display-' + pk).style.display = 'none';
  }

  // Rename (pencil) buttons
  document.querySelectorAll('.btn-group-rename').forEach(function (btn) {
    btn.addEventListener('click', function () {
      showRename(this.dataset.pk, this.dataset.name);
    });
  });

  // Cancel buttons
  document.querySelectorAll('.btn-group-cancel').forEach(function (btn) {
    btn.addEventListener('click', function () {
      hideRename(this.dataset.pk);
    });
  });

  // Sync display input → hidden input on every keystroke
  document.querySelectorAll('[data-syncs-to]').forEach(function (disp) {
    disp.addEventListener('input', function () {
      var target = document.getElementById(this.dataset.syncsTo);
      if (target) target.value = this.value;
    });
  });

  // Confirm before delete
  document.querySelectorAll('[data-group-delete]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      var name = this.dataset.groupName;
      if (!confirm('Delete group "' + name + '"? This cannot be undone.\n(Only possible if no personnel are assigned to this group.)')) {
        e.preventDefault();
      }
    });
  });
})();

// ── Personnel Squadron management ────────────────────────────────────────────
(function () {
  function showSqRename(pk, currentName) {
    document.getElementById('sq-view-' + pk).style.display = 'none';
    document.getElementById('sq-edit-' + pk).style.display = 'inline-flex';
    document.getElementById('sq-name-' + pk).style.display = 'none';
    var disp = document.getElementById('sq-input-display-' + pk);
    disp.value = currentName;
    disp.style.display = 'inline-block';
    document.getElementById('sq-input-' + pk).value = currentName;
    disp.focus();
    disp.select();
  }

  function hideSqRename(pk) {
    document.getElementById('sq-edit-' + pk).style.display = 'none';
    document.getElementById('sq-view-' + pk).style.display = 'inline-flex';
    document.getElementById('sq-name-' + pk).style.display = '';
    document.getElementById('sq-input-display-' + pk).style.display = 'none';
  }

  // Rename (pencil) buttons
  document.querySelectorAll('.btn-sq-rename').forEach(function (btn) {
    btn.addEventListener('click', function () {
      showSqRename(this.dataset.pk, this.dataset.name);
    });
  });

  // Cancel buttons
  document.querySelectorAll('.btn-sq-cancel').forEach(function (btn) {
    btn.addEventListener('click', function () {
      hideSqRename(this.dataset.pk);
    });
  });

  // Sync display input → hidden input on every keystroke
  document.querySelectorAll('[data-sq-syncs-to]').forEach(function (disp) {
    disp.addEventListener('input', function () {
      var target = document.getElementById(this.dataset.sqSyncsTo);
      if (target) target.value = this.value;
    });
  });

  // Confirm before delete
  document.querySelectorAll('[data-squadron-delete]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      var name = this.dataset.squadronName;
      if (!confirm('Delete squadron "' + name + '"? This cannot be undone.\n(Only possible if no personnel are assigned to this squadron.)')) {
        e.preventDefault();
      }
    });
  });
})();

// ── Purpose edit / cancel / delete ──────────────────────────────────────────
(function () {
  document.querySelectorAll('.btn-purpose-edit').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var pk = this.dataset.pk;
      document.querySelectorAll('#purpose-row-' + pk + ' .p-view').forEach(function (el) { el.style.display = 'none'; });
      document.querySelectorAll('#purpose-row-' + pk + ' .p-edit').forEach(function (el) { el.style.display = ''; });
    });
  });

  document.querySelectorAll('.btn-purpose-cancel').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var pk = this.dataset.pk;
      document.querySelectorAll('#purpose-row-' + pk + ' .p-view').forEach(function (el) { el.style.display = ''; });
      document.querySelectorAll('#purpose-row-' + pk + ' .p-edit').forEach(function (el) { el.style.display = 'none'; });
    });
  });

  document.querySelectorAll('.btn-purpose-delete').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      var name = this.dataset.name || 'this purpose';
      if (!confirm('Delete purpose "' + name + '"? This cannot be undone.')) {
        e.preventDefault();
      }
    });
  });
})();

// ── OREX Simulation — commit confirmation ────────────────────────────────────
(function () {
  var btn = document.getElementById('btn-sim-orex');
  if (!btn) return;
  btn.addEventListener('click', function (e) {
    var chk = document.getElementById('sim-commit-chk');
    if (chk && chk.checked) {
      if (!confirm('This will write real transactions to the database. Continue?')) {
        e.preventDefault();
      }
    }
  });
})();

// ── Manual Backup ────────────────────────────────────────────────────────────
(function () {
  var btn    = document.getElementById('btn-manual-backup');
  var status = document.getElementById('backup-status');
  var detail = document.getElementById('backup-detail');
  var urlEl  = document.getElementById('backup-url');
  if (!btn || !urlEl) return;

  btn.addEventListener('click', function () {
    btn.disabled = true;
    status.style.color = 'var(--muted)';
    status.textContent = 'Creating backup\u2026';
    detail.style.display = 'none';

    fetch(urlEl.dataset.url, {
      method: 'POST',
      headers: {
        'X-CSRFToken': (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '',
        'X-Requested-With': 'XMLHttpRequest',
      },
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.ok) {
        status.style.color = '#22c55e';
        status.textContent = '\u2713 Backup created successfully.';
        if (data.detail) {
          detail.textContent = data.detail;
          detail.style.display = '';
        }
      } else {
        status.style.color = '#ef4444';
        status.textContent = '\u2717 Backup failed: ' + (data.error || 'Unknown error');
      }
    })
    .catch(function (err) {
      status.style.color = '#ef4444';
      status.textContent = '\u2717 Request error: ' + err;
    })
    .finally(function () {
      btn.disabled = false;
    });
  });
})();

// ── Data Truncation — confirm ────────────────────────────────────────────────
(function () {
  var btn = document.getElementById('btn-truncate');
  if (!btn) return;
  btn.addEventListener('click', function (e) {
    if (!confirm('This will permanently delete all selected records. Are you sure?')) {
      e.preventDefault();
    }
  });
})();

// ── Purpose Field Visibility — per-row validation ────────────────────────────
// Highlights any purpose row where both Pistol and Rifle are unchecked so
// operators know the transaction form would be unusable for that purpose.
// Also blocks the settings form from saving in that state (server validates too).
(function () {
  var tbody = document.getElementById('purpose-vis-tbody');
  if (!tbody) return;

  function evaluateRow(row) {
    var cbs = row.querySelectorAll('input[type="checkbox"]');
    var bothOff = cbs.length === 2 && !cbs[0].checked && !cbs[1].checked;
    row.style.background = bothOff ? 'rgba(239,68,68,.10)' : '';
    var warn = row.querySelector('.purpose-vis-warn');
    if (!warn) {
      warn = document.createElement('span');
      warn.className = 'purpose-vis-warn';
      warn.style.cssText = 'font-size:.7rem;color:#ef4444;font-weight:600;margin-left:.5rem;vertical-align:middle';
      warn.textContent = '⚠ At least one must be checked';
      var nameTd = row.querySelector('td:first-child');
      if (nameTd) nameTd.appendChild(warn);
    }
    warn.style.display = bothOff ? '' : 'none';
  }

  tbody.querySelectorAll('tr').forEach(function (row) {
    evaluateRow(row);
    row.querySelectorAll('input[type="checkbox"]').forEach(function (cb) {
      cb.addEventListener('change', function () { evaluateRow(row); });
    });
  });

  // Block form submit when any purpose has both weapons disabled.
  var settingsForm = document.getElementById('settings-form');
  if (settingsForm) {
    settingsForm.addEventListener('submit', function (e) {
      var hasInvalid = false;
      tbody.querySelectorAll('tr').forEach(function (row) {
        var cbs = row.querySelectorAll('input[type="checkbox"]');
        if (cbs.length === 2 && !cbs[0].checked && !cbs[1].checked) hasInvalid = true;
      });
      if (hasInvalid) {
        e.preventDefault();
        tbody.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    });
  }
})();
