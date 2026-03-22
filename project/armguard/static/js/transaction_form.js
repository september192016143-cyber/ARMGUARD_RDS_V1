/**
 * ArmGuard RDS — transaction_form.js
 *
 * F1  FIX: Extracted from transaction_form.html to comply with CSP script-src 'self'
 *          (no 'unsafe-inline' needed).  All inline <script> blocks and inline event
 *          handler attributes (onclick=, onchange=, onfocus=, onblur=) removed from the
 *          template.  Server-side URLs injected via data-* attributes on the form element.
 *
 * F2  FIX: escHtml() wraps all server-returned strings before innerHTML insertion to
 *          prevent stored-XSS from manipulated DB records.
 *
 * F7  FIX: 300 ms debounce on personnel/item change events — prevents rapid-fire fetch
 *          requests when keyboard-navigating through dropdown options.
 *
 * F8  FIX: credentials:'same-origin' added to every fetch() call.
 *
 * F9  FIX: openTrPreview inner resp.json() catch — handles non-JSON 500 pages (e.g.
 *          Django debug error page) without an unhandled SyntaxError.
 */

// ── Utility: HTML-escape server-returned strings before innerHTML insertion ─────
function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── PDF.js loader: fetch source as text, import via correctly-typed Blob URL ───
// Dynamic import() enforces strict MIME checking. Nginx may serve .mjs files as
// application/octet-stream on servers whose mime.types lacks an .mjs entry.
// By creating the Blob ourselves we set type:'text/javascript', so the browser
// checks the Blob MIME type rather than the server Content-Type header.
function importPdfjsViaBlob(url) {
  return fetch(url)
    .then(function (r) {
      if (!r.ok) throw new Error('PDF.js load failed: HTTP ' + r.status);
      return r.text();
    })
    .then(function (src) {
      var blob    = new Blob([src], {type: 'text/javascript'});
      var blobUrl = URL.createObjectURL(blob);
      return import(blobUrl).then(function (mod) {
        URL.revokeObjectURL(blobUrl);
        return mod;
      });
    });
}

// ── Topbar logic ──────────────────────────────────────────────────────────────
function toggleDutyOther() {
  var sel = document.getElementById('tb_purpose');
  var other = document.getElementById('tb_purpose_other');
  if (other) other.style.display = sel && sel.value === 'Others' ? '' : 'none';
}

function toggleTrPreview() {
  var isSel = document.getElementById('tb_issuance_type');
  var btn = document.getElementById('btn-tr-preview');
  var parDocSection = document.getElementById('par-doc-section');
  if (!isSel) return;
  var isReturn = document.getElementById('tb_transaction_type').value === 'Return';
  if (btn) btn.style.display = (!isReturn && isSel.value === 'TR (Temporary Receipt)') ? '' : 'none';
  if (parDocSection) parDocSection.style.display = (!isReturn && isSel.value === 'PAR (Property Acknowledgement Receipt)') ? '' : 'none';
}

function toggleReturnMode() {
  var isReturn = document.getElementById('tb_transaction_type').value === 'Return';
  var issuanceWrapper = document.getElementById('issuance-wrapper');
  var purposeWrapper = document.getElementById('purpose-wrapper');
  if (issuanceWrapper) issuanceWrapper.style.display = isReturn ? 'none' : 'flex';
  if (purposeWrapper) purposeWrapper.style.display = isReturn ? 'none' : 'flex';
  toggleTrPreview();
  // When switching away from Return mode, clear any auto-filled consumable values
  // so they don't bleed into a Withdrawal form submission.
  if (!isReturn) {
    // Clear hidden FK fields
    var pmHid = document.getElementById('id_pistol_magazine') || document.querySelector('[name="pistol_magazine"]');
    if (pmHid) pmHid.value = '';
    var paHid = document.getElementById('id_pistol_ammunition') || document.querySelector('[name="pistol_ammunition"]');
    if (paHid) paHid.value = '';
    var raHid = document.getElementById('id_rifle_ammunition') || document.querySelector('[name="rifle_ammunition"]');
    if (raHid) raHid.value = '';
    var pmq = document.querySelector('[name="pistol_magazine_quantity"]');
    if (pmq) pmq.value = '';
    var paq = document.querySelector('[name="pistol_ammunition_quantity"]');
    if (paq) paq.value = '';
    var rmq = document.querySelector('[name="rifle_magazine_quantity"]');
    if (rmq) rmq.value = '';
    var raq = document.querySelector('[name="rifle_ammunition_quantity"]');
    if (raq) raq.value = '';
    var h = document.querySelector('[name="include_pistol_holster"]');
    if (h) h.checked = false;
    var mp = document.querySelector('[name="include_magazine_pouch"]');
    if (mp) mp.checked = false;
    var rs = document.querySelector('[name="include_rifle_sling"]');
    if (rs) rs.checked = false;
    var bd = document.querySelector('[name="include_bandoleer"]');
    if (bd) bd.checked = false;
  }
}

// ── PDF.js render helper (shared by openTrPreview) ────────────────────────────────────
// Renders every page of a PDF.js document into targetEl as sequential <canvas> nodes.
function renderAllPages(pdf, targetEl, scale) {
  var pageNums = [];
  for (var i = 1; i <= pdf.numPages; i++) pageNums.push(i);
  return pageNums.reduce(function (chain, num) {
    return chain.then(function () {
      return pdf.getPage(num).then(function (page) {
        var vp     = page.getViewport({scale: scale});
        var canvas = document.createElement('canvas');
        canvas.width  = vp.width;
        canvas.height = vp.height;
        canvas.style.cssText = 'display:block;width:100%;margin-bottom:4px;border-radius:.2rem;';
        targetEl.appendChild(canvas);
        return page.render({canvasContext: canvas.getContext('2d'), viewport: vp}).promise;
      });
    });
  }, Promise.resolve());
}

