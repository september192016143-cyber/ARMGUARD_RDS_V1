(function () {
  var container = document.getElementById('tr-pdf-container');
  if (!container) return;
  var pdfUrl = container.getAttribute('data-pdf-url');
  if (!pdfUrl) return;

  function showError(msg) {
    container.innerHTML =
      '<div style="color:#94a3b8;padding:1.5rem;text-align:center">'
      + 'PDF preview unavailable' + (msg ? ' (' + msg + ')' : '') + '. '
      + '<a href="' + pdfUrl + '" target="_blank" style="color:#60a5fa">Open PDF</a>'
      + '</div>';
  }

  // Fetch the PDF to verify the session is active, then render via <embed>.
  //
  // Why <embed> instead of <iframe>:
  //   Chrome's built-in PDF viewer creates internal sub-frames with src=''
  //   when rendering PDFs inside <iframe>. Those sub-frames are checked against
  //   the parent page's frame-src CSP directive, and '' matches nothing —
  //   producing "Framing '' violates frame-src 'self' blob: about:".
  //   <embed type="application/pdf"> is governed by object-src (already
  //   'self' blob:), not frame-src, so Chrome's internal PDF frames have no
  //   frame-src policy to violate.
  fetch(pdfUrl, {credentials: 'same-origin'})
    .then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.blob();
    })
    .then(function (blob) {
      // An HTML response means the session expired and Django returned the
      // login redirect page instead of the PDF.
      if (blob.type && blob.type.indexOf('text/html') !== -1) {
        throw new Error('Session expired');
      }
      var blobUrl = URL.createObjectURL(new Blob([blob], {type: 'application/pdf'}));
      var embed = document.createElement('embed');
      embed.setAttribute('type', 'application/pdf');
      embed.setAttribute('title', 'TR PDF Preview');
      embed.style.cssText = 'width:100%;height:100%;border:none;display:block;border-radius:0 0 .45rem .45rem';
      embed.src = blobUrl;
      container.innerHTML = '';
      container.style.display = 'block';
      container.appendChild(embed);
    })
    .catch(function (err) { showError(err ? err.message : ''); });
})();
