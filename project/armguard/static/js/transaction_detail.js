(function () {
  var iframe = document.getElementById('tr-pdf-iframe');
  if (!iframe) return;
  var pdfUrl = iframe.getAttribute('data-pdf-url');
  if (!pdfUrl) return;
  fetch(pdfUrl, {credentials: 'same-origin'})
    .then(function (r) { return r.blob(); })
    .then(function (blob) {
      // blob: URLs have no HTTP headers — X-Frame-Options is never checked.
      // CSP frame-src blob: allows this. Chrome renders PDFs inline in iframes
      // with blob URLs (unlike embed+blob which shows a file card).
      iframe.src = URL.createObjectURL(blob);
    })
    .catch(function () {
      iframe.src = pdfUrl;
    });
})();