// ── TR Preview ──────────────────────────────────────────────────────────────────
function openTrPreview() {
  var form = document.getElementById('txn-form');
  if (!form) return;
  var TR_PREVIEW_URL = form.dataset.trPreviewUrl;
  var pdfjsUrl  = form.dataset.pdfjsUrl;
  var workerUrl = form.dataset.pdfjsWorker;
  var data = new FormData(form);
  ['transaction_type', 'issuance_type', 'purpose', 'purpose_other'].forEach(function (name) {
    var id = name === 'purpose_other' ? 'tb_purpose_other' : 'tb_' + name;
    var el = document.getElementById(id);
    if (el) data.set(name, el.value);
  });
  var btn = document.getElementById('btn-tr-preview');
  var origHTML = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Loading\u2026';
  // F8 FIX: credentials:'same-origin' ensures session cookies are sent.
  fetch(TR_PREVIEW_URL, {
    method: 'POST',
    credentials: 'same-origin',
    body: data,
  })
  .then(function (resp) {
    if (!resp.ok) {
      // F9 FIX: catch non-JSON 500 pages so we never throw an unhandled SyntaxError.
      return resp.json()
        .catch(function () {
          throw { fieldErrors: {}, messages: ['Server error (' + resp.status + '). Please retry.'] };
        })
        .then(function (j) {
          var fieldErrs = j.field_errors || {};
          var nonFieldErrs = j.non_field_errors || (j.errors ? j.errors : ['Preview failed (' + resp.status + ')']);
          throw { fieldErrors: fieldErrs, messages: nonFieldErrs };
        });
    }
    return resp.arrayBuffer();
  })
  .then(function (buffer) {
    clearTrPreviewErrors();
    var previewContainer = document.getElementById('tr-preview-container');
    previewContainer.innerHTML = '';
    document.getElementById('tr-preview-modal').style.display = 'flex';
    document.body.style.overflow = 'hidden';
    // Render with PDF.js onto <canvas> elements.
    // No <embed>, no <iframe> — zero frame-src / object-src CSP involvement.
    // import() enforces strict MIME checking; bypass by fetching as text and
    // creating a correctly-typed Blob URL (browser checks Blob MIME, not server header).
    return importPdfjsViaBlob(pdfjsUrl).then(function (pdfjsLib) {
      pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;
      return pdfjsLib.getDocument({data: buffer}).promise;
    }).then(function (pdf) {
      return renderAllPages(pdf, previewContainer, 1.5);
    });
  })
  .catch(function (err) {
    clearTrPreviewErrors();
    if (err.fieldErrors) showTrPreviewFieldErrors(err.fieldErrors);
    var msgs = err.messages || [err.message || 'Unknown error'];
    showTrToast(msgs, 'error');
  })
  .finally(function () {
    btn.disabled = false;
    btn.innerHTML = origHTML;
  });
}

// ── TR Preview Modal ───────────────────────────────────────────────────────────
function closeTrPreview() {
  var modal = document.getElementById('tr-preview-modal');
  if (!modal) return; // safety: element may not exist after PJAX navigation
  modal.style.display = 'none';
  document.body.style.overflow = '';
  // Clear the PDF.js canvas nodes.
  var previewContainer = document.getElementById('tr-preview-container');
  if (previewContainer) previewContainer.innerHTML = '';
}

// ── Error display helpers ──────────────────────────────────────────────────────
function clearTrPreviewErrors() {
  document.querySelectorAll('[data-tr-error]').forEach(function (el) { el.remove(); });
  document.querySelectorAll('[data-tr-invalid]').forEach(function (el) {
    el.style.borderColor = '';
    el.removeAttribute('data-tr-invalid');
  });
}

function showTrPreviewFieldErrors(fieldErrors) {
  Object.keys(fieldErrors).forEach(function (name) {
    var msgs = fieldErrors[name];
    if (!msgs || !msgs.length) return;
    var el = document.querySelector('[name="' + name + '"]');
    if (!el) return;
    el.style.borderColor = '#ef4444';
    el.setAttribute('data-tr-invalid', '1');
    el.addEventListener('change', function onchg() {
      el.style.borderColor = '';
      el.removeAttribute('data-tr-invalid');
      var errDiv = el.parentElement && el.parentElement.querySelector('[data-tr-error]');
      if (errDiv) errDiv.remove();
      el.removeEventListener('change', onchg);
    }, { once: true });
    if (el.closest('.form-group')) {
      var errDiv = document.createElement('div');
      errDiv.className = 'form-error';
      errDiv.setAttribute('data-tr-error', '1');
      errDiv.textContent = msgs.join(', ');
      el.parentNode.insertBefore(errDiv, el.nextSibling);
    }
  });
}

function showTrToast(msgs, type) {
  var toast = document.getElementById('tr-toast');
  var icon = document.getElementById('tr-toast-icon');
  var span = document.getElementById('tr-toast-msg');
  if (!toast) return;
  if (!Array.isArray(msgs)) msgs = [msgs];
  // F2 FIX: Server error strings are HTML-escaped before innerHTML insertion.
  if (msgs.length === 1) {
    span.innerHTML = escHtml(msgs[0]);
  } else {
    span.innerHTML = '<ul style="margin:.25rem 0 0 0;padding-left:1.1rem;line-height:1.7;">' +
      msgs.map(function (m) { return '<li>' + escHtml(m) + '</li>'; }).join('') + '</ul>';
  }
  if (type === 'error') {
    toast.style.background = '#1e293b';
    toast.style.border = '1.5px solid #ef4444';
    icon.className = 'fa-solid fa-circle-exclamation';
    icon.style.color = '#ef4444';
    span.style.color = '#fca5a5';
  } else {
    toast.style.background = '#1e293b';
    toast.style.border = '1.5px solid #22c55e';
    icon.className = 'fa-solid fa-circle-check';
    icon.style.color = '#22c55e';
    span.style.color = '#bbf7d0';
  }
  toast.style.pointerEvents = 'auto';
  toast.style.opacity = '1';
  toast.style.transform = 'translateY(0)';
  clearTimeout(toast._timer);
  toast._timer = setTimeout(function () {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(-120%)';
    setTimeout(function () { toast.style.pointerEvents = 'none'; }, 300);
  }, 5000);
}

