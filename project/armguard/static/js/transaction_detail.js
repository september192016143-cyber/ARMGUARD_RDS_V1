(function () {
  var container = document.getElementById('tr-pdf-container');
  if (!container) return;
  var pdfUrl    = container.getAttribute('data-pdf-url');
  var pdfjsUrl  = container.getAttribute('data-pdfjs-url');
  var workerUrl = container.getAttribute('data-pdfjs-worker');
  if (!pdfUrl || !pdfjsUrl || !workerUrl) return;

  function showError(msg) {
    container.innerHTML =
      '<div style="color:#94a3b8;padding:1.5rem;text-align:center">'
      + 'PDF preview unavailable' + (msg ? ' (' + msg + ')' : '') + '. '
      + '<a href="' + pdfUrl + '" target="_blank" style="color:#60a5fa">Open PDF</a>'
      + '</div>';
  }

  // Render every page of a parsed PDF.js document into targetEl as <canvas> nodes.
  // Pages are rendered sequentially to avoid excessive memory pressure.
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
          canvas.style.cssText = 'display:block;width:100%;margin-bottom:4px;'
                               + 'box-shadow:0 1px 6px rgba(0,0,0,.4);border-radius:.2rem;';
          targetEl.appendChild(canvas);
          return page.render({canvasContext: canvas.getContext('2d'), viewport: vp}).promise;
        });
      });
    }, Promise.resolve());
  }

  // 1. Fetch PDF bytes — session cookie is sent (credentials:'same-origin'),
  //    so Django's auth and audit logging in pdf_viewer.py fire as normal.
  // 2. Parse with PDF.js (dynamically imported from self-hosted static file).
  // 3. Render each page onto a <canvas> element.
  //    No <iframe>, no <embed> — zero frame-src / object-src CSP involvement.
  fetch(pdfUrl, {credentials: 'same-origin'})
    .then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.arrayBuffer();
    })
    .then(function (buffer) {
      return import(pdfjsUrl).then(function (pdfjsLib) {
        pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;
        return pdfjsLib.getDocument({data: buffer}).promise;
      });
    })
    .then(function (pdf) {
      container.innerHTML          = '';
      container.style.display      = 'block';
      container.style.alignItems   = '';
      container.style.justifyContent = '';
      container.style.overflowY    = 'auto';
      container.style.padding      = '8px';
      container.style.boxSizing    = 'border-box';
      return renderAllPages(pdf, container, 1.5);
    })
    .catch(function (err) { showError(err ? err.message : ''); });
})();
