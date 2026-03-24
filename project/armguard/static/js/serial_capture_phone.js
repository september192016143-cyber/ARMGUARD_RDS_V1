/**
 * serial_capture_phone.js
 * Handles the phone-facing serial image capture page.
 * Upload URL is read from <meta name="armguard-upload-url">.
 */
(function () {
  var uploadUrl = (document.querySelector('meta[name="armguard-upload-url"]') || {}).content;
  if (!uploadUrl) return;

  var fileInput  = document.getElementById('file-input');
  var preview    = document.getElementById('preview');
  var sendBtn    = document.getElementById('send-btn');
  var takeBtn    = document.getElementById('take-btn');
  var retakeBtn  = document.getElementById('retake-btn');
  var statusEl   = document.getElementById('status');
  var selectedFile = null;

  if (!fileInput) return;

  takeBtn.addEventListener('click', function () { fileInput.click(); });
  if (retakeBtn) retakeBtn.addEventListener('click', function () { fileInput.click(); });

  fileInput.addEventListener('change', function () {
    var file = fileInput.files[0];
    if (!file) return;
    selectedFile = file;
    var url = URL.createObjectURL(file);
    preview.onload = function () { URL.revokeObjectURL(url); };
    preview.src = url;
    preview.style.display = 'block';
    sendBtn.disabled = false;
    if (retakeBtn) retakeBtn.style.display = '';
    statusEl.textContent = '';
    statusEl.className = 'status';
  });

  sendBtn.addEventListener('click', function () {
    if (!selectedFile) return;
    sendBtn.disabled = true;
    takeBtn.disabled = true;
    if (retakeBtn) retakeBtn.disabled = true;
    statusEl.textContent = 'Uploading\u2026';
    statusEl.className = 'status';

    var fd = new FormData();
    fd.append('image', selectedFile);

    fetch(uploadUrl, { method: 'POST', body: fd })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.success) {
          statusEl.textContent = '\u2713 Photo sent! The admin can see it now.';
          statusEl.className = 'status success';
          sendBtn.textContent = '\u2714 Sent';
          takeBtn.disabled = false;
          if (retakeBtn) retakeBtn.disabled = false;
        } else {
          statusEl.textContent = data.error || 'Upload failed. Try again.';
          statusEl.className = 'status error';
          sendBtn.disabled = false;
          takeBtn.disabled = false;
          if (retakeBtn) retakeBtn.disabled = false;
        }
      })
      .catch(function () {
        statusEl.textContent = 'Network error. Please try again.';
        statusEl.className = 'status error';
        sendBtn.disabled = false;
        takeBtn.disabled = false;
        if (retakeBtn) retakeBtn.disabled = false;
      });
  });
})();
