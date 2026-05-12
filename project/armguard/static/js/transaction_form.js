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

// ── PDF.js loader ─────────────────────────────────────────────────────────────
// Load PDF.js as an ES module via direct import(). Nginx serves .mjs files as
// text/javascript (patched by update-server.sh), so no blob-URL workaround needed.
// The URL is same-origin, covered by CSP script-src 'self'.
function importPdfjsViaBlob(url) {
  return import(url);
}

// ── Topbar logic ──────────────────────────────────────────────────────────────
function toggleDutyOther() {
  var sel = document.getElementById('tb_purpose');
  var other = document.getElementById('tb_purpose_other');
  if (!sel || !other) return;
  // Check is_others_type from the purpose config (prefer live-fetched, fall back to inline)
  var pcfgAll = window._livePurposeConfig || {};
  if (!Object.keys(pcfgAll).length) {
    var formEl = document.getElementById('txn-form');
    if (formEl && formEl.dataset.purposeConfig) {
      try { pcfgAll = JSON.parse(formEl.dataset.purposeConfig); } catch (_) {}
    }
  }
  var cfg = pcfgAll[sel.value] || {};
  var isOthersType = cfg.is_others_type === true;
  other.style.display = isOthersType ? '' : 'none';
}

function updateRifleMagQtyHint(pcfg) {
  var hint = document.getElementById('rifle-mag-qty-hint');
  var shortQty = pcfg.rifle_short_mag_qty;
  var longQty  = pcfg.rifle_long_mag_qty;
  // Detect selected magazine type from the dropdown option text (contains '20-rounds', '30-rounds', or 'EMTAN').
  // Magazine.__str__ returns "<type> (<capacity>)" e.g. "Mag Assy, 5.56mm: 30 rds Cap Alloy (30-rounds)".
  // EMTAN magazines display as "Mag Assy, 5.56mm: EMTAN (EMTAN)" — treated as long (30-rnd equiv).
  var magSel = document.getElementById('id_rifle_magazine') || document.querySelector('[name="rifle_magazine"]');
  var selText = (magSel && magSel.options && magSel.selectedIndex >= 0)
    ? (magSel.options[magSel.selectedIndex].text || '') : '';
  var isLong  = /30-rounds|\(EMTAN\)/.test(selText);
  var isShort = /20-rounds/.test(selText);

  // Update hint label.
  if (hint) {
    if (shortQty === undefined && longQty === undefined) {
      hint.textContent = '';
    } else if (isLong && longQty !== undefined) {
      hint.textContent = '\u2014 default: ' + longQty + ' (Long)';
    } else if (isShort && shortQty !== undefined) {
      hint.textContent = '\u2014 default: ' + shortQty + ' (Short)';
    } else {
      var parts = [];
      if (shortQty !== undefined) parts.push('Short: ' + shortQty);
      if (longQty  !== undefined) parts.push('Long: ' + longQty);
      hint.textContent = parts.length ? '\u2014 default ' + parts.join(' / ') : '';
    }
  }

  // Auto-fill rifle magazine qty input based on selected type, or default to short qty.
  var rmq = document.querySelector('[name="rifle_magazine_quantity"]');
  if (rmq) {
    if (isLong && longQty !== undefined) {
      rmq.value = longQty;
    } else if (isShort && shortQty !== undefined) {
      rmq.value = shortQty;
    } else if (shortQty !== undefined) {
      // No magazine type selected yet — pre-fill with short qty as default.
      rmq.value = shortQty;
    } else if (longQty !== undefined) {
      rmq.value = longQty;
    }
  }
}

