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

// ── Icon picker ──────────────────────────────────────────────────────────────
(function () {
  var dataEl   = document.getElementById('icon-picker-data');
  var grid     = document.getElementById('icon-grid');
  var searchEl = document.getElementById('icon-search');
  var hiddenEl = document.getElementById('id_app_icon');
  var labelEl  = document.getElementById('icon-selected-label');
  if (!dataEl || !grid || !hiddenEl) return;

  var icons = JSON.parse(dataEl.textContent);
  var current = hiddenEl.value.trim();

  function render(filter) {
    filter = (filter || '').toLowerCase();
    grid.innerHTML = '';

    icons.forEach(function (icon) {
      if (filter && icon.label.toLowerCase().indexOf(filter) === -1 &&
                    icon.cls.toLowerCase().indexOf(filter) === -1) return;

      var isSelected = (icon.cls === current);
      var cell = document.createElement('div');
      cell.title = icon.label;
      cell.style.cssText = [
        'display:flex;flex-direction:column;align-items:center;justify-content:center',
        'gap:.3rem;padding:.5rem .25rem;border-radius:8px;cursor:pointer',
        'border:2px solid ' + (isSelected ? 'var(--primary,#f59e0b)' : 'transparent'),
        'background:' + (isSelected ? 'rgba(245,158,11,.12)' : 'var(--surface2,#1a2035)'),
        'transition:border-color .15s,background .15s',
        'font-size:.65rem;color:var(--muted,#64748b);text-align:center;word-break:break-word',
      ].join(';');

      var ico = document.createElement('i');
      ico.className = icon.cls;
      ico.style.cssText = 'font-size:1.35rem;color:' +
        (isSelected ? 'var(--primary,#f59e0b)' : 'var(--text,#e2e8f0)');

      var lbl = document.createElement('span');
      lbl.textContent = icon.label;

      cell.appendChild(ico);
      cell.appendChild(lbl);

      cell.addEventListener('mouseenter', function () {
        if (icon.cls !== current) {
          this.style.borderColor = 'rgba(245,158,11,.4)';
          this.style.background  = 'rgba(245,158,11,.06)';
        }
      });
      cell.addEventListener('mouseleave', function () {
        if (icon.cls !== current) {
          this.style.borderColor = 'transparent';
          this.style.background  = 'var(--surface2,#1a2035)';
        }
      });

      cell.addEventListener('click', function () {
        if (current === icon.cls) {
          // deselect
          current = '';
        } else {
          current = icon.cls;
        }
        hiddenEl.value = current;
        updateLabel();
        render(searchEl ? searchEl.value : '');
      });

      grid.appendChild(cell);
    });
  }

  function updateLabel() {
    if (!labelEl) return;
    if (current) {
      labelEl.innerHTML = 'Selected: <code style="color:var(--primary,#f59e0b)">' +
        current.replace(/</g, '&lt;') + '</code>';
    } else {
      labelEl.textContent = 'No icon selected \u2014 default shield will be shown.';
    }
  }

  render('');

  if (searchEl) {
    searchEl.addEventListener('input', function () {
      render(this.value);
    });
  }
})();
