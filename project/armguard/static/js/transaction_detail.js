(function () {
  var container = document.getElementById('tr-pdf-container');
  if (!container) return;
  var pdfUrl = container.getAttribute('data-pdf-url');
  if (!pdfUrl) return;

  fetch(pdfUrl, {credentials: 'same-origin'})
    .then(function (r) { return r.blob(); })
    .then(function (blob) {
      // Create the iframe ONLY after we have the blob URL.
      // The iframe never has src="about:blank" — it's born with a blob: src.
      // Blob URLs carry no HTTP headers so X-Frame-Options is never checked.
      // CSP frame-src blob: allows it. No null-origin CSP violation.
      var iframe = document.createElement('iframe');
      iframe.style.cssText = 'width:100%;height:100%;border:none;display:block;border-radius:0 0 .45rem .45rem';
      iframe.title = 'TR PDF Preview';
      iframe.src = URL.createObjectURL(blob);
      container.innerHTML = '';
      container.style.display = 'block';
      container.appendChild(iframe);
    })
    .catch(function () {
      container.innerHTML =
        '<div style="color:#94a3b8;padding:1.5rem;text-align:center">'
        + 'PDF preview unavailable. '
        + '<a href="' + pdfUrl + '" target="_blank" style="color:#60a5fa">Open PDF</a>'
        + '</div>';
    });
})();
