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
