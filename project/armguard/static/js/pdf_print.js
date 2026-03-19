(function () {
  var printAttempted = false;
  var pdfLoadTimeout = null;

  function attemptPrint() {
    if (printAttempted) return;
    printAttempted = true;
    if (pdfLoadTimeout) clearTimeout(pdfLoadTimeout);
    try {
      // Try to print via iframe contentWindow for cleaner output.
      var frame = document.querySelector('#pdfContainer iframe');
      if (frame && frame.contentWindow) {
        frame.contentWindow.print();
      } else {
        window.print();
      }
      setTimeout(function () {
        var inst = document.getElementById('print-instructions');
        if (inst) inst.style.display = 'none';
      }, 1000);
    } catch (e) {
      try { window.print(); } catch (e2) {
        alert('Print failed. Please use Ctrl+P to print manually.');
      }
    }
  }

  // Load the PDF directly into an <iframe> using the authenticated same-origin
  // URL.  The PDF response carries no X-Frame-Options or CSP (SecurityHeaders
  // middleware skips non-HTML responses), so direct framing is safe.
  // This avoids the fetch→blob→iframe pattern that caused Chrome PDF viewer
  // to create internal empty-src sub-frames violating frame-src CSP.
  var container = document.getElementById('pdfContainer');
  var pdfUrl = container ? container.getAttribute('data-pdf-url') : null;
  if (pdfUrl) {
    var iframe = document.createElement('iframe');
    iframe.style.cssText = 'width:100%;height:100vh;border:none;display:block';
    iframe.addEventListener('load', function () {
      // Verify the iframe loaded PDF and not an HTML redirect/error page.
      try {
        if (iframe.contentDocument && iframe.contentDocument.body) {
          // Accessible contentDocument means it's HTML (auth redirect, error).
          // Fall back to window.print() after a short delay.
          pdfLoadTimeout = setTimeout(function () { attemptPrint(); }, 500);
          return;
        }
      } catch (e) { /* cross-origin PDF viewer — expected success case */ }
      attemptPrint();
    });
    iframe.src = pdfUrl;
    container.appendChild(iframe);
    pdfLoadTimeout = setTimeout(function () { attemptPrint(); }, 4000);
  } else {
    pdfLoadTimeout = setTimeout(function () { attemptPrint(); }, 2500);
  }

  window.onafterprint = function () {
    setTimeout(function () { window.close(); }, 1000);
  };
})();
