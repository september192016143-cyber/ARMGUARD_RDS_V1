import re

TEMPLATE = r'C:\Users\9533RDS\Desktop\hermosa\ARMGUARD_RDS_V1\project\armguard\templates\transactions\transaction_form.html'
JS_FILE  = r'C:\Users\9533RDS\Desktop\hermosa\ARMGUARD_RDS_V1\project\armguard\static\js\transaction_form.js'

# ── 1. Fix template ────────────────────────────────────────────────────────────
with open(TEMPLATE, 'r', encoding='utf-8') as f:
    tmpl = f.read()

original_len = len(tmpl)

# 1a. Remove duplicate top {% block extra_js %} (the script-tag-only one added earlier)
#     It looks like: {# F1 FIX: ... #}\n{% block extra_js %}\n<script src=...></script>\n{% endblock %}\n\n
tmpl = re.sub(
    r'\{# F1 FIX:.*?#\}\n\{% block extra_js %\}\n<script[^>]*></script>\n\{% endblock %\}\n\n',
    '\n',
    tmpl, flags=re.DOTALL
)
print(f'After 1a: {len(tmpl)} chars (removed {original_len - len(tmpl)})')

# 1b. Remove the orphaned topbar <script> block containing function definitions
#     (no closing </script> — it was removed in a previous session)
before_1b = len(tmpl)
tmpl = re.sub(
    r'(?s)<script>\nfunction toggleDutyOther\(\) \{.*?\n\}\n(?=\{% endblock %\})',
    '',
    tmpl
)
print(f'After 1b: {len(tmpl)} chars (removed {before_1b - len(tmpl)})')

# 1c. Replace big bottom {% block extra_js %} with just the static JS tag
before_1c = len(tmpl)
new_block = "{% block extra_js %}\n<script src=\"{% static 'js/transaction_form.js' %}\" defer></script>\n{% endblock %}"
tmpl = re.sub(
    r'(?s)\{% block extra_js %\}\n<script>\n// Style all raw widgets.*?\{% endblock %\}',
    new_block,
    tmpl
)
print(f'After 1c: {len(tmpl)} chars (removed {before_1c - len(tmpl)})')

with open(TEMPLATE, 'w', encoding='utf-8', newline='\n') as f:
    f.write(tmpl)
print('Template saved.')

# Verify: count remaining <script> tags
script_count = tmpl.count('<script')
print(f'Remaining <script> tags in template: {script_count}')
print(f'Remaining inline onclick/onchange: {tmpl.count("onclick=") + tmpl.count("onchange=") + tmpl.count("onfocus=") + tmpl.count("onblur=")}')

# ── 2. Append new JS sections to transaction_form.js ──────────────────────────
NEW_JS = """
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
        showQrToast('\\u2713 Personnel: ' + pOpt.text.trim(), true);
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
        showQrToast('\\u2713 Pistol: ' + piOpt.text.trim(), true);
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
        showQrToast('\\u2713 Rifle: ' + riOpt.text.trim(), true);
        matched = true;
      }
    }

    if (!matched) {
      showQrToast('\\u2717 No match found: ' + val, false);
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
  }, true); // capture phase
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
    if (pistolLabel) pistolLabel.textContent = pistolAmmo ? '\\u2192 ' + pistolAmmo : '';

    var rifleText = getSelectedText(rifleEl);
    var rifleAmmo = '';
    for (var rmodel in RIFLE_AMMO) {
      if (rifleText.indexOf(rmodel) !== -1) { rifleAmmo = RIFLE_AMMO[rmodel]; break; }
    }
    if (rifleLabel) rifleLabel.textContent = rifleAmmo ? '\\u2192 ' + rifleAmmo : '';
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

  document.addEventListener('DOMContentLoaded', function() {
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
  });
})();
"""

with open(JS_FILE, 'r', encoding='utf-8') as f:
    js = f.read()

js_original_len = len(js)

# Only append if not already appended
if 'Widget initialization' not in js:
    js = js + NEW_JS
    with open(JS_FILE, 'w', encoding='utf-8', newline='\n') as f:
        f.write(js)
    print(f'JS: {js_original_len} -> {len(js)} chars (appended)')
else:
    print('JS: already has widget code, skipping append')

print('All done.')
