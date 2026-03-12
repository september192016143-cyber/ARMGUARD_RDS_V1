document.addEventListener('click', function (e) {
  var btn = e.target.closest('[data-action="print"]');
  if (btn) {
    var url = btn.getAttribute('data-print-url');
    if (url) {
      window.open(url, '_blank', 'width=900,height=700,scrollbars=yes,resizable=yes');
    } else {
      window.print();
    }
  }
});

// Auto-print when body carries data-autoprint (used by bare print pages).
// Close the popup window automatically after the print dialog is dismissed
// (whether the user clicked Print or Cancel).
if (document.body && document.body.hasAttribute('data-autoprint')) {
  window.addEventListener('load', function () {
    window.onafterprint = function () { window.close(); };
    window.print();
  });
}
