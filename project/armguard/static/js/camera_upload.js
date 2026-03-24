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

  // ── Serial capture task polling ───────────────────────────────────────────
  // When the admin clicks "Via Phone" and a paired device is found the server
  // sets CameraDevice.pending_serial_task.  We poll every 3 s; when a task
  // arrives we show the overlay so the user can photograph the serial number
  // and send it back to the admin without leaving this page.

  var _overlay      = document.getElementById('serial-task-overlay');
  var _captureInput = document.getElementById('serial-capture-input');
  var _previewWrap  = document.getElementById('serial-preview-wrap');
  var _previewImg   = document.getElementById('serial-preview');
  var _sendBtn      = document.getElementById('serial-send-btn');
  var _serialStatus = document.getElementById('serial-status');
  var _cancelBtn    = document.getElementById('serial-cancel-btn');
  var _taskIdField  = document.getElementById('serial-task-id');
  var _activeTask   = null;

  function _isPinVerified() {
    return !pinGate || pinGate.classList.contains('hidden');
  }

  function _showOverlay(taskId) {
    _activeTask = taskId;
    if (_taskIdField) _taskIdField.value = taskId;
    _previewWrap.style.display = 'none';
    _previewImg.src = '';
    if (_sendBtn) _sendBtn.style.display = 'none';
    if (_serialStatus) _serialStatus.textContent = '';
    _overlay.style.display = 'flex';
  }

  function _hideOverlay() {
    _activeTask = null;
    if (_taskIdField) _taskIdField.value = '';
    _overlay.style.display = 'none';
    _captureInput.value = '';
    _previewWrap.style.display = 'none';
    _previewImg.src = '';
    if (_sendBtn) { _sendBtn.style.display = 'none'; _sendBtn.disabled = false; }
    if (_serialStatus) _serialStatus.textContent = '';
  }

  // Poll for a pending serial capture task every 3 s.
  // Fires regardless of PIN state so the notification appears immediately;
  // the actual upload still requires the HMAC key (enforced server-side).
  if (_overlay && cfg.taskApiUrl) {
    setInterval(function () {
      if (_activeTask) return;           // already handling a task

      fetch(cfg.taskApiUrl, { credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.type === 'serial_capture' && data.task_id && !_activeTask) {
            _showOverlay(data.task_id);
          }
        })
        .catch(function () {});
    }, 3000);
  }

  // Auto-upload helper — called immediately after file is selected.
  function _doSerialUpload(file) {
    if (_serialStatus) _serialStatus.textContent = 'Sending\u2026';
    if (_sendBtn) _sendBtn.style.display = 'none';

    var fd = new FormData(form);   // includes csrfmiddlewaretoken + serial_task_id
    fd.set('image', file);

    fetch(cfg.uploadUrl, {
      method: 'POST',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        'X-Api-Key': apiKey,
      },
      body: fd,
    })
      .then(function (r) { return r.json(); })
      .then(function (json) {
        if (json.success) {
          if (_serialStatus) _serialStatus.textContent = '\u2705 Photo sent!';
          setTimeout(function () { _hideOverlay(); }, 1200);
        } else {
          if (_serialStatus) _serialStatus.textContent = '\u274c ' + (json.error || 'Upload failed. Try again.');
          if (_sendBtn) { _sendBtn.style.display = ''; _sendBtn.disabled = false; }
        }
      })
      .catch(function () {
        if (_serialStatus) _serialStatus.textContent = 'Network error. Try again.';
        if (_sendBtn) { _sendBtn.style.display = ''; _sendBtn.disabled = false; }
      });
  }

  // Photo selected — preview + auto-upload immediately (no extra tap needed)
  if (_captureInput) {
    _captureInput.addEventListener('change', function () {
      if (!_captureInput.files || !_captureInput.files[0]) return;
      var file = _captureInput.files[0];
      var reader = new FileReader();
      reader.onload = function (e) {
        _previewImg.src = e.target.result;
        _previewWrap.style.display = '';
      };
      reader.readAsDataURL(file);
      _doSerialUpload(file);
    });
  }

  // Retry button — shown only when upload fails
  if (_sendBtn) {
    _sendBtn.addEventListener('click', function () {
      if (!_captureInput || !_captureInput.files || !_captureInput.files[0]) return;
      _doSerialUpload(_captureInput.files[0]);
    });
  }

  // Cancel — pressing Cancel hides the overlay; the admin form will time out
  // and can retry if needed
  if (_cancelBtn) {
    _cancelBtn.addEventListener('click', function () { _hideOverlay(); });
  }
})();
