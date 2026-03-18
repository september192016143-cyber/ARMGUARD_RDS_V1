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

  // Create iframe dynamically ONLY after blob is ready.
  // Never use src="about:blank" — it fires CSP check for null/''/about: origin.
  // Born-with-blob-src iframes pass frame-src blob: and carry no X-Frame-Options.
  var container = document.getElementById('pdfContainer');
  var pdfUrl = container ? container.getAttribute('data-pdf-url') : null;
  if (pdfUrl) {
    fetch(pdfUrl, {credentials: 'same-origin'})
      .then(function (r) { return r.blob(); })
      .then(function (blob) {
        var iframe = document.createElement('iframe');
        iframe.style.cssText = 'width:100%;height:100vh;border:none;display:block';
        iframe.src = URL.createObjectURL(blob);
        iframe.addEventListener('load', function () { attemptPrint(); });
        container.appendChild(iframe);
        pdfLoadTimeout = setTimeout(function () { attemptPrint(); }, 3000);
      })
      .catch(function () {
        pdfLoadTimeout = setTimeout(function () { attemptPrint(); }, 1000);
      });
  } else {
    pdfLoadTimeout = setTimeout(function () { attemptPrint(); }, 2500);
  }

  window.onafterprint = function () {
    setTimeout(function () { window.close(); }, 1000);
  };
})();
