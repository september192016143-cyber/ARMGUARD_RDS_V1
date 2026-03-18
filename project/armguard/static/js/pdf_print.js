(function () {
  var printAttempted = false;
  var pdfLoadTimeout = null;

  function attemptPrint() {
    if (printAttempted) return;
    printAttempted = true;
    if (pdfLoadTimeout) clearTimeout(pdfLoadTimeout);
    try {
      // iframe blob URL: can use contentWindow.print() for cleaner print output.
      var frame = document.getElementById('pdfFrame');
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

  // Fetch PDF as blob — blob: URLs have no HTTP headers so X-Frame-Options
  // is never checked. Chrome renders PDFs inline in iframes with blob URLs.
  // CSP frame-src blob: allows this.
  var pdfFrame = document.getElementById('pdfFrame');
  var pdfUrl = pdfFrame ? pdfFrame.getAttribute('data-pdf-url') : null;
  if (pdfUrl) {
    fetch(pdfUrl, {credentials: 'same-origin'})
      .then(function (r) { return r.blob(); })
      .then(function (blob) {
        pdfFrame.src = URL.createObjectURL(blob);
        pdfLoadTimeout = setTimeout(function () { attemptPrint(); }, 2500);
      })
      .catch(function () {
        pdfFrame.src = pdfUrl;
        pdfLoadTimeout = setTimeout(function () { attemptPrint(); }, 2500);
      });
  } else {
    pdfLoadTimeout = setTimeout(function () { attemptPrint(); }, 2500);
  }

  window.onafterprint = function () {
    setTimeout(function () { window.close(); }, 1000);
  };
})();
