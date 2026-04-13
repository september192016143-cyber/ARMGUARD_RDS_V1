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