// ── Banner helper ──────────────────────────────────────────────────────────────
function setBanner(id, type, html) {
  var el = document.getElementById(id);
  if (!el) return;
  if (!html) { el.style.display = 'none'; el.innerHTML = ''; return; }
  var colors = {
    ok:   { bg: 'rgba(34,197,94,.10)',  border: '#22c55e', text: '#86efac', icon: 'fa-circle-check' },
    warn: { bg: 'rgba(251,191,36,.10)', border: '#f59e0b', text: '#fcd34d', icon: 'fa-triangle-exclamation' },
    err:  { bg: 'rgba(239,68,68,.10)',  border: '#ef4444', text: '#fca5a5', icon: 'fa-circle-exclamation' },
    info: { bg: 'rgba(56,189,248,.10)', border: '#38bdf8', text: '#7dd3fc', icon: 'fa-circle-info' },
  };
  var c = colors[type] || colors.info;
  el.style.display = '';
  // html parameter contains pre-escaped or trusted status tag strings built from escHtml() output.
  el.innerHTML =
    '<div style="display:flex;align-items:flex-start;gap:.5rem;padding:.45rem .65rem;border-radius:.4rem;' +
    'background:' + c.bg + ';border:1px solid ' + c.border + ';font-size:.75rem;color:' + c.text + ';line-height:1.5;">' +
    '<i class="fa-solid ' + c.icon + '" style="flex-shrink:0;margin-top:.15rem;"></i>' +
    '<span>' + html + '</span></div>';
}

// ── Auto-fill Return form consumables from personnel_status data ──────────────
// Called when Return mode is active and a personnel is selected.
// Pre-populates magazine qty, ammo qty, accessory checkboxes, and weapon selects
// so the operator doesn't have to enter them manually. The backend binding rule
// requires all issued consumables to be present; this makes compliance easy.
function autoFillReturnConsumables(d) {
  // Pistol magazine hidden FK (id_pistol_magazine) + quantity
  if (d.open_pistol_mag_id) {
    var pmHid = document.getElementById('id_pistol_magazine') || document.querySelector('[name="pistol_magazine"]');
    if (pmHid) pmHid.value = String(d.open_pistol_mag_id);
  }
  var pmq = document.querySelector('[name="pistol_magazine_quantity"]');
  if (pmq && d.pistol_mag_qty) pmq.value = d.pistol_mag_qty;

  // Pistol ammo hidden FK (id_pistol_ammunition) + quantity
  if (d.open_pistol_ammo_id) {
    var paHid = document.getElementById('id_pistol_ammunition') || document.querySelector('[name="pistol_ammunition"]');
    if (paHid) paHid.value = String(d.open_pistol_ammo_id);
  }
  var paq = document.querySelector('[name="pistol_ammunition_quantity"]');
  if (paq && d.pistol_ammo_qty) paq.value = d.pistol_ammo_qty;

  // Rifle magazine: set dropdown by PK from open log, then set quantity
  if (d.open_rifle_mag_id) {
    var rmSel = document.getElementById('id_rifle_magazine') || document.querySelector('[name="rifle_magazine"]');
    if (rmSel) {
      rmSel.value = String(d.open_rifle_mag_id);
      // Trigger change so any dependent logic fires
      rmSel.dispatchEvent(new Event('change'));
    }
  }
  var rmq = document.querySelector('[name="rifle_magazine_quantity"]');
  if (rmq && d.rifle_mag_qty) rmq.value = d.rifle_mag_qty;

  // Rifle ammo hidden FK (id_rifle_ammunition) + quantity
  if (d.open_rifle_ammo_id) {
    var raHid = document.getElementById('id_rifle_ammunition') || document.querySelector('[name="rifle_ammunition"]');
    if (raHid) raHid.value = String(d.open_rifle_ammo_id);
  }
  var raq = document.querySelector('[name="rifle_ammunition_quantity"]');
  if (raq && d.rifle_ammo_qty) raq.value = d.rifle_ammo_qty;

  // Accessories — check the boxes that have issued items
  var holster = document.querySelector('[name="include_pistol_holster"]');
  if (holster) holster.checked = !!d.holster_issued;

  var magPouch = document.querySelector('[name="include_magazine_pouch"]');
  if (magPouch) magPouch.checked = !!d.mag_pouch_issued;

  var rifleSling = document.querySelector('[name="include_rifle_sling"]');
  if (rifleSling) rifleSling.checked = !!d.rifle_sling_issued;

  var bandoleer = document.querySelector('[name="include_bandoleer"]');
  if (bandoleer) bandoleer.checked = !!d.bandoleer_issued;

  // Auto-select pistol and rifle in the dropdowns if issued to this personnel
  if (d.pistol_issued) {
    var pistolSel2 = document.getElementById('id_pistol') || document.querySelector('[name="pistol"]');
    if (pistolSel2 && !pistolSel2.value) {
      pistolSel2.value = String(d.pistol_issued);
      pistolSel2.dispatchEvent(new Event('change'));
    }
  }
  if (d.rifle_issued) {
    var rifleSel2 = document.getElementById('id_rifle') || document.querySelector('[name="rifle"]');
    if (rifleSel2 && !rifleSel2.value) {
      rifleSel2.value = String(d.rifle_issued);
      rifleSel2.dispatchEvent(new Event('change'));
    }
  }
}

// ── Real-time field checks ─────────────────────────────────────────────────────
// F7 FIX: 300ms debounce timers — prevent firing on every dropdown option scrolled.
var _personnelTimer, _pistolTimer, _rifleTimer;

