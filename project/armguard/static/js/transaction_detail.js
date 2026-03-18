(function () {
  var iframe = document.getElementById('tr-pdf-iframe');
  if (!iframe) return;
  var pdfUrl = iframe.getAttribute('data-pdf-url');
  if (!pdfUrl) return;
  fetch(pdfUrl, {credentials: 'same-origin'})
    .then(function (r) { return r.blob(); })
    .then(function (blob) {
      var url = URL.createObjectURL(blob);
      iframe.src = url + '#toolbar=1&view=FitH';
    })
    .catch(function () {
      iframe.src = pdfUrl;
    });
})();
