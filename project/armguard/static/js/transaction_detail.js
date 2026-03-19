(function () {
  var container = document.getElementById('tr-pdf-container');
  if (!container) return;
  var pdfUrl = container.getAttribute('data-pdf-url');
  if (!pdfUrl) return;

  function showError(msg) {
    container.innerHTML =
      '<div style="color:#94a3b8;padding:1.5rem;text-align:center">'
      + 'PDF preview unavailable' + (msg ? ' (' + msg + ')' : '') + '. '
      + '<a href="' + pdfUrl + '" target="_blank" style="color:#60a5fa">Open PDF</a>'
      + '</div>';
  }

  // fetch() is not a framing request — X-Frame-Options is never checked.
  // The resulting blob URL has no HTTP headers, so neither X-Frame-Options
  // nor CSP frame-src applies to the blob itself. The iframe is created
  // AFTER the fetch with src=blob: directly — no about:blank ever.
  fetch(pdfUrl, {credentials: 'same-origin'})
    .then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.blob();
    })
    .then(function (blob) {
      var pdfBlob = new Blob([blob], {type: 'application/pdf'});
      var blobUrl = URL.createObjectURL(pdfBlob);
      var iframe = document.createElement('iframe');
      iframe.style.cssText = 'width:100%;height:100%;border:none;display:block;border-radius:0 0 .45rem .45rem';
      iframe.title = 'TR PDF Preview';
      // If Chrome PDF viewer fails to render, show download link instead
      iframe.addEventListener('load', function () {
        try {
          // contentDocument is null for PDF blobs rendered by the PDF viewer
          // — that is the SUCCESS case. An accessible contentDocument means
          // the iframe loaded an HTML error page instead.
          if (iframe.contentDocument && iframe.contentDocument.body) {
            var body = iframe.contentDocument.body.innerText || '';
            if (body.length > 0) showError('PDF render failed');
          }
        } catch (e) { /* cross-origin blob — expected, means PDF viewer took over */ }
      });
      iframe.src = blobUrl;
      container.innerHTML = '';
      container.style.display = 'block';
      container.appendChild(iframe);
    })
    .catch(function (err) { showError(err ? err.message : ''); });
})();
