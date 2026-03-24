/**
 * camera_upload.js
 * F-CSP: Extracted from upload.html inline <script> to comply with CSP script-src 'self'.
 * Handles: rotating API key countdown/refresh, PIN gate, image preview, AJAX upload.
 *
 * URLs that vary per-request are passed via
 *   <script type="application/json" id="camera-upload-data">
 * The HMAC key and expiry already come from <meta> tags; reactivate URL too.
 */
(function () {
  // ── URL config (from JSON block) ─────────────────────────────────────────
  var dataEl = document.getElementById('camera-upload-data');
  if (!dataEl) return;
  var cfg;
  try { cfg = JSON.parse(dataEl.textContent); } catch (e) { return; }

  // ── DOM refs ─────────────────────────────────────────────────────────────
  var input      = document.getElementById('image-input');
  var previewWrap= document.getElementById('preview-wrap');
  var preview    = document.getElementById('preview');
  var submitBtn  = document.getElementById('submit-btn');
  var statusEl   = document.getElementById('status');
  var thumbList  = document.getElementById('thumb-list');
  var dropZone   = document.getElementById('drop-zone');
  var form       = document.getElementById('upload-form');
  var pinGate    = document.getElementById('pin-gate');
  var pinInput   = document.getElementById('pin-input');
  var pinSubmit  = document.getElementById('pin-submit');
  var pinErr     = document.getElementById('pin-err');

  // ── Rotating API key ──────────────────────────────────────────────────────
  var apiKey        = document.querySelector('meta[name="x-camera-key"]').getAttribute('content');
  var expiresAt     = parseInt(document.querySelector('meta[name="x-camera-key-expires"]').getAttribute('content'), 10);
  var reactivateUrl = document.querySelector('meta[name="x-camera-reactivate"]').getAttribute('content');
  var countdown     = document.getElementById('key-countdown');
  var refreshing    = false;

  try { localStorage.setItem('armguard_cam_reactivate', reactivateUrl); } catch (e) {}

  function updateCountdown() {
    var remaining = Math.max(0, Math.round((expiresAt - Date.now()) / 1000));
    if (countdown) countdown.textContent = remaining;
    if (remaining <= 0 && document.visibilityState === 'visible' && !refreshing) {
      refreshKey();
    }
  }

  function refreshKey() {
    if (refreshing) return;
    refreshing = true;
    fetch(cfg.keyRefreshUrl, {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      credentials: 'same-origin',
    })
    .then(function (r) { return r.json(); })
    .then(function (json) {
      refreshing = false;
      if (json.authenticated) {
        apiKey    = json.key;
        expiresAt = json.expires_ms;
        updateCountdown();
      } else {
        var savedUrl = reactivateUrl;
        try {
          savedUrl = localStorage.getItem('armguard_cam_reactivate') || reactivateUrl;
        } catch (e) {}
        if (savedUrl) {
          window.location.replace(savedUrl);
        } else {
          setStatus('Session expired. Please scan the QR code again.', false);
          submitBtn.disabled = true;
        }
      }
    })
    .catch(function () {
      refreshing = false;
    });
  }

  updateCountdown();
  setInterval(updateCountdown, 1000);

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') {
      updateCountdown();
    }
  });

  // ── PIN gate ──────────────────────────────────────────────────────────────
  if (pinGate && !pinGate.classList.contains('hidden')) {
    pinInput.addEventListener('input', function () {
      pinInput.value = pinInput.value.replace(/\D/g, '').slice(0, 6);
      pinSubmit.disabled = pinInput.value.length < 6;
      pinErr.textContent = '';
    });
    pinInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !pinSubmit.disabled) pinSubmit.click();
    });

    pinSubmit.addEventListener('click', function () {
      pinSubmit.disabled = true;
      pinErr.textContent = '';
      var fd = new FormData();
      fd.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);
      fd.append('pin', pinInput.value);
      fetch(cfg.pinApiUrl, {
        method: 'POST',
        credentials: 'same-origin',
        body: fd,
      })
      .then(function (r) { return r.json(); })
      .then(function (json) {
        if (json.success) {
          pinGate.classList.add('hidden');
        } else {
          pinErr.textContent = json.error || 'Incorrect PIN.';
          pinInput.value = '';
          pinSubmit.disabled = true;
          pinInput.focus();
        }
      })
      .catch(function () {
        pinErr.textContent = 'Network error. Try again.';
        pinSubmit.disabled = false;
      });
    });

    setTimeout(function () { pinInput.focus(); }, 200);
  }

  // ── Helpers ───────────────────────────────────────────────────────────────
  function setStatus(msg, ok) {
    statusEl.textContent = msg;
    statusEl.className = ok ? 'ok' : 'err';
  }

  // ── Image preview ─────────────────────────────────────────────────────────
  input.addEventListener('change', function () {
    if (!input.files || !input.files[0]) return;
    var reader = new FileReader();
    reader.onload = function (e) {
      preview.src = e.target.result;
      previewWrap.style.display = '';
      submitBtn.disabled = false;
      statusEl.textContent = '';
    };
    reader.readAsDataURL(input.files[0]);
  });

  // ── Drag-and-drop ─────────────────────────────────────────────────────────
  dropZone.addEventListener('dragover', function (e) { e.preventDefault(); dropZone.classList.add('dragover'); });
  dropZone.addEventListener('dragleave', function () { dropZone.classList.remove('dragover'); });
  dropZone.addEventListener('drop', function (e) {
    e.preventDefault(); dropZone.classList.remove('dragover');
    if (e.dataTransfer && e.dataTransfer.files[0]) {
      input.files = e.dataTransfer.files;
      input.dispatchEvent(new Event('change'));
    }
  });

  // ── AJAX upload ───────────────────────────────────────────────────────────
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    if (!input.files || !input.files[0]) return;

    submitBtn.disabled = true;
    setStatus('Uploading\u2026', true);

    var data = new FormData(form);
    fetch(cfg.uploadUrl, {
      method: 'POST',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        'X-Api-Key': apiKey,
      },
      body: data,
    })
    .then(function (r) { return r.json(); })
    .then(function (json) {
      if (json.success) {
        setStatus('Uploaded successfully!', true);
        var img = document.createElement('img');
        img.src = json.url;
        img.title = json.filename;
        thumbList.prepend(img);
        input.value = '';
        preview.src = '';
        previewWrap.style.display = 'none';
        submitBtn.disabled = true;
      } else {
        setStatus('Error: ' + (json.error || 'Unknown error'), false);
        submitBtn.disabled = false;
      }
    })
    .catch(function () {
      setStatus('Network error. Check your connection.', false);
      submitBtn.disabled = false;
    });
  });
})();
