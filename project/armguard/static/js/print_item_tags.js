(function () {
  var cfgEl = document.getElementById('item-tags-config');
  if (!cfgEl) return;
  var cfg = JSON.parse(cfgEl.textContent);
  var GEN_URL    = cfg.genUrl;
  var REGEN_BASE  = cfg.regenBase.replace('PLACEHOLDER/', '');
  var DELETE_BASE = cfg.deleteBase.replace('PLACEHOLDER/', '');
  var PRINT_URL  = cfg.printUrl;
  var CSRF       = cfg.csrf;

  // ── Lazy image loading (IntersectionObserver) ─────────────────────────────
  var lazyObserver = null;
  function observeLazyImages(root) {
    var imgs = (root || document).querySelectorAll('img.lazy-tag[data-src]');
    if (!imgs.length) return;
    if (!('IntersectionObserver' in window)) {
      imgs.forEach(function (img) { img.src = img.dataset.src; img.removeAttribute('data-src'); img.classList.remove('lazy-tag'); });
      return;
    }
    if (!lazyObserver) {
      lazyObserver = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          var img = entry.target;
          img.src = img.dataset.src;
          img.removeAttribute('data-src');
          img.classList.remove('lazy-tag');
          lazyObserver.unobserve(img);
        });
      }, { rootMargin: '200px 0px' });
    }
    imgs.forEach(function (img) { lazyObserver.observe(img); });
  }
  observeLazyImages();
  // ─────────────────────────────────────────────────────────────────────────

  // ── Real-time filter (PJAX) ───────────────────────────────────────────────
  var filterForm = document.getElementById('tags-filter-form');
  var qInput     = document.getElementById('tags-q');
    var typeSelect = null;
  var modelSel   = document.getElementById('tags-model');
  var tagGrid    = document.getElementById('tagGrid');
  var clearBtn   = document.getElementById('tags-clear-btn');
  var debounceTimer;

  if (filterForm && tagGrid) {
    var baseUrl = filterForm.dataset.url || window.location.pathname;

    function hasFilters() {
      return !!((qInput && qInput.value.trim()) ||
                (typeSelect && typeSelect.value) ||
                (modelSel && modelSel.value));
    }

    function doFilterFetch() {
      var params = new URLSearchParams();
      if (qInput && qInput.value.trim()) params.set('q', qInput.value.trim());
      if (typeSelect && typeSelect.value) params.set('type', typeSelect.value);
      if (modelSel && modelSel.value) params.set('model', modelSel.value);
      fetch(baseUrl + '?' + params.toString(), {
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        tagGrid.innerHTML = html;
        var statsEl = document.getElementById('tags-ajax-stats');
        if (statsEl) {
          var el;
          el = document.getElementById('tags-stat-total');    if (el) el.textContent = statsEl.dataset.total;
          el = document.getElementById('tags-stat-with-tag'); if (el) el.textContent = statsEl.dataset.withTag;
          el = document.getElementById('tags-stat-without-tag'); if (el) el.textContent = statsEl.dataset.withoutTag;
        }
        var sc = document.getElementById('selCount');
        if (sc) sc.textContent = '0';
        if (clearBtn) clearBtn.style.display = hasFilters() ? '' : 'none';
        observeLazyImages(tagGrid);
      });
    }

    if (qInput) {
      qInput.addEventListener('input', function () {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(doFilterFetch, 400);
      });
    }
    if (typeSelect) typeSelect.addEventListener('change', doFilterFetch);
    if (modelSel)   modelSel.addEventListener('change',  doFilterFetch);

    filterForm.addEventListener('submit', function (e) {
      e.preventDefault();
      clearTimeout(debounceTimer);
      doFilterFetch();
    });
  }
  // ─────────────────────────────────────────────────────────────────────────

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
        var wrap = document.getElementById('wrap-' + itemId);
        if (data.success) {
          var img = wrap ? wrap.querySelector('img') : null;
          if (img) {
            // Clear any pending lazy state before forcing the new src.
            img.removeAttribute('data-src');
            img.classList.remove('lazy-tag');
            if (lazyObserver) lazyObserver.unobserve(img);
            img.src = data.thumb_url + '?v=' + Date.now();
          } else {
            var div = wrap ? wrap.querySelector('.tag-no-thumb') : null;
            if (div) {
              var newImg = document.createElement('img');
              newImg.id = 'thumb-' + itemId; newImg.src = data.thumb_url; newImg.alt = 'Tag';
              div.replaceWith(newImg);
            }
          }
          // Fix: template uses .badge-ok not .status-badge
          var badge = wrap ? wrap.querySelector('.badge-ok, .badge-missing') : null;
          if (badge) { badge.textContent = 'OK'; badge.className = 'badge-ok'; }
          else if (wrap) {
            var infoTop = wrap.querySelector('.tag-info > div');
            if (infoTop) { var nb = document.createElement('span'); nb.className = 'badge-ok'; nb.textContent = 'OK'; infoTop.appendChild(nb); }
          }
          var actions = wrap ? wrap.querySelector('.tag-actions') : null;
          if (actions && !actions.querySelector('a.btn-primary')) {
            var a = document.createElement('a');
            a.href = PRINT_URL + '?ids=' + itemId; a.target = '_blank';
            a.className = 'btn btn-primary btn-sm';
            a.setAttribute('data-item-action', 'print-single');
            a.setAttribute('data-item-id', itemId);
            a.innerHTML = '<i class="fas fa-print"></i> Print';
            actions.insertBefore(a, btn.nextSibling);
          }
          // Clear any previous inline error
          var prevErr = wrap ? wrap.querySelector('.regen-error') : null;
          if (prevErr) prevErr.remove();
        } else {
          // Show error inline in card so it's visible without dismissing an alert
          var errMsg = data.error || 'Unknown error';
          if (wrap) {
            var card = wrap.querySelector('.tag-card');
            var existing = wrap.querySelector('.regen-error');
            if (existing) { existing.textContent = '\u274C ' + errMsg; }
            else if (card) {
              var errDiv = document.createElement('div');
              errDiv.className = 'regen-error';
              errDiv.style.cssText = 'font-size:.65rem;color:#f87171;padding:.3rem .6rem;background:rgba(239,68,68,.1);border-top:1px solid rgba(239,68,68,.3);word-break:break-all;';
              errDiv.textContent = '\u274C ' + errMsg;
              card.appendChild(errDiv);
            }
          } else { alert('Regen error: ' + errMsg); }
        }
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
          var msg = 'Done — generated: ' + data.generated + ', skipped: ' + data.skipped;
          if (data.errors && data.errors.length) {
            msg += '\n\nErrors (' + data.errors.length + '):';
            data.errors.forEach(function (e) { msg += '\n• ' + e.id + ': ' + e.error; });
          }
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
  }, window.pjaxController ? { signal: window.pjaxController.signal } : undefined);

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
  }, window.pjaxController ? { signal: window.pjaxController.signal } : undefined);
})();
