/* Multi-slot phone-capture widget for discrepancy image fields (up to 5 slots).
 * Config is read from <script type="application/json" id="disc-capture-config">.
 *
 * Required config keys:
 *   initUrl     - POST endpoint to start a capture session
 *   phoneBtnId  - ID of the single "Via Phone" button
 *   overlayId, closeBtnId, qrImgId, statusElId, linkElId - overlay elements
 *   slots       - array of {inputId, chooseBtnId, clearBtnId, thumbId, emptyIconId}
 */
(function () {
  'use strict';

  var cfgEl = document.getElementById('disc-capture-config');
  if (!cfgEl) return;
  var cfg;
  try { cfg = JSON.parse(cfgEl.textContent); } catch (e) { return; }

  var overlay  = document.getElementById(cfg.overlayId);
  var closeBtn = document.getElementById(cfg.closeBtnId);
  var qrImg    = document.getElementById(cfg.qrImgId);
  var statusEl = document.getElementById(cfg.statusElId);
  var linkEl   = document.getElementById(cfg.linkElId);
  var phoneBtn = document.getElementById(cfg.phoneBtnId);

  if (!overlay) return;

  var slots = cfg.slots || [];
  var _timer = null, _token = null, _targetSlotIdx = -1;

  /* ── Per-slot wiring ──────────────────────────────────────────── */
  slots.forEach(function (slot, idx) {
    var inp    = document.getElementById(slot.inputId);
    var choose = document.getElementById(slot.chooseBtnId);
    var clear  = document.getElementById(slot.clearBtnId);
    var thumb  = document.getElementById(slot.thumbId);
    var empty  = document.getElementById(slot.emptyIconId);

    if (!inp) return;

    /* Choose File */
    if (choose) {
      choose.addEventListener('click', function () { inp.click(); });
    }

    /* Show thumbnail on file selection */
    inp.addEventListener('change', function () {
      if (inp.files && inp.files[0]) {
        var reader = new FileReader();
        reader.onload = function (e) {
          if (thumb) { thumb.src = e.target.result; thumb.style.display = 'block'; }
          if (empty) empty.style.display = 'none';
          if (clear) clear.style.display = '';
        };
        reader.readAsDataURL(inp.files[0]);
      }
    });

    /* Remove / Clear */
    if (clear) {
      clear.addEventListener('click', function () {
        inp.value = '';
        /* Tick Django's hidden clear checkbox so existing saved image is removed on save */
        var cbId = slot.inputId.replace(/^id_/, '') + '-clear_id';
        var clearCb = document.getElementById(cbId);
        if (clearCb) clearCb.checked = true;
        if (thumb) { thumb.src = ''; thumb.style.display = 'none'; }
        if (empty) empty.style.display = '';
        clear.style.display = 'none';
      });
    }
  });

  /* ── Via Phone ─────────────────────────────────────────────────── */
  function slotHasContent(idx) {
    var slot  = slots[idx];
    var inp   = document.getElementById(slot.inputId);
    var thumb = document.getElementById(slot.thumbId);
    var hasFile    = inp && inp.files && inp.files.length > 0;
    var hasPreview = thumb && thumb.src && thumb.src !== window.location.href &&
                     thumb.style.display !== 'none';
    return hasFile || hasPreview;
  }

  function getNextEmptySlotIdx() {
    for (var i = 0; i < slots.length; i++) {
      if (!slotHasContent(i)) return i;
    }
    return -1;
  }

  if (phoneBtn) {
    phoneBtn.addEventListener('click', function () {
      var idx = getNextEmptySlotIdx();
      if (idx < 0) {
        /* All slots filled — show message in overlay */
        if (qrImg)   qrImg.style.display = 'none';
        if (linkEl)  linkEl.style.display = 'none';
        if (statusEl) statusEl.textContent = 'All 5 image slots are filled. Remove one to add more.';
        overlay.style.display = 'flex';
        return;
      }
      _targetSlotIdx = idx;
      openOverlay();
    });
  }

  /* ── Overlay ───────────────────────────────────────────────────── */
  function csrf() {
    var el = document.querySelector('[name=csrfmiddlewaretoken]');
    return el ? el.value : '';
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function openOverlay() {
    if (qrImg)    { qrImg.style.display = 'none'; qrImg.src = ''; }
    if (linkEl)   linkEl.style.display = 'none';
    if (statusEl) statusEl.textContent = 'Generating QR code\u2026';
    overlay.style.display = 'flex';

    fetch(cfg.initUrl, {
      method: 'POST',
      headers: { 'X-CSRFToken': csrf() },
      credentials: 'same-origin'
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        _token = d.token;
        if (d.mode === 'device') {
          if (qrImg)  qrImg.style.display = 'none';
          if (linkEl) linkEl.style.display = 'none';
          if (statusEl) statusEl.innerHTML =
            '\uD83D\uDCF1 Capture request sent to <strong>' + esc(d.device_name || 'unnamed') + '</strong>.' +
            '<br><span style="font-size:.75rem;color:#94a3b8;">The camera page on that phone will prompt for the photo automatically.</span>';
        } else if (d.mode === 'pair_needed') {
          overlay.style.display = 'none';
          window.location.href = d.pair_url;
          return;
        } else {
          if (qrImg)  { qrImg.src = 'data:image/png;base64,' + d.qr_b64; qrImg.style.display = 'block'; }
          if (linkEl) { linkEl.href = d.phone_url; linkEl.style.display = ''; }
          if (statusEl) statusEl.textContent = 'Waiting for photo from phone\u2026';
        }
        startPoll();
      })
      .catch(function () {
        if (statusEl) statusEl.textContent = 'Error generating QR. Please try again.';
      });
  }

  function startPoll() {
    clearInterval(_timer);
    _timer = setInterval(function () {
      if (!_token) return;
      fetch('/inventory/serial-capture/' + _token + '/poll/', { credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d.ready) {
            clearInterval(_timer);
            if (statusEl) statusEl.textContent = 'Photo received! Loading\u2026';
            fetch(d.image_url, { credentials: 'same-origin' })
              .then(function (r) { return r.blob(); })
              .then(function (b) {
                var f  = new File([b], 'phone_capture.jpg', { type: b.type || 'image/jpeg' });
                var dt = new DataTransfer();
                dt.items.add(f);
                var slot = slots[_targetSlotIdx];
                var inp  = slot ? document.getElementById(slot.inputId) : null;
                if (inp) {
                  inp.files = dt.files;
                  inp.dispatchEvent(new Event('change'));
                }
                closeOverlay();
              })
              .catch(function () {
                if (statusEl) statusEl.textContent = 'Error loading photo. Please try again.';
              });
          } else if (d.expired) {
            clearInterval(_timer);
            if (statusEl) statusEl.textContent = 'Session expired. Close and try again.';
          }
        })
        .catch(function () {});
    }, 2000);
  }

  function closeOverlay() {
    overlay.style.display = 'none';
    clearInterval(_timer);
    _token = null;
    _targetSlotIdx = -1;
  }

  if (closeBtn) closeBtn.addEventListener('click', closeOverlay);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && overlay && overlay.style.display !== 'none') closeOverlay();
  });
}());
