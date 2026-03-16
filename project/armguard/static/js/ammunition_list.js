(function () {
  var cfg = JSON.parse(document.getElementById('ammo-config').textContent);
  var API = cfg.apiUrl;

  function fmt(n) {
    return Number(n).toLocaleString();
  }

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

