(function () {
  var form          = document.getElementById('personnel-filter-form');
  var qInput        = document.getElementById('personnel-q');
  var catSelect     = document.getElementById('personnel-category');
  var groupSelect   = document.getElementById('personnel-group');
  var squadronSelect= document.getElementById('personnel-squadron');
  var resultsDiv    = document.getElementById('personnel-results');
  var countSpan     = document.getElementById('personnel-count');
  if (!form || !resultsDiv) return;

  var baseUrl = form.dataset.url || window.location.pathname;
  var debounceTimer;

  // ── AJAX fetch ────────────────────────────────────────────────────────────
  function buildParams(page) {
    var params = new URLSearchParams();
    if (qInput.value.trim())              params.set('q',        qInput.value.trim());
    if (catSelect     && catSelect.value)     params.set('category', catSelect.value);
    if (groupSelect   && groupSelect.value)   params.set('group',    groupSelect.value);
    if (squadronSelect && squadronSelect.value) params.set('squadron', squadronSelect.value);
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
        var pageMatch = href.match(/[?&]page=(\d+)/);
        var page = pageMatch ? parseInt(pageMatch[1]) : 1;
        doFetch(buildParams(page));
      });
    });
  }

  // ── Input listeners ───────────────────────────────────────────────────────
  qInput.addEventListener('input', function () {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(function () { doFetch(buildParams(1)); }, 400);
  });
  if (catSelect)      catSelect.addEventListener('change',      function () { doFetch(buildParams(1)); });
  if (groupSelect)    groupSelect.addEventListener('change',    function () { doFetch(buildParams(1)); });
  if (squadronSelect) squadronSelect.addEventListener('change', function () { doFetch(buildParams(1)); });

  bindPagination();

  // ── Background QR / barcode scanner listener ──────────────────────────────
  // Keyboard-wedge scanners fire keystrokes very fast (≤50 ms gap) and end
  // with Enter. We intercept in the capture phase so the event lands here even
  // when a select/textarea has focus.
  (function () {
    var buf = '';
    var lastKey = 0;
    var scanning = false;
    var SCANNER_SPEED = 50;
    var MIN_LEN = 3;

    function showToast(msg, ok) {
      var t = document.getElementById('personnel-qr-toast');
      if (!t) {
        t = document.createElement('div');
        t.id = 'personnel-qr-toast';
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
