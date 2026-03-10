(function () {
  var printAttempted = false;
  var pdfLoadTimeout = null;

  function attemptPrint() {
    if (printAttempted) return;
    printAttempted = true;
    if (pdfLoadTimeout) clearTimeout(pdfLoadTimeout);
    try {
      var iframe = document.getElementById('pdfFrame');
      if (iframe.contentWindow) {
        iframe.contentWindow.print();
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

  var pdfFrame = document.getElementById('pdfFrame');
  pdfFrame.addEventListener('load', function () { attemptPrint(); });
  pdfLoadTimeout = setTimeout(function () { attemptPrint(); }, 2000);

  window.onafterprint = function () {
    setTimeout(function () { window.close(); }, 1000);
  };
})();
