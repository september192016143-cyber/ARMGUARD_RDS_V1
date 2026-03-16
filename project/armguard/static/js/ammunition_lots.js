(function () {
  var input = document.getElementById('lot-q');
  var form  = document.getElementById('lot-filter-form');
  if (!input || !form) return;
  var timer;
  input.addEventListener('input', function () {
    clearTimeout(timer);
    timer = setTimeout(function () { form.submit(); }, 350);
  });
})();
