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

  // Use fetch to verify the endpoint is reachable and returns PDF before
  // rendering.  The response blob is loaded via <embed> (object-src 'self'
  // blob:) instead of <iframe> (frame-src) to avoid Chrome PDF viewer
  // creating internal empty-src sub-frames that violate frame-src CSP.
  fetch(pdfUrl, {credentials: 'same-origin'})
    .then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.blob();
    })
    .then(function (blob) {
      // Verify the response is actually a PDF (not an HTML redirect/error page).
      if (blob.type && blob.type.indexOf('text/html') !== -1) {
        throw new Error('Unexpected HTML response');
      }
      var pdfBlob = new Blob([blob], {type: 'application/pdf'});
      var blobUrl = URL.createObjectURL(pdfBlob);

      // <embed> uses object-src CSP directive (already allows blob:).
      // Unlike <iframe>, Chrome's PDF viewer inside <embed> does NOT create
      // internal sub-frames — eliminating the "Framing ''" CSP violation.
      var embed = document.createElement('embed');
      embed.setAttribute('type', 'application/pdf');
      embed.setAttribute('title', 'TR PDF Preview');
      embed.style.cssText = 'width:100%;height:100%;border:none;display:block;border-radius:0 0 .45rem .45rem';
      embed.src = blobUrl;

      container.innerHTML = '';
      container.style.display = 'block';
      container.appendChild(embed);
    })
    .catch(function (err) { showError(err ? err.message : ''); });
})();
