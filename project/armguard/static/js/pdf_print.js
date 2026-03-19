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

  // Create iframe with src set directly to the PDF URL — no fetch, no blob.
  // Same-origin URL passes frame-src 'self' (CSP) and X-Frame-Options SAMEORIGIN.
  // Setting src before appending avoids any about:blank navigation.
  var container = document.getElementById('pdfContainer');
  var pdfUrl = container ? container.getAttribute('data-pdf-url') : null;
  if (pdfUrl) {
    var iframe = document.createElement('iframe');
    iframe.style.cssText = 'width:100%;height:100vh;border:none;display:block';
    iframe.src = pdfUrl;
    iframe.addEventListener('load', function () { attemptPrint(); });
    container.appendChild(iframe);
    pdfLoadTimeout = setTimeout(function () { attemptPrint(); }, 3000);
  } else {
    pdfLoadTimeout = setTimeout(function () { attemptPrint(); }, 2500);
  }

  window.onafterprint = function () {
    setTimeout(function () { window.close(); }, 1000);
  };
})();
