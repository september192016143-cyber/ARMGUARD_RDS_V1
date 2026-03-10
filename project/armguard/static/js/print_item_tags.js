(function () {
  var cfgEl = document.getElementById('item-tags-config');
  if (!cfgEl) return;
  var cfg = JSON.parse(cfgEl.textContent);
  var GEN_URL    = cfg.genUrl;
  var REGEN_BASE  = cfg.regenBase.replace('PLACEHOLDER/', '');
  var DELETE_BASE = cfg.deleteBase.replace('PLACEHOLDER/', '');
  var PRINT_URL  = cfg.printUrl;
  var CSRF       = cfg.csrf;

  function updateCount() {
    document.getElementById('selCount').textContent =
      document.querySelectorAll('.tag-checkbox:checked').length;
  }
  function toggleCheck(id) {
    var cb = document.querySelector('.tag-checkbox[value="' + id + '"]');
    if (cb) { cb.checked = !cb.checked; updateCount(); }
  }
  function selectAll() {
    document.querySelectorAll('.tag-checkbox').forEach(function (c) { c.checked = true; });
    updateCount();
  }
  function clearAll() {
    document.querySelectorAll('.tag-checkbox').forEach(function (c) { c.checked = false; });
    updateCount();
  }
  function getStack() {
    return (document.getElementById('stackCount') || {}).value || '1';
  }
  function printSelected() {
    var ids = Array.from(document.querySelectorAll('.tag-checkbox:checked')).map(function (c) { return c.value; });
    if (!ids.length) { alert('Select at least one item.'); return; }
    window.open(PRINT_URL + '?ids=' + ids.join(',') + '&stack=' + getStack(), '_blank');
  }
  function printAll() {
    window.open(PRINT_URL + '?all=1&stack=' + getStack(), '_blank');
  }
  function _setBusy(btn, busy) {
    btn.querySelector('.regen-icon').style.display = busy ? 'none' : 'inline';
    btn.querySelector('.regen-spinner').style.display = busy ? 'inline' : 'none';
    btn.disabled = busy;
  }

  function regenTag(itemId, btn) {
    _setBusy(btn, true);
    var url = REGEN_BASE + encodeURIComponent(itemId) + '/';
    fetch(url, { method: 'POST', headers: { 'X-CSRFToken': CSRF, 'Content-Type': 'application/json' } })
      .then(function (resp) {
        var ct = resp.headers.get('content-type') || '';
        if (!ct.includes('application/json')) return resp.text().then(function (t) { throw new Error('Non-JSON: ' + t.substring(0, 120)); });
        return resp.json();
      })
      .then(function (data) {
        if (data.success) {
          var wrap = document.getElementById('wrap-' + itemId);
          var img = wrap.querySelector('img');
          if (img) {
            img.src = data.thumb_url + '?v=' + Date.now();
          } else {
            var div = wrap.querySelector('.tag-no-thumb');
            if (div) {
              var newImg = document.createElement('img');
              newImg.id = 'thumb-' + itemId; newImg.src = data.thumb_url; newImg.alt = 'Tag';
              div.replaceWith(newImg);
            }
          }
          var badge = wrap.querySelector('.status-badge');
          if (badge) { badge.textContent = 'OK'; badge.className = 'status-badge badge-ok'; }
          var actions = wrap.querySelector('.tag-actions');
          if (actions && !actions.querySelector('a.btn-primary')) {
            var a = document.createElement('a');
            a.href = PRINT_URL + '?ids=' + itemId; a.target = '_blank';
            a.className = 'btn btn-primary btn-sm';
            a.innerHTML = '<i class="fas fa-print"></i> Print';
            actions.appendChild(a);
          }
        } else { alert('Error: ' + (data.error || 'Unknown error')); }
      })
      .catch(function (e) { alert('Request failed: ' + e.message); })
      .then(function () { _setBusy(btn, false); });
  }

  function _bulkGenerate(force, btn) {
    if (force && !confirm('Regenerate ALL item tags? This may take a while.')) return;
    _setBusy(btn, true);
    var fd = new FormData();
    fd.append('force', force ? '1' : '0');
    fd.append('csrfmiddlewaretoken', CSRF);
    fetch(GEN_URL, { method: 'POST', body: fd })
      .then(function (resp) {
        var ct = resp.headers.get('content-type') || '';
        if (!ct.includes('application/json')) return resp.text().then(function (t) { throw new Error('Non-JSON: ' + t.substring(0, 120)); });
        return resp.json();
      })
      .then(function (data) {
        if (data.success) {
          var msg = 'Done — generated: ' + data.generated + ', skipped: ' + data.skipped +
            (data.errors.length ? ', errors: ' + data.errors.length : '');
          alert(msg); location.reload();
        } else { alert('Error: ' + (data.error || JSON.stringify(data))); }
      })
      .catch(function (e) { alert('Request failed: ' + e.message); })
      .then(function () { _setBusy(btn, false); });
  }

  function genMissing(btn) { _bulkGenerate(false, btn); }
  function regenAll(btn)   { _bulkGenerate(true, btn); }

  function deleteTag(itemId, btn) {
    if (!confirm('Delete this item tag PNG from disk?')) return;
    _setBusy(btn, true);
    var url = DELETE_BASE + encodeURIComponent(itemId) + '/';
    fetch(url, { method: 'POST', headers: { 'X-CSRFToken': CSRF } })
      .then(function (resp) {
        var ct = resp.headers.get('content-type') || '';
        if (!ct.includes('application/json')) return resp.text().then(function (t) { throw new Error('Non-JSON: ' + t.substring(0, 120)); });
        return resp.json();
      })
      .then(function (data) {
        if (data.success) {
          var wrap = document.getElementById('wrap-' + itemId);
          var img = wrap.querySelector('img');
          if (img) { var ph = document.createElement('div'); ph.className = 'tag-no-thumb'; img.replaceWith(ph); }
          var printBtn = wrap.querySelector('a.btn-primary'); if (printBtn) printBtn.remove();
          btn.remove();
          var badge = wrap.querySelector('.badge-ok'); if (badge) badge.remove();
        } else {
          alert('Error: ' + (data.error || 'Unknown error'));
          _setBusy(btn, false);
        }
      })
      .catch(function (e) { alert('Request failed: ' + e.message); _setBusy(btn, false); });
  }

  /* ── Event delegation ── */
  document.addEventListener('change', function (e) {
    if (e.target && e.target.classList.contains('tag-checkbox')) updateCount();
  });

  document.addEventListener('click', function (e) {
    var t = e.target.closest ? e.target.closest('[data-action]') : null;
    if (!t) return;
    var action = t.getAttribute('data-action');
    if (action === 'select-all')     { e.preventDefault(); selectAll(); return; }
    if (action === 'clear-all')      { e.preventDefault(); clearAll(); return; }
    if (action === 'print-selected') { printSelected(); return; }
    if (action === 'print-all')      { printAll(); return; }
    if (action === 'gen-missing')    { genMissing(t); return; }
    if (action === 'regen-all')      { regenAll(t); return; }

    var itemAction = t.getAttribute('data-item-action');
    var itemId     = t.getAttribute('data-item-id');
    if (itemAction === 'toggle-check') { e.preventDefault(); toggleCheck(itemId); return; }
    if (itemAction === 'regen')        { regenTag(itemId, t); return; }
    if (itemAction === 'delete')       { deleteTag(itemId, t); return; }
    if (itemAction === 'print-single') {
      e.preventDefault();
      t.href = PRINT_URL + '?ids=' + itemId + '&stack=' + getStack();
      return;
    }
  });
})();
