document.addEventListener('click', function (e) {
  if (e.target && e.target.getAttribute('data-action') === 'print') {
    window.print();
  }
});
