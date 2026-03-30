(function () {
  var printAttempted = false;
  var fallbackTimer  = null;
  var printTimer     = null;

  function attemptPrint() {
    if (printAttempted) return;
    printAttempted = true;
    if (fallbackTimer) clearTimeout(fallbackTimer);
    if (printTimer)    clearTimeout(printTimer);
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

  // Render PDF via PDF.js onto <canvas> elements, then auto-print.
  // PDF.js uses fetch→ArrayBuffer→<canvas> — no <embed>, no <iframe>,
  // zero frame-src / object-src CSP involvement.
  // The Web Worker (pdf.worker.min.mjs) is same-origin → worker-src 'self'.
  var container = document.getElementById('pdfContainer');
  var pdfUrl    = container ? container.getAttribute('data-pdf-url')      : null;
  var pdfjsUrl  = container ? container.getAttribute('data-pdfjs-url')    : null;
  var workerUrl = container ? container.getAttribute('data-pdfjs-worker') : null;

  if (pdfUrl && pdfjsUrl && workerUrl) {
    // Scale for rendering. CSS width:100% rescales to fit the container
    // regardless of pixel count, so this only affects sharpness.
    // 1.5 is sufficient for legal-size print quality.
    var PRINT_SCALE = 1.5;

    function renderAllPages(pdf, targetEl, scale) {
      var pageNums = [];
      for (var i = 1; i <= pdf.numPages; i++) pageNums.push(i);
      return pageNums.reduce(function (chain, num) {
        return chain.then(function () {
          return pdf.getPage(num).then(function (page) {
            var vp     = page.getViewport({scale: scale});
            var canvas = document.createElement('canvas');
            canvas.width  = vp.width;
            canvas.height = vp.height;
            canvas.style.cssText = 'display:block;width:100%;margin:0;';
            targetEl.appendChild(canvas);
            return page.render({canvasContext: canvas.getContext('2d'), viewport: vp}).promise;
          });
        });
      }, Promise.resolve());
    }

    // import() enforces strict MIME checking; bypass by fetching as text and
    // creating a correctly-typed Blob URL (browser checks Blob MIME, not server header).
    function importPdfjsViaBlob(url) {
      return fetch(url)
        .then(function (r) {
          if (!r.ok) throw new Error('PDF.js load failed: HTTP ' + r.status);
          return r.text();
        })
        .then(function (src) {
          var blob    = new Blob([src], {type: 'text/javascript'});
          var blobUrl = URL.createObjectURL(blob);
          return import(blobUrl).then(function (mod) {
            URL.revokeObjectURL(blobUrl);
            return mod;
          });
        });
    }

    fetch(pdfUrl, {credentials: 'same-origin'})
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.arrayBuffer();
      })
      .then(function (buffer) {
        return importPdfjsViaBlob(pdfjsUrl).then(function (pdfjsLib) {
          pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;
          return pdfjsLib.getDocument({data: buffer}).promise;
        });
      })
      .then(function (pdf) {
        return renderAllPages(pdf, container, PRINT_SCALE);
      })
      .then(function () {
        // All pages rendered — small delay lets the browser paint before the dialog.
        printTimer = setTimeout(function () { attemptPrint(); }, 300);
      })
      .catch(function () {
        // Fetch / parse error — still open print dialog so the user isn't stuck.
        printTimer = setTimeout(function () { attemptPrint(); }, 500);
      });

    // Hard fallback: if PDF.js never resolves (network hang), print after 8 s.
    fallbackTimer = setTimeout(function () { attemptPrint(); }, 8000);
  } else {
    fallbackTimer = setTimeout(function () { attemptPrint(); }, 2500);
  }

  window.onafterprint = function () {
    setTimeout(function () { window.close(); }, 1000);
  };
})();
