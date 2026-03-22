(function () {
  var form          = document.getElementById('txn-filter-form');
  var qInput        = document.getElementById('txn-q');
  var typeSelect    = document.getElementById('txn-type');
  var issuanceSelect= document.getElementById('txn-issuance');
  var resultsDiv    = document.getElementById('txn-results');
  var countSpan     = document.getElementById('txn-count');
  if (!form || !resultsDiv) return;

  var baseUrl = form.dataset.url || window.location.pathname;
  var debounceTimer;

  // Keep date range from the current URL so calendar filter stays active
  function getDateParams() {
    var p = new URLSearchParams(window.location.search);
    return { date_from: p.get('date_from') || '', date_to: p.get('date_to') || '' };
  }

  // ── AJAX fetch ────────────────────────────────────────────────────────────
  function buildParams(page) {
    var params = new URLSearchParams();
    if (qInput.value.trim()) params.set('q', qInput.value.trim());
    if (typeSelect && typeSelect.value) params.set('type', typeSelect.value);
    if (issuanceSelect && issuanceSelect.value) params.set('issuance', issuanceSelect.value);
    var dates = getDateParams();
    if (dates.date_from) params.set('date_from', dates.date_from);
    if (dates.date_to)   params.set('date_to',   dates.date_to);
    if (page && page > 1) params.set('page', page);
    return params;
  }

  function doFetch(params) {
    fetch(baseUrl + '?' + params.toString(), {
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
    .then(function (r) { return r.text(); })
    .then(function (html) {
      resultsDiv.innerHTML = html;
      var countEl = resultsDiv.querySelector('#ajax-count');
      if (countEl && countSpan) {
        countSpan.textContent = countEl.dataset.count + ' records';
      }
      bindPagination();
    });
  }

  function bindPagination() {
    resultsDiv.querySelectorAll('.page-link[href]').forEach(function (a) {
      a.addEventListener('click', function (e) {
        e.preventDefault();
        var href = a.getAttribute('href');
        var m = href.match(/[?&]page=(\d+)/);
        doFetch(buildParams(m ? parseInt(m[1]) : 1));
      });
    });
  }

  // ── Input listeners ───────────────────────────────────────────────────────
  qInput.addEventListener('input', function () {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(function () { doFetch(buildParams(1)); }, 400);
  });
  if (typeSelect)     typeSelect.addEventListener('change',     function () { doFetch(buildParams(1)); });
  if (issuanceSelect) issuanceSelect.addEventListener('change', function () { doFetch(buildParams(1)); });

  bindPagination();

  // ── Background QR / barcode scanner listener ──────────────────────────────
  (function () {
    var buf = '';
    var lastKey = 0;
    var scanning = false;
    var SCANNER_SPEED = 50;
    var MIN_LEN = 3;

    function showToast(msg, ok) {
      var t = document.getElementById('txn-qr-toast');
      if (!t) {
        t = document.createElement('div');
        t.id = 'txn-qr-toast';
        t.style.cssText = 'position:fixed;bottom:1.5rem;right:1.5rem;padding:.6rem 1.1rem;border-radius:.5rem;font-size:.85rem;font-weight:600;z-index:9999;transition:opacity .4s;pointer-events:none';
        document.body.appendChild(t);
      }
      t.style.background = ok ? '#166534' : '#7f1d1d';
      t.style.color = '#fff';
      t.textContent = msg;
      t.style.opacity = '1';
      clearTimeout(t._hide);
      t._hide = setTimeout(function () { t.style.opacity = '0'; }, 2500);
    }

    function handleScan(val) {
      qInput.value = val;
      showToast('\u2713 Scanning: ' + val, true);
      clearTimeout(debounceTimer);
      doFetch(buildParams(1));
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
