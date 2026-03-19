(function () {
  var container = document.getElementById('tr-pdf-container');
  if (!container) return;
  var pdfUrl = container.getAttribute('data-pdf-url');
  if (!pdfUrl) return;

  fetch(pdfUrl, {credentials: 'same-origin'})
    .then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.blob();
    })
    .then(function (blob) {
      // Force application/pdf so Chrome's built-in PDF viewer picks it up,
      // regardless of what MIME type the server echoed in Content-Type.
      var pdfBlob = new Blob([blob], {type: 'application/pdf'});
      var iframe = document.createElement('iframe');
      iframe.style.cssText = 'width:100%;height:100%;border:none;display:block;border-radius:0 0 .45rem .45rem';
      iframe.title = 'TR PDF Preview';
      iframe.src = URL.createObjectURL(pdfBlob);
      container.innerHTML = '';
      container.style.display = 'block';
      container.appendChild(iframe);
    })
    .catch(function (err) {
      container.innerHTML =
        '<div style="color:#94a3b8;padding:1.5rem;text-align:center">'
        + 'PDF preview unavailable' + (err ? ' (' + err.message + ')' : '') + '. '
        + '<a href="' + pdfUrl + '" target="_blank" style="color:#60a5fa">Open PDF</a>'
        + '</div>';
    });
})();