function checkPersonnel(val) {
  var form = document.getElementById('txn-form');
  var PERSONNEL_URL = form ? form.dataset.personnelUrl : '';
  if (!val) { setBanner('personnel-status-banner', null, ''); return; }
  // F8 FIX: credentials:'same-origin' on all fetch calls.
  fetch(PERSONNEL_URL + '?personnel_id=' + encodeURIComponent(val), {
    credentials: 'same-origin',
  })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (d.error) { setBanner('personnel-status-banner', 'err', escHtml(d.error)); return; }
      var txnType = document.getElementById('tb_transaction_type');
      var type = txnType ? txnType.value : 'Withdrawal';
      var lines = [];
      if (type === 'Withdrawal') {
        // F2 FIX: d.pistol_issued / d.rifle_issued are escaped before concatenation.
        if (d.pistol_issued)  lines.push('<b style="color:#ef4444">Pistol already issued:</b> ' + escHtml(d.pistol_issued) + ' \u2014 cannot withdraw another');
        else                  lines.push('<b style="color:#22c55e">No pistol currently issued</b> \u2014 allowed to withdraw');
        if (d.rifle_issued)   lines.push('<b style="color:#ef4444">Rifle already issued:</b> ' + escHtml(d.rifle_issued) + ' \u2014 cannot withdraw another');
        else                  lines.push('<b style="color:#22c55e">No rifle currently issued</b> \u2014 allowed to withdraw');
        if (d.pistol_mag_issued)  lines.push('Pistol magazine issued: ' + escHtml(String(d.pistol_mag_issued)) + ' \u00d7' + escHtml(String(d.pistol_mag_qty)));
        if (d.rifle_mag_issued)   lines.push('Rifle magazine issued: '  + escHtml(String(d.rifle_mag_issued))  + ' \u00d7' + escHtml(String(d.rifle_mag_qty)));
        if (d.pistol_ammo_issued) lines.push('Pistol ammo issued: ' + escHtml(String(d.pistol_ammo_qty)) + ' rounds');
        if (d.rifle_ammo_issued)  lines.push('Rifle ammo issued: '  + escHtml(String(d.rifle_ammo_qty))  + ' rounds');
        if (d.holster_issued)     lines.push('Holster issued: 1 per pistol');
        if (d.mag_pouch_issued)   lines.push('Magazine pouch issued: ' + escHtml(String(d.mag_pouch_qty)) + ' unit' + (d.mag_pouch_qty == 1 ? '' : 's'));
        if (d.rifle_sling_issued) lines.push('Rifle sling issued: '   + escHtml(String(d.rifle_sling_qty)) + ' unit' + (d.rifle_sling_qty == 1 ? '' : 's'));
        if (d.bandoleer_issued)   lines.push('Bandoleer issued: '     + escHtml(String(d.bandoleer_qty))   + ' unit' + (d.bandoleer_qty == 1 ? '' : 's'));
        var btype = (d.pistol_issued || d.rifle_issued) ? 'warn' : 'ok';
        setBanner('personnel-status-banner', btype, lines.join('<br>'));
      } else {
        var hasItems = d.pistol_issued || d.rifle_issued || d.pistol_mag_issued || d.rifle_mag_issued
          || d.pistol_ammo_issued || d.rifle_ammo_issued || d.holster_issued
          || d.mag_pouch_issued || d.rifle_sling_issued || d.bandoleer_issued;
        if (!hasItems) { setBanner('personnel-status-banner', 'warn', 'No items currently issued to this personnel.'); return; }
        if (d.pistol_issued)      lines.push('<b>Pistol:</b> '           + escHtml(d.pistol_issued));
        if (d.rifle_issued)       lines.push('<b>Rifle:</b> '            + escHtml(d.rifle_issued));
        if (d.pistol_mag_issued)  lines.push('Pistol magazine: \u00d7'   + escHtml(String(d.pistol_mag_qty)));
        if (d.rifle_mag_issued)   lines.push('Rifle magazine: \u00d7'    + escHtml(String(d.rifle_mag_qty)));
        if (d.pistol_ammo_issued) lines.push('Pistol ammo: '             + escHtml(String(d.pistol_ammo_qty)) + ' rounds');
        if (d.rifle_ammo_issued)  lines.push('Rifle ammo: '              + escHtml(String(d.rifle_ammo_qty))  + ' rounds');
        if (d.holster_issued)     lines.push('Holster: 1 per pistol');
        if (d.mag_pouch_issued)   lines.push('Magazine pouch: '          + escHtml(String(d.mag_pouch_qty))   + ' unit' + (d.mag_pouch_qty == 1 ? '' : 's'));
        if (d.rifle_sling_issued) lines.push('Rifle sling: '             + escHtml(String(d.rifle_sling_qty)) + ' unit' + (d.rifle_sling_qty == 1 ? '' : 's'));
        if (d.bandoleer_issued)   lines.push('Bandoleer: '               + escHtml(String(d.bandoleer_qty))   + ' unit' + (d.bandoleer_qty == 1 ? '' : 's'));
        setBanner('personnel-status-banner', 'info', '<b>Currently issued:</b><br>' + lines.join('<br>'));

        // AUTO-FILL Return form: populate all issued consumable fields so the
        // operator doesn't have to enter them manually (binding rule enforces completeness).
        autoFillReturnConsumables(d);
      }
    })
    .catch(function () { setBanner('personnel-status-banner', 'err', 'Could not fetch personnel status.'); });
}

function checkItem(selectId, bannerId, itemType) {
  var form = document.getElementById('txn-form');
  var ITEM_URL = form ? form.dataset.itemUrl : '';
  var sel = document.getElementById(selectId);
  var val = sel ? sel.value : '';
  if (!val) { setBanner(bannerId, null, ''); return; }
  var txnType = document.getElementById('tb_transaction_type');
  var isReturn = txnType && txnType.value === 'Return';
  // F8 FIX: credentials:'same-origin' on all fetch calls.
  fetch(ITEM_URL + '?type=' + itemType + '&item_id=' + encodeURIComponent(val), {
    credentials: 'same-origin',
  })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (d.error) { setBanner(bannerId, 'err', escHtml(d.error)); return; }
      // F2 FIX: d.model / d.serial_number / d.issued_to / d.reason escaped via escHtml().
      var modelSn = escHtml(d.model) + ' (S/N: ' + escHtml(d.serial_number) + ')';
      if (isReturn) {
        if (!d.available && d.item_status === 'Issued') {
          var personnelSel = document.querySelector('[name="personnel"]');
          var selectedPersonnel = personnelSel ? personnelSel.value : '';
          if (selectedPersonnel && d.issued_to && String(d.issued_to) === String(selectedPersonnel)) {
            setBanner(bannerId, 'ok', '<b>Issued to this personnel</b> \u2014 ' + modelSn + ' \u2014 ready to return');
          } else if (d.issued_to) {
            setBanner(bannerId, 'warn', '<b>' + escHtml(d.model) + '</b> (S/N: ' + escHtml(d.serial_number) + ') is issued to a <b>different personnel</b> \u2014 cannot return here');
          } else {
            setBanner(bannerId, 'ok', '<b>Issued</b> \u2014 ' + modelSn);
          }
        } else {
          setBanner(bannerId, 'err', '<b>Not currently issued</b> \u2014 ' + modelSn + ' cannot be returned');
        }
      } else {
        if (d.available) {
          setBanner(bannerId, 'ok', '<b>Available</b> \u2014 ' + modelSn);
        } else {
          var msg = escHtml(d.reason || ('Status: ' + d.item_status));
          if (d.issued_to) msg += ' \u2014 issued to: ' + escHtml(String(d.issued_to));
          setBanner(bannerId, 'err', msg);
        }
      }
    })
    .catch(function () { setBanner(bannerId, 'err', 'Could not fetch item status.'); });
}

