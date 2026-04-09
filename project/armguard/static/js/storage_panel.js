/* storage_panel.js — Storage Status panel for /users/ (admin only) */
(function () {
  'use strict';

  const API_URL = '/users/storage/';

  function fmt(n) {
    return Number(n).toLocaleString();
  }

  function pctColor(pct) {
    if (pct >= 90) return 'var(--danger)';
    if (pct >= 70) return '#f59e0b';
    return 'var(--success, #22c55e)';
  }

  function recordTable(group, label) {
    const rows = (group && group.rows) ? group.rows : [];
    const total = (group && group.total) ? group.total : '—';
    const avg   = (group && group.avg)   ? group.avg   : '—';
    const count = (group && group.count !== undefined) ? group.count : '—';
    const rowsHtml = rows.length === 0
      ? '<tr><td colspan="2" style="color:var(--muted);padding:.4rem .3rem">No files found.</td></tr>'
      : rows.map(function (r) {
          return '<tr style="border-top:1px solid var(--border,rgba(255,255,255,.07))">' +
            '<td style="padding:.2rem .3rem;color:var(--text);font-size:.75rem;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + r.id + '">' + r.name + '</td>' +
            '<td style="text-align:right;padding:.2rem .3rem;color:var(--primary);font-size:.75rem;white-space:nowrap">' + r.size + '</td>' +
            '</tr>';
        }).join('');
    return '<div>' +
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
    '</div>';
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
    const pr = data.per_record || {};
    const grid = document.getElementById('storage-per-record-grid');
    if (grid) {
      grid.innerHTML =
        recordTable(pr.personnel, 'Personnel') +
        recordTable(pr.pistols,   'Pistols') +
        recordTable(pr.rifles,    'Rifles');
    }

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
