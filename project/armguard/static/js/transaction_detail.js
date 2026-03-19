(function () {
  var container = document.getElementById('tr-pdf-container');
  if (!container) return;
  var pdfUrl = container.getAttribute('data-pdf-url');
  if (!pdfUrl) return;

  // Create the iframe with src already set — it navigates directly to the PDF
  // URL without ever having src="about:blank". Same-origin URL passes both
  // frame-src 'self' (CSP) and X-Frame-Options SAMEORIGIN (Nginx).
  var iframe = document.createElement('iframe');
  iframe.style.cssText = 'width:100%;height:100%;border:none;display:block;border-radius:0 0 .45rem .45rem';
  iframe.title = 'TR PDF Preview';
  iframe.src = pdfUrl;
  container.innerHTML = '';
  container.style.display = 'block';
  container.appendChild(iframe);
})();