function toggleWeaponSections() {
  var form    = document.getElementById('txn-form');
  var purpose = document.getElementById('tb_purpose');
  var val     = purpose ? purpose.value : '';
  var isReturn = (document.getElementById('tb_transaction_type') || {}).value === 'Return';
  var cfg     = {};
  try { cfg = JSON.parse((form && form.dataset.purposeConfig) || '{}'); } catch (e) {}
  // Prefer live-fetched config (updated after purpose edits without reload)
  if (window._livePurposeConfig && Object.keys(window._livePurposeConfig).length) {
    cfg = window._livePurposeConfig;
  }
  // On Return, always show both pistol and rifle regardless of purpose config.
  var pcfg       = isReturn ? {pistol: true, rifle: true} : (cfg[val] || {pistol: true, rifle: true});
  var showPistol = pcfg.pistol !== false;
  var showRifle  = pcfg.rifle  !== false;

  // Update accessory quantity hint labels from per-purpose settings config.
  function _qtyText(n) {
    if (n === undefined || n === null) return '';
    return n === 1 ? ' \u2014 1 unit' : ' \u2014 ' + n + ' units';
  }
  var holsterQtyLabel    = document.getElementById('holster-qty-label');
  var magpouchQtyLabel   = document.getElementById('magpouch-qty-label');
  var rifleslingQtyLabel = document.getElementById('riflesling-qty-label');
  var bandoleerQtyLabel  = document.getElementById('bandoleer-qty-label');
  if (holsterQtyLabel    && pcfg.holster_qty     !== undefined) holsterQtyLabel.textContent    = _qtyText(pcfg.holster_qty);
  if (magpouchQtyLabel   && pcfg.mag_pouch_qty   !== undefined) magpouchQtyLabel.textContent   = _qtyText(pcfg.mag_pouch_qty);
  if (rifleslingQtyLabel && pcfg.rifle_sling_qty !== undefined) rifleslingQtyLabel.textContent = _qtyText(pcfg.rifle_sling_qty);
  if (bandoleerQtyLabel  && pcfg.bandoleer_qty   !== undefined) bandoleerQtyLabel.textContent  = _qtyText(pcfg.bandoleer_qty);

  // Rifle magazine qty hint: update based on selected magazine type (20-rounds/30-rounds).
  updateRifleMagQtyHint(pcfg);

  // Auto-check rifle sling and bandoleer based on purpose config qty.
  if (!isReturn) {
    var _rs = document.querySelector('[name="include_rifle_sling"]');
    var _bd = document.querySelector('[name="include_bandoleer"]');
    if (_rs && pcfg.rifle_sling_qty !== undefined) _rs.checked = pcfg.rifle_sling_qty > 0;
    if (_bd && pcfg.bandoleer_qty   !== undefined) _bd.checked = pcfg.bandoleer_qty   > 0;
  }

  // Pistol column + related accessories
  var pistolCol  = document.getElementById('pistol-col');
  var holsterRow = document.getElementById('pistol-holster-row');
  var pouchRow   = document.getElementById('magazine-pouch-row');
  if (pistolCol)  pistolCol.style.display  = showPistol ? '' : 'none';
  if (holsterRow) holsterRow.style.display = showPistol ? '' : 'none';
  if (pouchRow)   pouchRow.style.display   = showPistol ? '' : 'none';
  if (!showPistol) {
    var pistolSel = document.getElementById('id_pistol') || document.querySelector('[name="pistol"]');
    if (pistolSel && pistolSel.value) { pistolSel.value = ''; pistolSel.dispatchEvent(new Event('change')); }
    var pmq = document.querySelector('[name="pistol_magazine_quantity"]');
    if (pmq) pmq.value = '';
    var paq = document.querySelector('[name="pistol_ammunition_quantity"]');
    if (paq) paq.value = '';
    var h = document.querySelector('[name="include_pistol_holster"]');
    if (h) h.checked = false;
    var mp = document.querySelector('[name="include_magazine_pouch"]');
    if (mp) mp.checked = false;
  }

  // Rifle column + related accessories
  var rifleCol = document.getElementById('rifle-col');
  var slingRow = document.getElementById('rifle-sling-row');
  var bandRow  = document.getElementById('bandoleer-row');
  if (rifleCol)  rifleCol.style.display  = showRifle ? '' : 'none';
  if (slingRow)  slingRow.style.display  = showRifle ? '' : 'none';
  if (bandRow)   bandRow.style.display   = showRifle ? '' : 'none';
  if (!showRifle) {
    var rifleSel = document.getElementById('id_rifle') || document.querySelector('[name="rifle"]');
    if (rifleSel && rifleSel.value) { rifleSel.value = ''; rifleSel.dispatchEvent(new Event('change')); }
    var rmSel = document.getElementById('id_rifle_magazine') || document.querySelector('[name="rifle_magazine"]');
    if (rmSel) rmSel.value = '';
    var rmq = document.querySelector('[name="rifle_magazine_quantity"]');
    if (rmq) rmq.value = '';
    var raq = document.querySelector('[name="rifle_ammunition_quantity"]');
    if (raq) raq.value = '';
    var rs = document.querySelector('[name="include_rifle_sling"]');
    if (rs) rs.checked = false;
    var bd = document.querySelector('[name="include_bandoleer"]');
    if (bd) bd.checked = false;
  }
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

  // Discrepancy section — only relevant on Return
  var discSection = document.getElementById('discrepancy-section');
  if (discSection) discSection.style.display = isReturn ? '' : 'none';
  if (!isReturn && discSection) {
    var cb = document.getElementById('cb_report_discrepancy');
    if (cb) cb.checked = false;
    var discFields = document.getElementById('discrepancy-fields');
    if (discFields) discFields.style.display = 'none';
    var disType = document.getElementById('dis_type');
    var disDesc = document.getElementById('dis_desc');
    if (disType) { disType.required = false; disType.value = ''; disType.style.borderColor = ''; }
    if (disDesc) { disDesc.required = false; disDesc.value = ''; disDesc.style.borderColor = ''; }
  }
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
  // Re-evaluate weapon column visibility whenever the transaction type changes.
  // Without this, switching to Return after selecting a purpose that hides Rifle
  // leaves the rifle column hidden even though Returns always show both columns.
  toggleWeaponSections();
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
// AbortControllers for in-flight status fetches — cancelled when the selection
// changes so stale responses never overwrite current data.
var _personnelFetchController = null;
var _pistolFetchController    = null;
var _rifleFetchController     = null;

function checkPersonnel(val) {
  var form = document.getElementById('txn-form');
  var PERSONNEL_URL = form ? form.dataset.personnelUrl : '';
  if (!val) { setBanner('personnel-status-banner', null, ''); return; }
  // Cancel any previous in-flight request before starting a new one.
  if (_personnelFetchController) { _personnelFetchController.abort(); }
  _personnelFetchController = new AbortController();
  var _signal = _personnelFetchController.signal;
  // Auto-abort after 8 s so the banner never hangs indefinitely.
  var _personnelTimeout = setTimeout(function () { _personnelFetchController.abort(); }, 8000);
  // F8 FIX: credentials:'same-origin' on all fetch calls.
  fetch(PERSONNEL_URL + '?personnel_id=' + encodeURIComponent(val), {
    credentials: 'same-origin',
    signal: _signal,
  })
    .then(function (r) {
      clearTimeout(_personnelTimeout);
      // Handle non-2xx responses explicitly so r.json() never throws an
      // unexpected SyntaxError (e.g. an HTML error page would go to .catch()
      // and show the generic "Could not fetch" message instead of the real error).
      if (!r.ok) {
        return r.json().catch(function () { return {}; }).then(function (d) {
          setBanner('personnel-status-banner', 'err',
            escHtml((d && d.error) ? d.error : 'Could not fetch personnel status (HTTP ' + r.status + ').'));
          return null;
        });
      }
      return r.json();
    })
    .then(function (d) {
      if (!d) return; // handled above (non-OK response)
      if (d.error) { setBanner('personnel-status-banner', 'err', escHtml(d.error)); return; }
      var txnType = document.getElementById('tb_transaction_type');
      // Use the actual transaction type the operator selected — not a computed guess.
      // Previously the code derived type from hasIssuedItems, which caused the
      // Withdrawal-branch ("allowed to withdraw") to show on a Return form whenever
      // a personnel had no items issued.
      var isReturnMode = txnType && txnType.value === 'Return';
      var hasIssuedItems = !!(d.pistol_issued || d.rifle_issued || d.pistol_mag_issued
        || d.rifle_mag_issued || d.pistol_ammo_issued || d.rifle_ammo_issued
        || d.holster_issued || d.mag_pouch_issued || d.rifle_sling_issued || d.bandoleer_issued);
      var lines = [];
      if (!isReturnMode) {
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
      // Update the sidebar ID card using data already in hand — avoids a
      // second round-trip to the same personnel_status endpoint.
      if (typeof window._sidebarUpdatePersonnel === 'function') {
        window._sidebarUpdatePersonnel(d);
      }
    })
    .catch(function (err) {
      clearTimeout(_personnelTimeout);
      // Ignore AbortError — triggered intentionally when a newer selection supersedes this
      // request or when the 8-second timeout fires.
      if (err && err.name === 'AbortError') return;
      setBanner('personnel-status-banner', 'err', 'Could not fetch personnel status.');
    });
}

function checkItem(selectId, bannerId, itemType) {
  var form = document.getElementById('txn-form');
  var ITEM_URL = form ? form.dataset.itemUrl : '';
  var sel = document.getElementById(selectId);
  var val = sel ? sel.value : '';
  if (!val) { setBanner(bannerId, null, ''); return; }
  var txnType = document.getElementById('tb_transaction_type');
  var isReturn = txnType && txnType.value === 'Return';
  // Cancel any previous in-flight request for this item type before starting a new one.
  if (itemType === 'pistol') {
    if (_pistolFetchController) _pistolFetchController.abort();
    _pistolFetchController = new AbortController();
  } else {
    if (_rifleFetchController) _rifleFetchController.abort();
    _rifleFetchController = new AbortController();
  }
  var _itemCtl = itemType === 'pistol' ? _pistolFetchController : _rifleFetchController;
  // Auto-abort after 8 s so the banner never hangs indefinitely.
  var _itemTimeout = setTimeout(function () { _itemCtl.abort(); }, 8000);
  // F8 FIX: credentials:'same-origin' on all fetch calls.
  fetch(ITEM_URL + '?type=' + itemType + '&item_id=' + encodeURIComponent(val), {
    credentials: 'same-origin',
    signal: _itemCtl.signal,
  })
    .then(function (r) {
      clearTimeout(_itemTimeout);
      // 429 = rate-limited: show a soft warning but don't block the form.
      if (r.status === 429) {
        setBanner(bannerId, 'warn', 'Status check unavailable — too many requests. You can still submit.');
        return Promise.reject({ name: 'RateLimit' });
      }
      return r.json();
    })
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
        } else if (d.has_open_discrepancy) {
          setBanner(bannerId, 'err',
            '<i class="fa-solid fa-triangle-exclamation" style="margin-right:.3rem;"></i>' +
            '<b>Withdrawal blocked</b> \u2014 ' + modelSn +
            ' has an <b>open discrepancy</b>. Resolve it before withdrawing.');
        } else {
          var msg = escHtml(d.reason || ('Status: ' + d.item_status));
          setBanner(bannerId, 'err', msg);
        }
      }
    })
    .catch(function (err) {
      clearTimeout(_itemTimeout);
      // Ignore AbortError — triggered intentionally when a newer selection supersedes this
      // request or when the 8-second timeout fires.
      // Ignore RateLimit — already handled above with a soft warning banner.
      if (err && (err.name === 'AbortError' || err.name === 'RateLimit')) return;
      setBanner(bannerId, 'err', 'Could not fetch item status.');
    });
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

  // ── Navigation guard ──────────────────────────────────────────────────────
  // Warn before PJAX or full-page navigation if the form has been changed, so
  // the armorer does not silently lose a partially-filled transaction.
  // The guard is cleared on intentional form submit, and when PJAX replaces the
  // page (pjaxController aborts the signal for this page's script lifecycle).
  function _setDirtyGuard() {
    if (window._pjaxNavigationGuard) return; // already armed
    window._pjaxNavigationGuard = function () {
      return window.confirm(
        'You have unsaved changes.\nLeave this page and discard the transaction data?'
      );
    };
  }
  // Remove guard when PJAX navigates away from this page.
  if (window.pjaxController) {
    window.pjaxController.signal.addEventListener('abort', function () {
      window._pjaxNavigationGuard = null;
    });
  }
  // Guard against full-page unloads: address bar navigation, tab close, Ctrl+R.
  window.addEventListener(
    'beforeunload',
    function (e) {
      if (window._pjaxNavigationGuard) { e.preventDefault(); e.returnValue = ''; }
    },
    window.pjaxController ? { signal: window.pjaxController.signal } : {}
  );

  // Topbar selects — styles and change handlers (replaces inline onfocus/onblur/onchange)
  var tbType     = document.getElementById('tb_transaction_type');
  var tbIssuance = document.getElementById('tb_issuance_type');
  var tbPurpose  = document.getElementById('tb_purpose');
  _attachSelectStyles(tbType);
  _attachSelectStyles(tbIssuance);
  _attachSelectStyles(tbPurpose);

  // ── Persist last-selected Type / Issuance / Purpose across page refreshes ──
  // Only restore when the form has no server-side pre-fill (i.e. it's a fresh
  // blank form, not a re-display after a validation error that already has values).
  var _LS_TYPE     = 'armguard_txn_type';
  var _LS_ISSUANCE = 'armguard_txn_issuance';
  var _LS_PURPOSE  = 'armguard_txn_purpose';
  var _isNewForm   = !(form && form.dataset.hasErrors === 'true');
  try {
    if (_isNewForm) {
      var _savedType     = localStorage.getItem(_LS_TYPE);
      var _savedIssuance = localStorage.getItem(_LS_ISSUANCE);
      var _savedPurpose  = localStorage.getItem(_LS_PURPOSE);
      if (_savedType     && tbType     && tbType.querySelector('option[value="'     + _savedType     + '"]')) tbType.value     = _savedType;
      if (_savedIssuance && tbIssuance && tbIssuance.querySelector('option[value="' + _savedIssuance + '"]')) tbIssuance.value = _savedIssuance;
      if (_savedPurpose  && tbPurpose  && tbPurpose.querySelector('option[value="'  + _savedPurpose  + '"]')) tbPurpose.value  = _savedPurpose;
    }
  } catch (e) { /* localStorage unavailable — ignore */ }
  function _saveTopbarState() {
    try {
      if (tbType)     localStorage.setItem(_LS_TYPE,     tbType.value);
      if (tbIssuance) localStorage.setItem(_LS_ISSUANCE, tbIssuance.value);
      if (tbPurpose)  localStorage.setItem(_LS_PURPOSE,  tbPurpose.value);
    } catch (e) {}
  }

  if (tbType)     tbType.addEventListener('change',     toggleReturnMode);
  if (tbIssuance) tbIssuance.addEventListener('change', toggleTrPreview);
  if (tbPurpose) {
    tbPurpose.addEventListener('change', toggleDutyOther);
    tbPurpose.addEventListener('change', toggleWeaponSections);
  }
  // Save state whenever any topbar dropdown changes
  if (tbType)     tbType.addEventListener('change',     _saveTopbarState);
  if (tbIssuance) tbIssuance.addEventListener('change', _saveTopbarState);
  if (tbPurpose)  tbPurpose.addEventListener('change',  _saveTopbarState);

  // Rifle magazine selection → update the qty hint in real-time.
  var rifMagSel = document.getElementById('id_rifle_magazine') || document.querySelector('[name="rifle_magazine"]');
  if (rifMagSel) {
    rifMagSel.addEventListener('change', function () {
      var form2 = document.getElementById('txn-form');
      var purpose2 = document.getElementById('tb_purpose');
      var cfg2 = {};
      try { cfg2 = JSON.parse((form2 && form2.dataset.purposeConfig) || '{}'); } catch (e) {}
      var pcfg2 = cfg2[(purpose2 && purpose2.value) || ''] || {};
      updateRifleMagQtyHint(pcfg2);
    });
  }

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
  // Note: Alt+W / Alt+R only apply when NO personnel is selected. Once a personnel is chosen,
  // the transaction type is locked to their open withdrawal state (Return if they have issued
  // items, Withdrawal otherwise) and cannot be manually overridden via hotkey.
  // Alt+T / Alt+A / Alt+1–6 are no-ops in Return mode (issuance and purpose don't apply to returns).
  document.addEventListener('keydown', function (e) {
    if (!e.altKey) return;
    var key = e.key.toLowerCase();
    var _isReturn = tbType && tbType.value === 'Return';
    if (key === 'w' || key === 'r') {
      e.preventDefault();
      // Type is auto-determined when a personnel is selected — hotkey is a no-op in that case.
      var _pSel = document.querySelector('[name="personnel"]');
      if (_pSel && _pSel.value) return;
      var newType = key === 'w' ? 'Withdrawal' : 'Return';
      if (tbType && tbType.value !== newType) {
        tbType.value = newType;
        tbType.dispatchEvent(new Event('change'));
      }
    } else if (key === 't' || key === 'a') {
      e.preventDefault();
      if (_isReturn) return; // issuance type not applicable on returns
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
    } else if (e.altKey || (e.key >= '1' && e.key <= '9')) {
      // Purpose hotkeys: read from data-hotkey attributes on the <option> elements.
      // Each option may carry data-hotkey="1", "F2", "Alt+3" etc. set by TransactionPurpose.
      if (_isReturn) return; // purpose not applicable on returns
      var purposeSel2 = document.getElementById('tb_purpose');
      if (!purposeSel2) return;
      var pressedKey = e.altKey ? ('Alt+' + e.key) : e.key;
      var matched = null;
      purposeSel2.querySelectorAll('option').forEach(function (opt) {
        if (opt.dataset.hotkey === pressedKey) matched = opt.value;
      });
      if (matched === null && e.key >= '1' && e.key <= '9') {
        // Fallback: numeric key N selects the Nth option (1-based) for backward compat
        var idx = parseInt(e.key, 10) - 1;
        var opts = purposeSel2.querySelectorAll('option');
        if (idx >= 0 && idx < opts.length) matched = opts[idx].value;
      }
      if (matched !== null && purposeSel2.value !== matched) {
        e.preventDefault();
        purposeSel2.value = matched;
        purposeSel2.dispatchEvent(new Event('change'));
      }
    }
  }, window.pjaxController ? { signal: window.pjaxController.signal } : {});

  // Initial state
  toggleReturnMode();
  toggleDutyOther();
  toggleWeaponSections();

  // Personnel select — with 300ms debounce (F7 FIX)
  var personnelSel = document.querySelector('[name="personnel"]');
  if (personnelSel) {
    personnelSel.addEventListener('change', function () {
      var val = this.value;
      if (val) _setDirtyGuard(); // personnel selected — form is no longer blank
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
      if (this.value) _setDirtyGuard();
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
      if (this.value) _setDirtyGuard();
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

  // Auto-check accessories based on purpose's auto_accessories config flag
  function autoCheckPurposeAccessories() {
    var purposeSel = document.getElementById('tb_purpose');
    if (!purposeSel || !purposeSel.value) return;
    var formEl = document.getElementById('txn-form');
    var pcfgAll = {};
    if (formEl && formEl.dataset.purposeConfig) {
      try { pcfgAll = JSON.parse(formEl.dataset.purposeConfig); } catch (_) {}
    }
    var cfg = pcfgAll[purposeSel.value] || {};
    var isWithdrawal = tbType && tbType.value === 'Withdrawal';
    if (cfg.auto_accessories && isWithdrawal) {
      if (pistolSel && pistolSel.value) {
        var holster  = document.querySelector('[name="include_pistol_holster"]');
        var magPouch = document.querySelector('[name="include_magazine_pouch"]');
        if (holster)  holster.checked = true;
        if (magPouch) magPouch.checked = true;
      }
      if (rifleSel && rifleSel.value) {
        var rifleSling = document.querySelector('[name="include_rifle_sling"]');
        if (rifleSling) rifleSling.checked = true;
      }
    }
  }
  if (pistolSel) pistolSel.addEventListener('change', autoCheckPurposeAccessories);
  if (rifleSel)  rifleSel.addEventListener('change',  autoCheckPurposeAccessories);
  if (tbPurpose) tbPurpose.addEventListener('change', autoCheckPurposeAccessories);
  if (tbType)    tbType.addEventListener('change',    autoCheckPurposeAccessories);
  autoCheckPurposeAccessories();

  // Discrepancy checkbox — expand/collapse the type+description fields
  var discCb = document.getElementById('cb_report_discrepancy');
  if (discCb) {
    discCb.addEventListener('change', function () {
      var discFields = document.getElementById('discrepancy-fields');
      var disType    = document.getElementById('dis_type');
      var disDesc    = document.getElementById('dis_desc');
      if (discFields) discFields.style.display = this.checked ? 'flex' : 'none';
      if (disType)    disType.required = this.checked;
      if (disDesc)    disDesc.required = this.checked;
      if (!this.checked) {
        if (disType) { disType.value = ''; disType.style.borderColor = ''; }
        if (disDesc) { disDesc.value = ''; disDesc.style.borderColor = ''; }
      }
    });
  }

  // Form submit — sync topbar selects into hidden inputs; clear persisted type
  if (form) {
    // Double-submit guard: disable the submit button and set a flag the moment
    // the form fires so that rapid Enter presses or accidental double-clicks
    // cannot send multiple POSTs and burn rate-limit quota.  The guard is
    // automatically cleared if the browser navigates back (e.g. validation errors
    // re-render the page, which runs this script fresh with _submitting = false).
    var _submitting = false;
    form.addEventListener('submit', function (e) {
      if (_submitting) { e.preventDefault(); return; }
      _submitting = true;
      // Intentional submit — clear the navigation guard so the success redirect
      // does not trigger a "You have unsaved changes" confirmation dialog.
      window._pjaxNavigationGuard = null;
      var btn = document.getElementById('btn-tr-submit');
      if (btn) { btn.disabled = true; btn.textContent = 'Submitting\u2026'; }

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
        var pistolCol = document.getElementById('pistol-col');
        if (pistolCol && pistolCol.style.display === 'none') {
          showQrToast('\u26A0 Pistol is not used for this purpose', false);
          matched = true;
        } else {
          // Mark matched synchronously so the rifle block and "No match" fallback are skipped.
          matched = true;
          var _piIsReturn = (document.getElementById('tb_transaction_type') || {}).value === 'Return';
          var _piForm    = document.getElementById('txn-form');
          var _piUrl     = _piForm ? _piForm.dataset.itemUrl : '';
          var _piPSel    = document.querySelector('[name="personnel"]');
          var _piPId     = _piPSel ? _piPSel.value : '';
          // Validate BEFORE populating the field.
          fetch(_piUrl + '?type=pistol&item_id=' + encodeURIComponent(piOpt.value), { credentials: 'same-origin' })
            .then(function(r) { return r.json(); })
            .then(function(d) {
              if (d.error) { showQrToast('\u2717 Pistol: ' + d.error, false); return; }
              var _piLabel = d.model + ' (' + d.serial_number + ')';
              if (_piIsReturn) {
                // Return: item must be Issued to the selected personnel.
                if (!_piPId) {
                  showQrToast('\u26A0 Select personnel first before scanning', false);
                } else if (d.item_status === 'Issued' && String(d.issued_to) === String(_piPId)) {
                  pistolSel.value = piOpt.value;
                  pistolSel.dispatchEvent(new Event('change'));
                  var _piQr = document.getElementById('fe_qr_item_id');
                  if (_piQr) _piQr.value = val;
                  showQrToast('\u2713 Pistol: ' + _piLabel, true);
                } else if (d.item_status === 'Issued') {
                  showQrToast('\u2717 Pistol: Issued to a different personnel \u2014 cannot return', false);
                } else {
                  showQrToast('\u2717 Pistol: Not currently issued \u2014 cannot return', false);
                }
              } else {
                // Withdrawal: item must be available.
                if (d.available) {
                  pistolSel.value = piOpt.value;
                  // Mutual exclusion on Withdrawal — one weapon per transaction.
                  if (rifleSel) { rifleSel.value = ''; rifleSel.dispatchEvent(new Event('change')); }
                  pistolSel.dispatchEvent(new Event('change'));
                  var _piQr2 = document.getElementById('fe_qr_item_id');
                  if (_piQr2) _piQr2.value = val;
                  showQrToast('\u2713 Pistol: ' + _piLabel, true);
                } else {
                  showQrToast('\u2717 Pistol: ' + (d.reason || 'Not available \u2014 cannot withdraw'), false);
                }
              }
            })
            .catch(function() { showQrToast('\u2717 Pistol: Could not validate item', false); });
        }
      }
    }

    if (!matched && rifleSel) {
      var riOpt = Array.from(rifleSel.options).find(function(o) {
        return o.value && (o.text.indexOf(val) !== -1 || o.value === val);
      });
      if (riOpt) {
        var rifleCol = document.getElementById('rifle-col');
        if (rifleCol && rifleCol.style.display === 'none') {
          showQrToast('\u26A0 Rifle is not used for this purpose', false);
          matched = true;
        } else {
          // Mark matched synchronously so the "No match" fallback is skipped.
          matched = true;
          var _riIsReturn = (document.getElementById('tb_transaction_type') || {}).value === 'Return';
          var _riForm    = document.getElementById('txn-form');
          var _riUrl     = _riForm ? _riForm.dataset.itemUrl : '';
          var _riPSel    = document.querySelector('[name="personnel"]');
          var _riPId     = _riPSel ? _riPSel.value : '';
          // Validate BEFORE populating the field.
          fetch(_riUrl + '?type=rifle&item_id=' + encodeURIComponent(riOpt.value), { credentials: 'same-origin' })
            .then(function(r) { return r.json(); })
            .then(function(d) {
              if (d.error) { showQrToast('\u2717 Rifle: ' + d.error, false); return; }
              var _riLabel = d.model + ' (' + d.serial_number + ')';
              if (_riIsReturn) {
                // Return: item must be Issued to the selected personnel.
                if (!_riPId) {
                  showQrToast('\u26A0 Select personnel first before scanning', false);
                } else if (d.item_status === 'Issued' && String(d.issued_to) === String(_riPId)) {
                  rifleSel.value = riOpt.value;
                  rifleSel.dispatchEvent(new Event('change'));
                  var _riQr = document.getElementById('fe_qr_item_id');
                  if (_riQr) _riQr.value = val;
                  showQrToast('\u2713 Rifle: ' + _riLabel, true);
                } else if (d.item_status === 'Issued') {
                  showQrToast('\u2717 Rifle: Issued to a different personnel \u2014 cannot return', false);
                } else {
                  showQrToast('\u2717 Rifle: Not currently issued \u2014 cannot return', false);
                }
              } else {
                // Withdrawal: item must be available.
                if (d.available) {
                  rifleSel.value = riOpt.value;
                  // Mutual exclusion on Withdrawal — one weapon per transaction.
                  if (pistolSel) { pistolSel.value = ''; pistolSel.dispatchEvent(new Event('change')); }
                  rifleSel.dispatchEvent(new Event('change'));
                  var _riQr2 = document.getElementById('fe_qr_item_id');
                  if (_riQr2) _riQr2.value = val;
                  showQrToast('\u2713 Rifle: ' + _riLabel, true);
                } else {
                  showQrToast('\u2717 Rifle: ' + (d.reason || 'Not available \u2014 cannot withdraw'), false);
                }
              }
            })
            .catch(function() { showQrToast('\u2717 Rifle: Could not validate item', false); });
        }
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

    // Do not intercept when a text input or textarea is focused — the user is
    // typing manually and their keystrokes must reach the focused element unchanged.
    var _active = document.activeElement;
    var _isTextFocus = _active && (
      _active.tagName === 'TEXTAREA' ||
      (_active.tagName === 'INPUT' &&
        _active.type !== 'checkbox' && _active.type !== 'radio' &&
        _active.type !== 'button'   && _active.type !== 'submit' &&
        _active.type !== 'hidden')
    );
    if (_isTextFocus) {
      buf = '';
      scanning = false;
      return;
    }

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

// ── Purpose weapon selection → auto-fill ammo quantities ─────────────────────
(function() {
  var dutyEl    = document.getElementById('tb_purpose');
  var pistolEl  = document.querySelector('[name="pistol"]');
  var rifleEl   = document.querySelector('[name="rifle"]');
  var magQtyEl  = document.querySelector('[name="pistol_magazine_quantity"]');
  var ammoQtyEl = document.querySelector('[name="pistol_ammunition_quantity"]');
  var rifleQtyEl    = document.querySelector('[name="rifle_magazine_quantity"]');
  var rifleAmmoQtyEl = document.querySelector('[name="rifle_ammunition_quantity"]');
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

  function applyPurposeDefaults() {
    if (!dutyEl || !dutyEl.value) { updateAmmoLabels(); return; }
    var formEl = document.getElementById('txn-form');
    var pcfgAll = {};
    // Prefer live-fetched config (updated after purpose edits without reload);
    // fall back to the server-rendered inline blob.
    if (window._livePurposeConfig) {
      pcfgAll = window._livePurposeConfig;
    } else if (formEl && formEl.dataset.purposeConfig) {
      try { pcfgAll = JSON.parse(formEl.dataset.purposeConfig); } catch (_) {}
    }
    var cfg = pcfgAll[dutyEl.value] || {};
    var hasPistol = pistolEl && pistolEl.value;
    if (hasPistol) {
      if (magQtyEl  && !magQtyEl.value  && cfg.pistol_mag_qty)  magQtyEl.value  = cfg.pistol_mag_qty;
      if (ammoQtyEl && !ammoQtyEl.value && cfg.pistol_ammo_qty) ammoQtyEl.value = cfg.pistol_ammo_qty;
    }
    var hasRifle = rifleEl && rifleEl.value;
    if (hasRifle) {
      var rifleText = getSelectedText(rifleEl);
      var rifleQty = rifleText.indexOf('M14') !== -1
        ? (cfg.rifle_short_mag_qty || 0)
        : (cfg.rifle_long_mag_qty  || 0);
      if (rifleQtyEl    && !rifleQtyEl.value    && rifleQty)          rifleQtyEl.value    = rifleQty;
      if (rifleAmmoQtyEl && !rifleAmmoQtyEl.value && cfg.rifle_ammo_qty) rifleAmmoQtyEl.value = cfg.rifle_ammo_qty;
    }
    updateAmmoLabels();
  }

  if (dutyEl)   dutyEl.addEventListener('change', applyPurposeDefaults);
  if (pistolEl) pistolEl.addEventListener('change', applyPurposeDefaults);
  if (rifleEl)  rifleEl.addEventListener('change', applyPurposeDefaults);
  applyPurposeDefaults();

  // Fetch live purpose config from the API so the form picks up any purpose
  // changes made in Settings without needing a full page reload.
  (function fetchLivePurposeConfig() {
    fetch('/transactions/api/purpose-config/', { credentials: 'same-origin' })
      .then(function(r) { return r.ok ? r.json() : null; })
      .then(function(data) {
        if (!data) return;
        window._livePurposeConfig = data;
        // Also refresh the purpose dropdown options with the live list
        if (dutyEl) {
          var currentVal = dutyEl.value;
          // Remove dynamically-added options (keep any blank placeholder)
          while (dutyEl.options.length > 1) dutyEl.remove(1);
          Object.keys(data).forEach(function(name) {
            var opt = document.createElement('option');
            opt.value = name;
            opt.textContent = name;
            if (data[name].hotkey) opt.setAttribute('data-hotkey', data[name].hotkey);
            if (name === currentVal) opt.selected = true;
            dutyEl.appendChild(opt);
          });
          if (currentVal) dutyEl.value = currentVal;
        }
        applyPurposeDefaults();
      })
      .catch(function() { /* silent — fall back to inline config */ });
  })();
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
  var _form = document.getElementById('txn-form');
  var _trDefaultHours = _form ? (parseInt(_form.dataset.trDefaultHours, 10) || 24) : 24;
  var _defaultIssuance = _form ? (_form.dataset.defaultIssuance || '') : '';
  // Pre-select the configured default issuance type on initial load (only when blank)
  if (tbIssuance && !tbIssuance.value && _defaultIssuance) {
    for (var i = 0; i < tbIssuance.options.length; i++) {
      if (tbIssuance.options[i].value === _defaultIssuance) {
        tbIssuance.selectedIndex = i;
        break;
      }
    }
  }
  function toggleReturnBy() {
    if (!returnBySection) return;
    var isWithdrawal = tbType && tbType.value === 'Withdrawal';
    var isTR = tbIssuance && (tbIssuance.value || '').toUpperCase().startsWith('TR');
    returnBySection.style.display = (isWithdrawal && isTR) ? '' : 'none';
    // Pre-fill with now + configured TR return hours when TR is selected and field is still empty
    if (isWithdrawal && isTR) {
      var inp = document.getElementById('id_return_by');
      if (inp && !inp.value) {
        var d = new Date(Date.now() + _trDefaultHours * 60 * 60 * 1000);
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

  // Called by checkPersonnel() with the already-fetched personnel_status data,
  // so no second round-trip to the same endpoint is needed.
  window._sidebarUpdatePersonnel = function(d) {
    if (d && d.id_card_front_url) {
      setImg('sidebar-id-card-img', d.id_card_front_url);
      showEl('sidebar-personnel', 'flex');
    } else {
      hideEl('sidebar-personnel');
    }
  };

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
    // Personnel sidebar is now updated by checkPersonnel() using the data it
    // already receives — no separate fetch or change listener needed here.
    if (personnelSel && !personnelSel.value) {
      // If no personnel is selected on load, ensure the sidebar is hidden.
      hideEl('sidebar-personnel');
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
