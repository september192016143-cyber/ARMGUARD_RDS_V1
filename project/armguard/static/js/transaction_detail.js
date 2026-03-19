(function () {
  var container = document.getElementById('tr-pdf-container');
  if (!container) return;
  var pdfUrl = container.getAttribute('data-pdf-url');
  if (!pdfUrl) return;

  // Load the PDF directly into an <iframe> using the authenticated same-origin
  // URL — no fetch, no blob URL needed.
  //
  // Why this avoids the CSP "Framing ''" violation:
  //   • frame-src 'self' covers same-origin URLs — the iframe src is allowed.
  //   • Chrome's PDF viewer creates internal sub-frames INSIDE the iframe, but
  //     the PDF response carries no CSP header (SecurityHeadersMiddleware skips
  //     non-HTML responses), so those internal sub-frames have no policy to
  //     violate — they never produce a "Framing ''" error.
  //   • The previous fetch→blob→iframe pattern triggered the violation because
  //     Chrome internally navigated the blob iframe to '' before the blob URL
  //     was committed, and '' does not match any frame-src directive.
  var iframe = document.createElement('iframe');
  iframe.title = 'TR PDF Preview';
  iframe.style.cssText = 'width:100%;height:100%;border:none;display:block;border-radius:0 0 .45rem .45rem';

  iframe.addEventListener('load', function () {
    // If the session expired Chrome will load the login redirect (HTML) into
    // the iframe. Detect that by checking whether contentDocument is accessible
    // (cross-origin PDF viewer blocks access; same-origin HTML is accessible).
    try {
      if (iframe.contentDocument && iframe.contentDocument.body &&
          iframe.contentDocument.body.innerText.length > 0) {
        container.innerHTML =
          '<div style="color:#94a3b8;padding:1.5rem;text-align:center">'
          + 'Session expired. <a href="' + pdfUrl + '" target="_blank" style="color:#60a5fa">Open PDF</a>'
          + '</div>';
      }
    } catch (e) { /* cross-origin PDF viewer — expected, means PDF loaded OK */ }
  });

  iframe.src = pdfUrl;
  container.innerHTML = '';
  container.style.display = 'block';
  container.appendChild(iframe);
})();
