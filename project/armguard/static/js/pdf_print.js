(function () {
  var printAttempted = false;
  var pdfLoadTimeout = null;

  function attemptPrint() {
    if (printAttempted) return;
    printAttempted = true;
    if (pdfLoadTimeout) clearTimeout(pdfLoadTimeout);
    try {
      window.print();
      setTimeout(function () {
        var inst = document.getElementById('print-instructions');
        if (inst) inst.style.display = 'none';
      }, 1000);
    } catch (e) {
      alert('Print failed. Please use Ctrl+P to print manually.');
    }
  }

  // Use fetch→blob→<embed type="application/pdf">.
  // <embed> is governed by object-src (already 'self' blob:), NOT frame-src,
  // so Chrome's internal PDF viewer sub-frames never trigger frame-src CSP
  // violations ("Framing '' violates frame-src ...").
  var container = document.getElementById('pdfContainer');
  var pdfUrl = container ? container.getAttribute('data-pdf-url') : null;
  if (pdfUrl) {
    fetch(pdfUrl, {credentials: 'same-origin'})
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.blob();
      })
      .then(function (blob) {
        var blobUrl = URL.createObjectURL(new Blob([blob], {type: 'application/pdf'}));
        var embed = document.createElement('embed');
        embed.setAttribute('type', 'application/pdf');
        embed.style.cssText = 'width:100%;height:100vh;border:none;display:block;';
        // <embed> fires a load event in most browsers once the PDF is rendered.
        embed.addEventListener('load', function () { attemptPrint(); });
        embed.src = blobUrl;
        container.appendChild(embed);
        // Fallback: trigger print after 4 s in case load event does not fire.
        pdfLoadTimeout = setTimeout(function () { attemptPrint(); }, 4000);
      })
      .catch(function () {
        // If fetch fails (session expired, network error), attempt print anyway
        // so the user at least gets the browser print dialog on the blank page.
        pdfLoadTimeout = setTimeout(function () { attemptPrint(); }, 1000);
      });
  } else {
    pdfLoadTimeout = setTimeout(function () { attemptPrint(); }, 2500);
  }

  window.onafterprint = function () {
    setTimeout(function () { window.close(); }, 1000);
  };
})();
