/* storage_panel.js — Storage Status panel for /users/ (admin only) */
(function () {
  'use strict';

  const API_URL = '/users/storage/';
  const PAGE_SIZE = 10;

  // Current page state per group key
  var pages = { personnel: 1, pistols: 1, rifles: 1 };
  // Last fetched data cache
  var cachedData = null;

  function fmt(n) {
    return Number(n).toLocaleString();
  }

  function pctColor(pct) {
    if (pct >= 90) return 'var(--danger)';
    if (pct >= 70) return '#f59e0b';
    return 'var(--success, #22c55e)';
  }

  function renderRecordTable(key, group, label) {
    var rows  = (group && group.rows)  ? group.rows  : [];
    var total = (group && group.total) ? group.total : '—';
    var avg   = (group && group.avg)   ? group.avg   : '—';
    var count = (group && group.count !== undefined) ? group.count : '—';
    var page      = pages[key] || 1;
    var totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
    if (page > totalPages) { page = totalPages; pages[key] = page; }
    var start = (page - 1) * PAGE_SIZE;
    var pageRows = rows.slice(start, start + PAGE_SIZE);

    var rowsHtml = pageRows.length === 0
      ? '<tr><td colspan="2" style="color:var(--muted);padding:.4rem .3rem">No files found.</td></tr>'
      : pageRows.map(function (r) {
          return '<tr style="border-top:1px solid var(--border,rgba(255,255,255,.07))">' +
            '<td style="padding:.2rem .3rem;color:var(--text);font-size:.75rem;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + r.id + '">' + r.name + '</td>' +
            '<td style="text-align:right;padding:.2rem .3rem;color:var(--primary);font-size:.75rem;white-space:nowrap">' + r.size + '</td>' +
            '</tr>';
        }).join('');

    // Pagination controls
    var paginationHtml = '';
    if (totalPages > 1) {
      var btns = '';
      // Prev
      btns += '<button data-key="' + key + '" data-page="' + (page - 1) + '" ' +
        (page <= 1 ? 'disabled ' : '') +
        'style="' + pageBtnStyle(false) + '">&lsaquo;</button>';
      // Page numbers (window of ±2)
      for (var i = 1; i <= totalPages; i++) {
        if (i === page) {
          btns += '<button disabled style="' + pageBtnStyle(true) + '">' + i + '</button>';
        } else if (i >= page - 2 && i <= page + 2) {
          btns += '<button data-key="' + key + '" data-page="' + i + '" style="' + pageBtnStyle(false) + '">' + i + '</button>';
        }
      }
      // Next
      btns += '<button data-key="' + key + '" data-page="' + (page + 1) + '" ' +
        (page >= totalPages ? 'disabled ' : '') +
        'style="' + pageBtnStyle(false) + '">&rsaquo;</button>';
      paginationHtml = '<div style="display:flex;gap:.25rem;align-items:center;margin-top:.5rem;flex-wrap:wrap">' + btns + '</div>';
    }

    var el = document.getElementById('pr-' + key);
    if (!el) return;
    el.innerHTML =
      '<div style="font-size:.72rem;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:.4rem">' + label + '</div>' +
      '<div style="font-size:.72rem;color:var(--muted);margin-bottom:.4rem">' +
        count + ' records &mdash; Total: <strong style="color:var(--text)">' + total + '</strong>' +
        ' &mdash; Avg: <strong style="color:var(--text)">' + avg + '</strong>' +
      '</div>' +
      '<table style="width:100%;border-collapse:collapse">' +
        '<thead><tr style="color:var(--muted);font-size:.68rem">' +
          '<th style="text-align:left;padding:.15rem .3rem">Name / ID</th>' +
          '<th style="text-align:right;padding:.15rem .3rem">Used</th>' +
        '</tr></thead>' +
        '<tbody>' + rowsHtml + '</tbody>' +
      '</table>' +
      paginationHtml;
  }

  function pageBtnStyle(active) {
    return 'cursor:pointer;border:1px solid var(--border,rgba(255,255,255,.12));border-radius:4px;padding:.1rem .45rem;font-size:.72rem;background:' +
      (active ? 'var(--primary)' : 'var(--surface2,rgba(255,255,255,.06))') +
      ';color:' + (active ? '#fff' : 'var(--text)') + ';';
  }

  function renderPerRecord(pr) {
    var grid = document.getElementById('storage-per-record-grid');
    if (!grid) return;
    // Build the three column containers once
    if (!document.getElementById('pr-personnel')) {
      grid.innerHTML =
        '<div id="pr-personnel"></div>' +
        '<div id="pr-pistols"></div>' +
        '<div id="pr-rifles"></div>';
      // Single delegated listener for all pagination buttons
      grid.addEventListener('click', function (e) {
        var btn = e.target.closest('button[data-key]');
        if (!btn || btn.disabled) return;
        var k = btn.getAttribute('data-key');
        var p = parseInt(btn.getAttribute('data-page'), 10);
        if (!k || isNaN(p) || !cachedData) return;
        pages[k] = p;
        var labels = { personnel: 'Personnel', pistols: 'Pistols', rifles: 'Rifles' };
        renderRecordTable(k, cachedData.per_record[k], labels[k]);
      });
    }
    renderRecordTable('personnel', pr.personnel, 'Personnel');
    renderRecordTable('pistols', pr.pistols, 'Pistols');
    renderRecordTable('rifles', pr.rifles, 'Rifles');
  }

  function render(data) {
    // ── Disk bar ──────────────────────────────────────────────────────────────
    const disk = data.disk || {};
    if (disk.used_pct !== undefined) {
      const pct = disk.used_pct;
      document.getElementById('storage-disk-label').textContent = pct + '% used';
      const bar = document.getElementById('storage-disk-bar');
      bar.style.width = pct + '%';
      bar.style.background = pctColor(pct);
      document.getElementById('storage-disk-used').textContent = 'Used: ' + (disk.used || '—');
      document.getElementById('storage-disk-free').textContent = 'Free: ' + (disk.free || '—') + ' / ' + (disk.total || '—');
    } else {
      document.getElementById('storage-disk-label').textContent = 'N/A';
    }

    // ── Media folders ─────────────────────────────────────────────────────────
    const tbody = document.getElementById('storage-folders-body');
    const folders = data.folders || [];
    if (folders.length === 0) {
      tbody.innerHTML = '<tr><td colspan="3" style="color:var(--muted);padding:.5rem .3rem">No data.</td></tr>';
    } else {
      tbody.innerHTML = folders.map(function (f) {
        return '<tr style="border-top:1px solid var(--border,rgba(255,255,255,.07))">' +
          '<td style="padding:.25rem .3rem;color:var(--text)">' + f.label + '</td>' +
          '<td style="text-align:right;padding:.25rem .3rem;color:var(--muted)">' + fmt(f.files) + '</td>' +
          '<td style="text-align:right;padding:.25rem .3rem;color:var(--text-secondary,var(--muted))">' + f.size + '</td>' +
          '</tr>';
      }).join('');
    }

    // ── DB size ───────────────────────────────────────────────────────────────
    document.getElementById('storage-db-size').textContent =
      (data.db && data.db.size) ? data.db.size : '—';

    // ── Record counts ─────────────────────────────────────────────────────────
    const rtbody = document.getElementById('storage-records-body');
    const records = data.records || [];
    if (records.length === 0) {
      rtbody.innerHTML = '<tr><td colspan="2" style="color:var(--muted);padding:.5rem .3rem">No data.</td></tr>';
    } else {
      rtbody.innerHTML = records.map(function (r) {
        return '<tr style="border-top:1px solid var(--border,rgba(255,255,255,.07))">' +
          '<td style="padding:.25rem .3rem;color:var(--text)">' + r.label + '</td>' +
          '<td style="text-align:right;padding:.25rem .3rem;font-weight:600;color:var(--primary)">' + fmt(r.count) + '</td>' +
          '</tr>';
      }).join('');
    }

    // ── Per-record storage ────────────────────────────────────────────────────
    cachedData = data;
    pages = { personnel: 1, pistols: 1, rifles: 1 };
    renderPerRecord(data.per_record || {});

    // ── Timestamp ─────────────────────────────────────────────────────────────
    document.getElementById('storage-ts').textContent = 'Last updated: ' + new Date().toLocaleTimeString();
    document.getElementById('storage-error').style.display = 'none';
  }

  function loadStorage() {
    fetch(API_URL, { credentials: 'same-origin' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (data) {
        if (data.error) throw new Error(data.error);
        render(data);
      })
      .catch(function (err) {
        const el = document.getElementById('storage-error');
        if (el) { el.textContent = 'Could not load storage data: ' + err.message; el.style.display = 'block'; }
      });
  }

  (function () {
    loadStorage();
    const btn = document.getElementById('storage-refresh-btn');
    if (btn) btn.addEventListener('click', loadStorage);

    const cleanBtn = document.getElementById('storage-cleanup-btn');
    if (cleanBtn) {
      cleanBtn.addEventListener('click', function () {
        if (!confirm('Delete all orphaned personnel image, QR, and ID card files that have no matching personnel record?')) return;
        cleanBtn.disabled = true;
        cleanBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Cleaning…';
        const csrfEl = document.querySelector('[name=csrfmiddlewaretoken]') ||
                       { value: '' };
        fetch('/users/storage/cleanup-orphans/', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'X-CSRFToken': csrfEl.value || getCookie('csrftoken') },
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.error) { alert('Error: ' + data.error); return; }
          alert('Removed ' + data.removed + ' orphaned file(s).');
          loadStorage();
        })
        .catch(function (e) { alert('Request failed: ' + e.message); })
        .finally(function () {
          cleanBtn.disabled = false;
          cleanBtn.innerHTML = '<i class="fa-solid fa-broom"></i> Clean Orphans';
        });
      });
    }

    function getCookie(name) {
      const v = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
      return v ? v.pop() : '';
    }
  })();
})();
