(function () {
  const form = document.getElementById('personnel-filter-form');
  const qInput = document.getElementById('personnel-q');
  const catSelect = document.getElementById('personnel-category');
  const groupSelect = document.getElementById('personnel-group');
  const resultsDiv = document.getElementById('personnel-results');
  const countSpan = document.getElementById('personnel-count');
  if (!form || !resultsDiv) return;

  const baseUrl = form.dataset.url || form.getAttribute('action') || window.location.pathname;
  let debounceTimer;

  function buildParams(page) {
    var params = new URLSearchParams();
    if (qInput.value.trim()) params.set('q', qInput.value.trim());
    if (catSelect && catSelect.value) params.set('category', catSelect.value);
    if (groupSelect && groupSelect.value) params.set('group', groupSelect.value);
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

  qInput.addEventListener('input', function () {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(function () { doFetch(buildParams(1)); }, 400);
  });

  if (catSelect) catSelect.addEventListener('change', function () { doFetch(buildParams(1)); });
  if (groupSelect) groupSelect.addEventListener('change', function () { doFetch(buildParams(1)); });

  bindPagination();
})();
