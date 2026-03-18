(function () {
  var printAttempted = false;
  var pdfLoadTimeout = null;

  function attemptPrint() {
    if (printAttempted) return;
    printAttempted = true;
    if (pdfLoadTimeout) clearTimeout(pdfLoadTimeout);
    try {
      // <object> has no contentWindow — use window.print() directly.
      // Chrome prints the embedded PDF content when window.print() is called.
      window.print();
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

  // Use blob fetch so X-Frame-Options DENY on server never applies
  // (blob: URLs have no HTTP headers; Chrome's embed PDF viewer renders them fine).
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