// ── Topbar select focus/blur style handlers ────────────────────────────────────
function _attachSelectStyles(el) {
  if (!el) return;
  el.addEventListener('focus', function () { this.style.borderColor = 'var(--primary)'; });
  el.addEventListener('blur',  function () { this.style.borderColor = '#475569'; });
}

// ── DOMContentLoaded setup ────────────────────────────────────────────────────
(function () {
  var form = document.getElementById('txn-form');

  // Topbar selects — styles and change handlers (replaces inline onfocus/onblur/onchange)
  var tbType     = document.getElementById('tb_transaction_type');
  var tbIssuance = document.getElementById('tb_issuance_type');
  var tbPurpose  = document.getElementById('tb_purpose');
  _attachSelectStyles(tbType);
  _attachSelectStyles(tbIssuance);
  _attachSelectStyles(tbPurpose);

  if (tbType)     tbType.addEventListener('change',     toggleReturnMode);
  if (tbIssuance) tbIssuance.addEventListener('change', toggleTrPreview);
  if (tbPurpose)  tbPurpose.addEventListener('change',  toggleDutyOther);

  // Persist type selection across refresh / PJAX navigation
  if (tbType) tbType.addEventListener('change', function () {
    sessionStorage.setItem('txn_form_type', this.value);
  });

  // Buttons (replaces inline onclick=)
  var previewBtn = document.getElementById('btn-tr-preview');
  var submitBtn  = document.getElementById('btn-tr-submit');
  if (previewBtn) previewBtn.addEventListener('click', openTrPreview);
  if (submitBtn)  submitBtn.addEventListener('click', function () {
    if (form) form.requestSubmit();
  });

  // TR Preview Modal close handlers (replaces inline onclick/keydown)
  var modal = document.getElementById('tr-preview-modal');
  var closeBtn = document.getElementById('btn-tr-preview-close');
  if (closeBtn) closeBtn.addEventListener('click', closeTrPreview);
  if (modal)    modal.addEventListener('click', function (e) { if (e.target === this) closeTrPreview(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeTrPreview(); }, window.pjaxController ? { signal: window.pjaxController.signal } : undefined);

  // Enter (not inside a text field) → submit form
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' || e.altKey || e.ctrlKey || e.metaKey) return;
    var tag = (document.activeElement && document.activeElement.tagName) || '';
    if (/^(INPUT|TEXTAREA|SELECT|BUTTON|A)$/.test(tag)) return;
    e.preventDefault();
    if (form) form.requestSubmit();
  }, window.pjaxController ? { signal: window.pjaxController.signal } : {});

  // Alt+W → Withdrawal  |  Alt+R → Return  |  Alt+T → TR  |  Alt+A → PAR  |  Alt+V → TR Preview
  // Alt+1…6 → Purpose (Duty Sentinel, Duty Vigil, Duty Security, Honor Guard, Others, OREX)
  document.addEventListener('keydown', function (e) {
    if (!e.altKey) return;
    var key = e.key.toLowerCase();
    if (key === 'w' || key === 'r') {
      e.preventDefault();
      var newType = key === 'w' ? 'Withdrawal' : 'Return';
      if (tbType && tbType.value !== newType) {
        tbType.value = newType;
        sessionStorage.setItem('txn_form_type', newType);
        tbType.dispatchEvent(new Event('change'));
      }
    } else if (key === 't' || key === 'a') {
      e.preventDefault();
      var newIssuance = key === 't'
        ? 'TR (Temporary Receipt)'
        : 'PAR (Property Acknowledgement Receipt)';
      if (tbIssuance && tbIssuance.value !== newIssuance) {
        tbIssuance.value = newIssuance;
        tbIssuance.dispatchEvent(new Event('change'));
      }
    } else if (key === 'v') {
      e.preventDefault();
      var btn = document.getElementById('btn-tr-preview');
      if (btn && btn.style.display !== 'none') openTrPreview();
    } else if (e.key >= '1' && e.key <= '6') {
      e.preventDefault();
      var purposes = ['Duty Sentinel', 'Duty Vigil', 'Duty Security', 'Honor Guard', 'Others', 'OREX'];
      var newPurpose = purposes[parseInt(e.key, 10) - 1];
      if (tbPurpose && tbPurpose.value !== newPurpose) {
        tbPurpose.value = newPurpose;
        tbPurpose.dispatchEvent(new Event('change'));
      }
    }
  }, window.pjaxController ? { signal: window.pjaxController.signal } : {});

  // Restore persisted type (survives page refresh and PJAX navigation)
  var _savedType = sessionStorage.getItem('txn_form_type');
  if (_savedType && tbType && (_savedType === 'Withdrawal' || _savedType === 'Return')) {
    tbType.value = _savedType;
  }

  // Initial state
  toggleReturnMode();
  toggleDutyOther();

  // Personnel select — with 300ms debounce (F7 FIX)
  var personnelSel = document.querySelector('[name="personnel"]');
  if (personnelSel) {
    personnelSel.addEventListener('change', function () {
      var val = this.value;
      clearTimeout(_personnelTimer);
      _personnelTimer = setTimeout(function () {
        checkPersonnel(val);
        if (pistolSel && pistolSel.value) checkItem('id_pistol', 'pistol-status-banner', 'pistol');
        if (rifleSel  && rifleSel.value)  checkItem('id_rifle',  'rifle-status-banner',  'rifle');
      }, 300);
    });
    if (personnelSel.value) checkPersonnel(personnelSel.value);
  }

  var pistolSel = document.getElementById('id_pistol') || document.querySelector('[name="pistol"]');
  if (pistolSel) {
    pistolSel.setAttribute('id', 'id_pistol');
    pistolSel.addEventListener('change', function () {
      clearTimeout(_pistolTimer);
      var id = this.id || '';
      _pistolTimer = setTimeout(function () { checkItem(id, 'pistol-status-banner', 'pistol'); }, 300);
    });
    if (pistolSel.value) checkItem('id_pistol', 'pistol-status-banner', 'pistol');
  }

  var rifleSel = document.getElementById('id_rifle') || document.querySelector('[name="rifle"]');
  if (rifleSel) {
    rifleSel.setAttribute('id', 'id_rifle');
    rifleSel.addEventListener('change', function () {
      clearTimeout(_rifleTimer);
      var id = this.id || '';
      _rifleTimer = setTimeout(function () { checkItem(id, 'rifle-status-banner', 'rifle'); }, 300);
    });
    if (rifleSel.value) checkItem('id_rifle', 'rifle-status-banner', 'rifle');
  }

  // Re-run all checks when transaction type changes
  if (tbType) {
    tbType.addEventListener('change', function () {
      var p = document.querySelector('[name="personnel"]');
      if (p && p.value) checkPersonnel(p.value);
      if (pistolSel && pistolSel.value) checkItem('id_pistol', 'pistol-status-banner', 'pistol');
      if (rifleSel  && rifleSel.value)  checkItem('id_rifle',  'rifle-status-banner',  'rifle');
    });
  }

  // Auto-check accessories for Duty Sentinel + Glock 17 9mm
  function autoCheckDutySentinelAccessories() {
    var purposeSel = document.getElementById('tb_purpose');
    var pistolText = pistolSel && pistolSel.options[pistolSel.selectedIndex]
      ? pistolSel.options[pistolSel.selectedIndex].text : '';
    var isGlock17       = pistolSel && pistolSel.value && pistolText.toLowerCase().indexOf('glock 17') !== -1;
    var isDutySentinel  = purposeSel && purposeSel.value === 'Duty Sentinel';
    var isWithdrawal    = tbType && tbType.value === 'Withdrawal';
    if (isGlock17 && isDutySentinel && isWithdrawal) {
      var holster  = document.querySelector('[name="include_pistol_holster"]');
      var magPouch = document.querySelector('[name="include_magazine_pouch"]');
      if (holster)  holster.checked  = true;
      if (magPouch) magPouch.checked = true;
    }
  }
  if (pistolSel) pistolSel.addEventListener('change', autoCheckDutySentinelAccessories);
  if (tbPurpose) tbPurpose.addEventListener('change', autoCheckDutySentinelAccessories);
  if (tbType)    tbType.addEventListener('change',    autoCheckDutySentinelAccessories);
  autoCheckDutySentinelAccessories();

  // Form submit — sync topbar selects into hidden inputs; clear persisted type
  if (form) {
    form.addEventListener('submit', function () {
      sessionStorage.removeItem('txn_form_type');
      var isReturn = tbType && tbType.value === 'Return';
      ['transaction_type', 'issuance_type', 'purpose', 'purpose_other'].forEach(function (name) {
        var sel = document.getElementById('tb_' + name);
        if (!sel) return;
        var inp = document.createElement('input');
        inp.type = 'hidden'; inp.name = name;
        if (isReturn && name === 'issuance_type') inp.value = '';
        else                                       inp.value = sel.value;
        form.appendChild(inp);
      });
    });
  }

  // Form error toast auto-dismiss (only present when Django renders form.non_field_errors)
  var errorToast = document.getElementById('form-error-toast');
  if (errorToast) {
    function dismissErrorToast() {
      errorToast.style.transition = 'opacity .4s';
      errorToast.style.opacity = '0';
      setTimeout(function () { errorToast.remove(); }, 400);
    }
    setTimeout(dismissErrorToast, 5000);
    ['personnel', 'pistol', 'rifle'].forEach(function (name) {
      var el = document.querySelector('[name="' + name + '"]');
      if (el) el.addEventListener('change', function () { if (this.value) dismissErrorToast(); });
    });
    // Dismiss button (replaces inline onclick=)
    var dismissBtn = errorToast.querySelector('[data-dismiss]');
    if (dismissBtn) dismissBtn.addEventListener('click', dismissErrorToast);
  }
})();

