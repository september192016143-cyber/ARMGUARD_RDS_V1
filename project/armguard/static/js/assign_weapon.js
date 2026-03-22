/**
 * ArmGuard RDS — assign_weapon.js
 *
 * Barcode/QR scanner support for the Assign Weapon page.
 *
 * Strategy: keep focus on a hidden off-screen input (#aw-scan-capture) so that
 * scanner key bursts are never intercepted by an open <select> dropdown.
 * A fast keydown burst (≤50 ms gap) is treated as a scanner input; slower
 * typing is ignored (user navigating the dropdowns manually).
 */
(function () {
  var captureInput = document.getElementById('aw-scan-capture');
  var buf = '';
  var lastKey = 0;
  var scanning = false;
  var SCANNER_SPEED = 50;
  var MIN_LEN = 3;

  // After user interacts with a select (change/blur), return focus to the
  // hidden capture input so the next scan lands safely.
  ['pistol-select', 'rifle-select'].forEach(function (id) {
    var sel = document.getElementById(id);
    if (!sel) return;
    sel.addEventListener('change', function () {
      if (captureInput) setTimeout(function () { captureInput.focus(); }, 0);
    });
    sel.addEventListener('blur', function () {
      if (captureInput) setTimeout(function () { captureInput.focus(); }, 0);
    });
  });

  function showQrToast(msg, ok) {
    var t = document.getElementById('aw-qr-toast');
    if (!t) {
      t = document.createElement('div');
      t.id = 'aw-qr-toast';
      t.style.cssText = 'position:fixed;bottom:1.5rem;right:1.5rem;padding:.6rem 1.1rem;border-radius:.5rem;font-size:.85rem;font-weight:600;z-index:9999;transition:opacity .4s;pointer-events:none';
      document.body.appendChild(t);
    }
    t.style.background = ok ? '#166534' : '#7f1d1d';
    t.style.color = '#fff';
    t.textContent = msg;
    t.style.opacity = '1';
    clearTimeout(t._hide);
    t._hide = setTimeout(function () { t.style.opacity = '0'; }, 2500);
  }

  function tryAutofill(val) {
    var pistolSel = document.querySelector('[name="pistol"]');
    var rifleSel  = document.querySelector('[name="rifle"]');
    var matched = false;

    // Check all options (including disabled) across both selects for a match.
    // This allows the scanner to produce a specific "already assigned" message
    // instead of the generic "No match" when the scanned weapon is locked.
    var allOptions = [];
    if (pistolSel) allOptions = allOptions.concat(Array.from(pistolSel.options));
    if (rifleSel)  allOptions = allOptions.concat(Array.from(rifleSel.options));

    var disabledMatch = allOptions.find(function (o) {
      return o.disabled && o.dataset &&
        (o.dataset.qr === val || o.dataset.itemId === val || o.text.indexOf(val) !== -1);
    });
    if (disabledMatch) {
      var holder = disabledMatch.dataset.holder || 'another person';
      var model  = disabledMatch.dataset.model  || '';
      var serial = disabledMatch.dataset.serial || '';
      var detail = model ? model + (serial ? ' SN: ' + serial : '') : 'Item';
      showQrToast('\u2717 ' + detail + ' \u2014 already assigned to ' + holder, false);
      return;
    }

    if (!matched && pistolSel) {
      var piOpt = Array.from(pistolSel.options).find(function (o) {
        return !o.disabled && o.value && (o.value === val || (o.dataset && o.dataset.qr === val) || o.text.indexOf(val) !== -1);
      });
      if (piOpt) {
        pistolSel.value = piOpt.value;
        pistolSel.dispatchEvent(new Event('change'));
        showQrToast('\u2713 Pistol: ' + piOpt.text.trim(), true);
        matched = true;
      }
    }

    if (!matched && rifleSel) {
      var riOpt = Array.from(rifleSel.options).find(function (o) {
        return !o.disabled && o.value && (o.value === val || (o.dataset && o.dataset.qr === val) || o.text.indexOf(val) !== -1);
      });
      if (riOpt) {
        rifleSel.value = riOpt.value;
        rifleSel.dispatchEvent(new Event('change'));
        showQrToast('\u2713 Rifle: ' + riOpt.text.trim(), true);
        matched = true;
      }
    }

    if (!matched) {
      showQrToast('\u2717 No match: ' + val, false);
    }
  }

  document.addEventListener('keydown', function (e) {
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
      if (!scanning) {
        // Scan burst detected — close any open select by blurring it and
        // moving focus to the safe capture input.
        var ae = document.activeElement;
        if (ae && ae.tagName === 'SELECT') {
          ae.blur();
          if (captureInput) captureInput.focus();
        }
        scanning = true;
      }
      e.preventDefault();
      e.stopPropagation();
    } else {
      buf = e.key;
      scanning = false;
    }
    lastKey = now;
  }, window.pjaxController ? { capture: true, signal: window.pjaxController.signal } : true); // capture phase — fires before focus target
}());
