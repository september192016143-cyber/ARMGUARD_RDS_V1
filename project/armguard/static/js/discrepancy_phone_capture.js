/* Phone-capture widget for discrepancy image fields.
 * Config is read from <script type="application/json" id="disc-capture-config">.
 * Required keys: initUrl, fileInputId, phoneBtnId, chooseBtnId,
 *   overlayId, closeBtnId, qrImgId, statusElId, linkElId,
 *   previewRowId, previewThumbId
 */
(function () {
  'use strict';

  var cfgEl = document.getElementById('disc-capture-config');
  if (!cfgEl) return;
  var cfg;
  try { cfg = JSON.parse(cfgEl.textContent); } catch (e) { return; }

  var fileInput    = document.getElementById(cfg.fileInputId);
  var phoneBtn     = document.getElementById(cfg.phoneBtnId);
  var chooseBtn    = document.getElementById(cfg.chooseBtnId);
  var overlay      = document.getElementById(cfg.overlayId);
  var closeBtn     = document.getElementById(cfg.closeBtnId);
  var qrImg        = document.getElementById(cfg.qrImgId);
  var statusEl     = document.getElementById(cfg.statusElId);
  var linkEl       = document.getElementById(cfg.linkElId);
  var previewRow   = document.getElementById(cfg.previewRowId);
  var previewThumb = document.getElementById(cfg.previewThumbId);

  if (!fileInput) return;

  if (chooseBtn) {
    chooseBtn.addEventListener('click', function () { fileInput.click(); });
  }

  fileInput.addEventListener('change', function () {
    if (fileInput.files && fileInput.files[0]) {
      var reader = new FileReader();
      reader.onload = function (e) {
        if (previewThumb) previewThumb.src = e.target.result;
        if (previewRow)   previewRow.style.display = 'flex';
      };
      reader.readAsDataURL(fileInput.files[0]);
    }
  });

  var _timer = null, _token = null;

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
    if (qrImg)   { qrImg.style.display = 'none'; qrImg.src = ''; }
    if (linkEl)  linkEl.style.display = 'none';
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
                fileInput.files = dt.files;
                fileInput.dispatchEvent(new Event('change'));
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
  }

  if (phoneBtn) phoneBtn.addEventListener('click', openOverlay);
  if (closeBtn) closeBtn.addEventListener('click', closeOverlay);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && overlay && overlay.style.display !== 'none') closeOverlay();
  });
}());
