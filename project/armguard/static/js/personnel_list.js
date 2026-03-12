(function () {
  const form = document.getElementById('personnel-filter-form');
  const qInput = document.getElementById('personnel-q');
  const selects = [document.getElementById('personnel-category'), document.getElementById('personnel-group')];
  if (!form) return;
  let debounceTimer;

  qInput.addEventListener('input', function () {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(function () { form.submit(); }, 350);
  });

  selects.forEach(function (sel) {
    if (sel) sel.addEventListener('change', function () { form.submit(); });
  });
})();