// ── Widget initialization ─────────────────────────────────────────────────────
// Runs after DOM is parsed (script has 'defer'). Adds form-control class to widgets.
document.querySelectorAll('#txn-form select, #txn-form input[type=number], #txn-form textarea').forEach(function(el) {
  el.classList.add('form-control');
});

// ── Notes "REMARKS" floating placeholder ─────────────────────────────────────
(function() {
  var ta = document.querySelector('[name="notes"]');
  var ph = document.getElementById('notes-placeholder');
  if (!ta || !ph) return;
  function sync() { ph.style.opacity = ta.value ? '0' : '1'; }
  ta.addEventListener('input', sync);
  ta.addEventListener('focus', function() { ph.style.opacity = '0'; });
  ta.addEventListener('blur', sync);
  sync();
})();

// ── Background barcode/QR scanner listener ────────────────────────────────────
// Keyboard-wedge scanners fire keystrokes very fast (< 50 ms apart) and
// finish with Enter. We intercept in the CAPTURE phase so events are caught
// even when focus is inside a select/input/textarea.
(function() {
  var buf = '';
  var lastKey = 0;
  var scanning = false;
  var SCANNER_SPEED = 50; // ms — gap threshold between scanner keystrokes
  var MIN_LEN = 3;

  function showQrToast(msg, ok) {
    var t = document.getElementById('qr-toast');
    if (!t) {
      t = document.createElement('div');
      t.id = 'qr-toast';
      t.style.cssText = 'position:fixed;bottom:1.5rem;right:1.5rem;padding:.6rem 1.1rem;border-radius:.5rem;font-size:.85rem;font-weight:600;z-index:9999;transition:opacity .4s;pointer-events:none';
      document.body.appendChild(t);
    }
    t.style.background = ok ? '#166534' : '#7f1d1d';
    t.style.color = '#fff';
    t.textContent = msg;
    t.style.opacity = '1';
    clearTimeout(t._hide);
    t._hide = setTimeout(function() { t.style.opacity = '0'; }, 2500);
  }

  function tryAutofill(val) {
    var personnelSel = document.querySelector('[name="personnel"]');
    var pistolSel    = document.querySelector('[name="pistol"]');
    var rifleSel     = document.querySelector('[name="rifle"]');
    var matched = false;

    if (personnelSel) {
      var pOpt = Array.from(personnelSel.options).find(function(o) {
        return o.value && (o.value === val || o.text.indexOf(val) !== -1);
      });
      if (pOpt) {
        personnelSel.value = pOpt.value;
        personnelSel.dispatchEvent(new Event('change'));
        var qrPEl = document.getElementById('fe_qr_personnel_id');
        if (qrPEl) qrPEl.value = val;
        showQrToast('\u2713 Personnel: ' + pOpt.text.trim(), true);
        matched = true;
      }
    }

    if (!matched && pistolSel) {
      var piOpt = Array.from(pistolSel.options).find(function(o) {
        return o.value && (o.text.indexOf(val) !== -1 || o.value === val);
      });
      if (piOpt) {
        pistolSel.value = piOpt.value;
        if (rifleSel) { rifleSel.value = ''; rifleSel.dispatchEvent(new Event('change')); }
        pistolSel.dispatchEvent(new Event('change'));
        var qrIEl = document.getElementById('fe_qr_item_id');
        if (qrIEl) qrIEl.value = val;
        showQrToast('\u2713 Pistol: ' + piOpt.text.trim(), true);
        matched = true;
      }
    }

    if (!matched && rifleSel) {
      var riOpt = Array.from(rifleSel.options).find(function(o) {
        return o.value && (o.text.indexOf(val) !== -1 || o.value === val);
      });
      if (riOpt) {
        rifleSel.value = riOpt.value;
        if (pistolSel) { pistolSel.value = ''; pistolSel.dispatchEvent(new Event('change')); }
        rifleSel.dispatchEvent(new Event('change'));
        var qrIEl2 = document.getElementById('fe_qr_item_id');
        if (qrIEl2) qrIEl2.value = val;
        showQrToast('\u2713 Rifle: ' + riOpt.text.trim(), true);
        matched = true;
      }
    }

    if (!matched) {
      showQrToast('\u2717 No match found: ' + val, false);
      return;
    }

    var focused = document.activeElement;
    if (focused && (focused.tagName === 'INPUT' || focused.tagName === 'TEXTAREA')) {
      var fv = focused.value || '';
      var idx = fv.lastIndexOf(val);
      if (idx !== -1) focused.value = fv.slice(0, idx) + fv.slice(idx + val.length);
    }
  }

  document.addEventListener('keydown', function(e) {
    var now = Date.now();
    var gap = now - lastKey;

    if (e.key === 'Enter') {
      if (scanning && buf.length >= MIN_LEN) {
        e.preventDefault();
        e.stopPropagation();
        tryAutofill(buf);
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
  }, window.pjaxController ? { capture: true, signal: window.pjaxController.signal } : true); // capture phase
})();

// ── Duty Sentinel + weapon -> auto-fill ammo quantities ───────────────────────
(function() {
  var dutyEl    = document.getElementById('tb_purpose');
  var pistolEl  = document.querySelector('[name="pistol"]');
  var rifleEl   = document.querySelector('[name="rifle"]');
  var magQtyEl  = document.querySelector('[name="pistol_magazine_quantity"]');
  var ammoQtyEl = document.querySelector('[name="pistol_ammunition_quantity"]');
  var pistolLabel = document.getElementById('pistol-ammo-type-label');
  var rifleLabel  = document.getElementById('rifle-ammo-type-label');

  var PISTOL_AMMO = {
    'Glock 17 9mm':            'M882 9x19mm Ball 435 Ctg',
    'M1911 Cal.45':            'Cal.45 Ball 433 Ctg',
    'Armscor Hi Cap Cal.45':   'Cal.45 Ball 433 Ctg',
    'RIA Hi Cap Cal.45':       'Cal.45 Ball 433 Ctg',
    'M1911 Customized Cal.45': 'Cal.45 Ball 433 Ctg',
  };
  var RIFLE_AMMO = {
    'M4 Carbine DSAR-15 5.56mm':  'M193 5.56mm Ball 428 Ctg',
    'M4 14.5" DGIS EMTAN 5.56mm': 'M193 5.56mm Ball 428 Ctg',
    'M16A1 Rifle 5.56mm':         'M193 5.56mm Ball 428 Ctg',
    'M653 Carbine 5.56mm':        'M193 5.56mm Ball 428 Ctg',
    'M14 Rifle 7.62mm':           'M80 7.62x51mm Ball 431 Ctg',
  };

  function getSelectedText(sel) {
    if (!sel || !sel.value) return '';
    var opt = sel.options[sel.selectedIndex];
    return opt ? opt.text.trim() : '';
  }

  function updateAmmoLabels() {
    var pistolText = getSelectedText(pistolEl);
    var pistolAmmo = '';
    for (var model in PISTOL_AMMO) {
      if (pistolText.indexOf(model) !== -1) { pistolAmmo = PISTOL_AMMO[model]; break; }
    }
    if (pistolLabel) pistolLabel.textContent = pistolAmmo ? '\u2192 ' + pistolAmmo : '';

    var rifleText = getSelectedText(rifleEl);
    var rifleAmmo = '';
    for (var rmodel in RIFLE_AMMO) {
      if (rifleText.indexOf(rmodel) !== -1) { rifleAmmo = RIFLE_AMMO[rmodel]; break; }
    }
    if (rifleLabel) rifleLabel.textContent = rifleAmmo ? '\u2192 ' + rifleAmmo : '';
  }

  function applySentinelDefaults() {
    var isSentinel = dutyEl && dutyEl.value === 'Duty Sentinel';
    var hasPistol  = pistolEl && pistolEl.value;
    if (isSentinel && hasPistol) {
      if (magQtyEl  && !magQtyEl.value)  magQtyEl.value  = 4;
      if (ammoQtyEl && !ammoQtyEl.value) ammoQtyEl.value = 42;
    }
    updateAmmoLabels();
  }

  if (dutyEl)   dutyEl.addEventListener('change', applySentinelDefaults);
  if (pistolEl) pistolEl.addEventListener('change', applySentinelDefaults);
  if (rifleEl)  rifleEl.addEventListener('change', updateAmmoLabels);
  applySentinelDefaults();
})();

// ── PAR issuance section toggle ───────────────────────────────────────────────
(function() {
  var issuanceField = document.querySelector('[name="issuance_type"]');
  var parSection    = document.getElementById('par-doc-section');
  function togglePar() {
    if (issuanceField && parSection) {
      parSection.style.display = (issuanceField.value || '').toUpperCase().startsWith('PAR') ? '' : 'none';
    }
  }
  if (issuanceField) {
    issuanceField.addEventListener('change', togglePar);
    togglePar();
  }
})();

// ── Return-By deadline section toggle (TR Withdrawal only) ───────────────────
(function() {
  var tbType      = document.getElementById('tb_transaction_type');
  var tbIssuance  = document.getElementById('tb_issuance_type');
  var returnBySection = document.getElementById('return-by-section');
  function toggleReturnBy() {
    if (!returnBySection) return;
    var isWithdrawal = tbType && tbType.value === 'Withdrawal';
    var isTR = tbIssuance && (tbIssuance.value || '').toUpperCase().startsWith('TR');
    returnBySection.style.display = (isWithdrawal && isTR) ? '' : 'none';
    // Pre-fill with now+24h when TR is selected and field is still empty
    if (isWithdrawal && isTR) {
      var inp = document.getElementById('id_return_by');
      if (inp && !inp.value) {
        var d = new Date(Date.now() + 24 * 60 * 60 * 1000);
        var pad = function(n) { return String(n).padStart(2, '0'); };
        inp.value = d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
                    'T' + pad(d.getHours()) + ':' + pad(d.getMinutes());
      }
    }
  }
  if (tbType)     tbType.addEventListener('change', toggleReturnBy);
  if (tbIssuance) tbIssuance.addEventListener('change', toggleReturnBy);
  toggleReturnBy();
})();

// ── Sidebar: personnel ID card + item images ──────────────────────────────────
(function() {
  var _form = document.getElementById('txn-form');
  var PERSONNEL_URL = _form ? _form.dataset.personnelUrl : '';
  var ITEM_URL      = _form ? _form.dataset.itemUrl : '';

  function showEl(id, flexDir) {
    var el = document.getElementById(id);
    if (el) { el.style.display = flexDir || 'flex'; }
  }
  function hideEl(id) {
    var el = document.getElementById(id);
    if (el) { el.style.display = 'none'; }
  }
  function setImg(id, url) {
    var el = document.getElementById(id);
    if (!el) return;
    if (url) { el.src = url; el.style.display = 'block'; }
    else     { el.src = ''; el.style.display = 'none'; }
  }

  function updatePersonnelSidebar(val) {
    if (!val) { hideEl('sidebar-personnel'); return; }
    fetch(PERSONNEL_URL + '?personnel_id=' + encodeURIComponent(val), { credentials: 'same-origin' })
      .then(function(r) { return r.json(); })
      .then(function(d) {
        if (d.id_card_front_url) {
          setImg('sidebar-id-card-img', d.id_card_front_url);
          showEl('sidebar-personnel', 'flex');
        } else {
          hideEl('sidebar-personnel');
        }
      })
      .catch(function() { hideEl('sidebar-personnel'); });
  }

  function updateItemSidebar(type, val) {
    var blockId  = 'sidebar-' + type;
    var tagImgId = 'sidebar-' + type + '-tag-img';
    var serImgId = 'sidebar-' + type + '-serial-img';
    if (!val) { hideEl(blockId); return; }
    fetch(ITEM_URL + '?type=' + type + '&item_id=' + encodeURIComponent(val), { credentials: 'same-origin' })
      .then(function(r) { return r.json(); })
      .then(function(d) {
        if (d.item_tag_url || d.serial_image_url) {
          setImg(tagImgId, d.item_tag_url || null);
          setImg(serImgId, d.serial_image_url || null);
          showEl(blockId, 'flex');
        } else {
          hideEl(blockId);
        }
      })
      .catch(function() { hideEl(blockId); });
  }

  (function() {
    var personnelSel = document.querySelector('[name="personnel"]');
    var pistolSel    = document.getElementById('id_pistol') || document.querySelector('[name="pistol"]');
    var rifleSel     = document.getElementById('id_rifle')  || document.querySelector('[name="rifle"]');
    if (personnelSel) {
      personnelSel.addEventListener('change', function() { updatePersonnelSidebar(this.value); });
      if (personnelSel.value) updatePersonnelSidebar(personnelSel.value);
    }
    if (pistolSel) {
      pistolSel.addEventListener('change', function() { updateItemSidebar('pistol', this.value); });
      if (pistolSel.value) updateItemSidebar('pistol', pistolSel.value);
    }
    if (rifleSel) {
      rifleSel.addEventListener('change', function() { updateItemSidebar('rifle', this.value); });
      if (rifleSel.value) updateItemSidebar('rifle', rifleSel.value);
    }
  })();
})();
