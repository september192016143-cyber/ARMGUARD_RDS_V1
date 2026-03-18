(function () {
  var embed = document.getElementById('tr-pdf-embed');
  if (!embed) return;
  var pdfUrl = embed.getAttribute('data-pdf-url');
  if (!pdfUrl) return;
  fetch(pdfUrl, {credentials: 'same-origin'})
    .then(function (r) { return r.blob(); })
    .then(function (blob) {
      embed.src = URL.createObjectURL(blob);
    })
    .catch(function () {
      embed.src = pdfUrl;
    });
})();
