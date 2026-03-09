/**
 * personnel_form.js — CSP-safe replacement for the inline <script> block
 * that was previously embedded in personnel_form.html.
 *
 * Config is passed via data attributes on #personnelForm:
 *   data-preview-url  – URL for the card-preview AJAX endpoint
 *   data-show-back    – "1" to start with the card flipped to the back face
 *
 * Field IDs use Django ModelForm defaults (id_<fieldname>), which are stable
 * for this form and do not need to be templated.
 */
(function () {
  'use strict';

  const form = document.getElementById('personnelForm');
  if (!form) return;

  const PREVIEW_URL = form.dataset.previewUrl;
  const SHOW_BACK   = form.dataset.showBack === '1';
  const CSRF        = document.querySelector('[name=csrfmiddlewaretoken]').value;

  const flipCard     = document.getElementById('previewFlipCard');
  const previewFront = document.getElementById('previewFront');
  const previewBack  = document.getElementById('previewBack');
  const pidDisplay   = document.getElementById('previewPersonnelId');

  // ── Add form-control class to all plain inputs ──────────────────────────────
  // (Django form widgets do not add CSS classes by default.)
  form.querySelectorAll(
    'input[type=text],input[type=number],input[type=email],input[type=tel],select,textarea'
  ).forEach(el => el.classList.add('form-control'));

  // ── Flip card (replaces CSP-blocked onclick= attribute) ─────────────────────
  function showFront() { if (flipCard) flipCard.classList.remove('flipped'); }
  function showBack()  { if (flipCard) flipCard.classList.add('flipped'); }

  if (flipCard) {
    flipCard.addEventListener('click', () => flipCard.classList.toggle('flipped'));
  }
  if (SHOW_BACK) showBack();

  // ── Debounced AJAX card preview ─────────────────────────────────────────────
  let _debounceTimer = null;
  let _pendingFront  = null;
  let _pendingBack   = null;

  function fetchPreview(face) {
    const imgEl = face === 'front' ? previewFront : previewBack;
    if (!imgEl) return;

    if (face === 'front' && _pendingFront) { _pendingFront.abort(); _pendingFront = null; }
    if (face === 'back'  && _pendingBack)  { _pendingBack.abort();  _pendingBack  = null; }

    const ctrl = new AbortController();
    if (face === 'front') _pendingFront = ctrl; else _pendingBack = ctrl;

    const fd = new FormData(form);
    fd.set('face', face);

    fetch(PREVIEW_URL, {
      method: 'POST',
      headers: { 'X-CSRFToken': CSRF },
      body: fd,
      signal: ctrl.signal,
    })
      .then(r => r.ok ? r.blob() : null)
      .then(blob => {
        if (!blob) return;
        const old = imgEl.src;
        imgEl.src = URL.createObjectURL(blob);
        if (old && old.startsWith('blob:')) URL.revokeObjectURL(old);
      })
      .catch(() => {/* aborted or network error — silently ignore */});
  }

  function schedulePreview() {
    clearTimeout(_debounceTimer);
    _debounceTimer = setTimeout(() => {
      fetchPreview('front');
      fetchPreview('back');
    }, 450);
  }

  // ── Personnel ID simulation (mirrors models.py save() logic) ────────────────
  const _ENLISTED = ['AM','AW','A2C','AW2C','A1C','AW1C','SGT','SSGT','TSGT','MSGT','SMSGT','CMSGT'];
  const _OFFICERS = ['2LT','1LT','CPT','MAJ','LTCOL','COL','BGEN','MGEN','LTGEN','GEN'];

  function simulatePersonnelId(rank, afsn) {
    if (!rank || !afsn) return null;
    const now    = new Date();
    const pad    = n => String(n).padStart(2, '0');
    const suffix = pad(now.getHours()) + pad(now.getDate()) + pad(now.getMinutes())
                 + pad(now.getMonth() + 1) + String(now.getFullYear()).slice(-2);
    if (_ENLISTED.includes(rank)) return 'PEP-' + afsn + '-' + suffix;
    if (_OFFICERS.includes(rank)) {
      const a = afsn.startsWith('O-') ? afsn : 'O-' + afsn;
      return 'POF_' + a + '-' + suffix;
    }
    return 'P' + afsn + '-' + suffix;
  }

  function updatePidDisplay() {
    if (!pidDisplay) return;
    const rank = (document.getElementById('id_rank') || {}).value  || '';
    const afsn = (document.getElementById('id_AFSN') || {}).value  || '';
    const sim  = simulatePersonnelId(rank, afsn);
    pidDisplay.textContent = sim || 'Auto-generated on save';
    pidDisplay.style.color = sim ? 'var(--text)' : 'var(--muted)';
  }

  // ── Wire all form inputs ─────────────────────────────────────────────────────
  form.querySelectorAll('input,select,textarea').forEach(el => {
    const evt = el.type === 'file' ? 'change' : 'input';
    el.addEventListener(evt, () => {
      updatePidDisplay();
      schedulePreview();
      // Photo uploaded → show front (real image); text/select → show back (live mock)
      if (el.type === 'file') showFront(); else showBack();
    });
  });

  // ── Initial render ───────────────────────────────────────────────────────────
  updatePidDisplay();
  schedulePreview();
}());
