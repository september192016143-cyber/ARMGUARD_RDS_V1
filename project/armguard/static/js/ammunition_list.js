(function () {
  var cfg = JSON.parse(document.getElementById('ammo-config').textContent);
  var API = cfg.apiUrl;
  var LOTS = {};
  var lotsEl = document.getElementById('lots-by-type');
  if (lotsEl) { try { LOTS = JSON.parse(lotsEl.textContent); } catch(e) {} }

  function fmt(n) {
    return Number(n).toLocaleString();
  }

  // ---- Lot drill-down modal ------------------------------------------------
  var modal = document.getElementById('ammo-lot-modal');

  document.querySelectorAll('.ammo-drill').forEach(function (el) {
    el.addEventListener('click', function () {
      var type = this.dataset.type;
      document.getElementById('ammo-lot-title').textContent = type;
      var tbody = document.getElementById('ammo-lot-tbody');
      tbody.innerHTML = '';
      var lots = LOTS[type] || [];
      lots.forEach(function (l, i) {
        var tr = document.createElement('tr');
        tr.style.background = i % 2 ? 'rgba(12,166,120,.06)' : '';
        tr.innerHTML =
          '<td style="padding:.4rem .65rem;font-weight:600">' + l.lot + '</td>' +
          '<td style="padding:.4rem .65rem;text-align:center">' + fmt(l.possessed) + '</td>' +
          '<td style="padding:.4rem .65rem;text-align:center;color:var(--green)">' + fmt(l.on_stock) + '</td>' +
          '<td style="padding:.4rem .65rem;text-align:center;' + (l.issued_par > 0 ? 'color:var(--primary);font-weight:700' : 'color:var(--muted)') + '">' + fmt(l.issued_par) + '</td>' +
          '<td style="padding:.4rem .65rem;text-align:center;' + (l.issued_tr > 0 ? 'color:var(--primary);font-weight:700' : 'color:var(--muted)') + '">' + fmt(l.issued_tr) + '</td>';
        tbody.appendChild(tr);
      });
      modal.style.display = 'flex';
    });
  });

  if (modal) {
    modal.addEventListener('click', function (e) {
      if (e.target === this) this.style.display = 'none';
    });
  }
  var closeBtn = document.getElementById('ammo-lot-close');
  if (closeBtn) {
    closeBtn.addEventListener('click', function () { modal.style.display = 'none'; });
  }

  // ---- Real-time polling ---------------------------------------------------
  function refresh() {
    fetch(API).then(function (r) { return r.json(); }).then(function (data) {
      data.items.forEach(function (item) {
        var row = document.querySelector('tr[data-ammo-type="' + item.type + '"]');
        if (!row) return;

        var possessedEl = row.querySelector('.ammo-possessed');
        if (possessedEl) possessedEl.textContent = fmt(item.possessed);

        var onStockEl = row.querySelector('.ammo-on-stock');
        if (onStockEl) {
          onStockEl.textContent = fmt(item.on_stock);
          onStockEl.style.color = item.on_stock === 0 ? 'var(--red)' : 'var(--green)';
        }

        var parEl = row.querySelector('.ammo-par');
        if (parEl) {
          parEl.textContent = fmt(item.issued_par);
          parEl.style.color = item.issued_par > 0 ? 'var(--primary)' : 'var(--muted)';
          parEl.style.fontWeight = item.issued_par > 0 ? '700' : '';
        }

        var trEl = row.querySelector('.ammo-tr');
        if (trEl) {
          trEl.textContent = fmt(item.issued_tr);
          trEl.style.color = item.issued_tr > 0 ? 'var(--primary)' : 'var(--muted)';
          trEl.style.fontWeight = item.issued_tr > 0 ? '700' : '';
        }

        var svcEl = row.querySelector('.ammo-serviceable');
        if (svcEl) {
          svcEl.textContent = fmt(item.on_stock);
          svcEl.style.color = item.on_stock === 0 ? 'var(--red)' : 'var(--green)';
        }
      });
    }).catch(function () {});
  }

  setInterval(refresh, 10000);
})();

