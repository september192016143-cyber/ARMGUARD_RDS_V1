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

  // Load PDF.js via direct import(). Nginx serves .mjs as text/javascript
  // (patched by update-server.sh). Same-origin URL — allowed by CSP script-src 'self'.
  function importPdfjsViaBlob(url) {
    return import(url);
  }

  // 1. Fetch PDF bytes — session cookie is sent (credentials:'same-origin'),
  //    so Django's auth and audit logging in pdf_viewer.py fire as normal.
  // 2. Parse with PDF.js (imported via blob URL to sidestep MIME type enforcement).
  // 3. Render each page onto a <canvas> element.
  //    No <iframe>, no <embed> — zero frame-src / object-src CSP involvement.
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

// ── Personnel typeahead + QR/barcode scanner ──────────────────────────────────
(function () {
  var card     = document.getElementById('td-personnel-card');
  var input    = document.getElementById('td-personnel-search');
  var dropdown = document.getElementById('td-personnel-results');
  if (!card || !input || !dropdown) return;

  var SEARCH_URL  = card.dataset.searchUrl;
  var DETAIL_BASE = card.dataset.detailBase; // e.g. /personnel/
  var debounceTimer;
  var DEBOUNCE = 300;

  function escHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function renderResults(results) {
    if (!results.length) {
      dropdown.innerHTML = '<div style="padding:.45rem .7rem;font-size:.72rem;color:var(--muted,#64748b)">No results</div>';
      dropdown.style.display = 'block';
      return;
    }
    dropdown.innerHTML = results.map(function (r) {
      return '<div class="td-ps-item" data-id="' + escHtml(r.id) + '"'
        + ' style="padding:.4rem .7rem;font-size:.72rem;cursor:pointer;border-bottom:1px solid var(--border,#334155)">'
        + '<span style="font-weight:600">' + escHtml(r.last_name) + ', ' + escHtml(r.first_name) + '</span>'
        + ' <span style="color:var(--muted,#64748b)">' + escHtml(r.rank) + '</span>'
        + '<br><span style="font-size:.67rem;color:var(--muted,#64748b)">AFSN: ' + escHtml(r.AFSN)
        + ' \u00b7 ID: ' + escHtml(r.id) + '</span>'
        + '</div>';
    }).join('');
    dropdown.style.display = 'block';
  }

  function closeDropdown() {
    dropdown.style.display = 'none';
    dropdown.innerHTML = '';
  }

  function doSearch(q) {
    q = q.trim();
    if (q.length < 2) { closeDropdown(); return; }
    fetch(SEARCH_URL + '?q=' + encodeURIComponent(q), { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) { renderResults(d.results || []); })
      .catch(function () { closeDropdown(); });
  }

  function navigateTo(personnelId) {
    var url = DETAIL_BASE + encodeURIComponent(personnelId) + '/';
    closeDropdown();
    input.value = '';
    if (typeof window.pjaxNavigate === 'function') {
      window.pjaxNavigate(url);
    } else {
      window.location.href = url;
    }
  }

  // Hover highlight
  dropdown.addEventListener('mouseover', function (e) {
    var item = e.target.closest('.td-ps-item');
    if (item) item.style.background = 'var(--hover-bg,#334155)';
  });
  dropdown.addEventListener('mouseout', function (e) {
    var item = e.target.closest('.td-ps-item');
    if (item) item.style.background = '';
  });
  dropdown.addEventListener('click', function (e) {
    var item = e.target.closest('.td-ps-item');
    if (item) navigateTo(item.dataset.id);
  });

  input.addEventListener('input', function () {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(function () { doSearch(input.value); }, DEBOUNCE);
  });

  // Close dropdown on outside click
  document.addEventListener('click', function (e) {
    if (!input.contains(e.target) && !dropdown.contains(e.target)) closeDropdown();
  }, window.pjaxController ? { signal: window.pjaxController.signal } : {});

  // ── QR / barcode scanner (keyboard-wedge) ─────────────────────────────────
  // Same pattern as personnel_list.js: fast keystrokes (≤50 ms) ending with
  // Enter are treated as a scanner burst and routed to the search field.
  (function () {
    var buf          = '';
    var lastKey      = 0;
    var scanning     = false;
    var SCANNER_SPEED = 50;
    var MIN_LEN      = 3;

    function handleScan(val) {
      input.value = val;
      closeDropdown();
      doSearch(val);
    }

    document.addEventListener('keydown', function (e) {
      var now = Date.now();
      var gap = now - lastKey;

      if (e.key === 'Enter') {
        if (scanning && buf.length >= MIN_LEN) {
          e.preventDefault();
          e.stopPropagation();
          handleScan(buf);
        }
        buf = '';
        scanning = false;
        lastKey = 0;
        return;
      }

      if (e.key.length !== 1) return;

      if (buf.length === 0) {
        buf = e.key;
        scanning = false;
      } else if (gap <= SCANNER_SPEED) {
        buf += e.key;
        scanning = true;
        e.preventDefault();
        e.stopPropagation();
      } else {
        buf = e.key;
        scanning = false;
      }
      lastKey = now;
    }, window.pjaxController ? { capture: true, signal: window.pjaxController.signal } : true);
  })();
})();
