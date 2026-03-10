(function () {
  var cfg = JSON.parse(document.getElementById('ammo-config').textContent);
  var API = cfg.apiUrl;

  function refresh() {
    fetch(API).then(function (r) { return r.json(); }).then(function (data) {
      data.items.forEach(function (item) {
        var row = document.querySelector('tr[data-ammo-pk="' + item.pk + '"]');
        if (!row) return;
        var issuedEl = row.querySelector('.ammo-issued');
        if (issuedEl) {
          issuedEl.textContent = item.issued;
          issuedEl.style.color = item.issued > 0 ? '#f0a030' : 'var(--muted)';
        }
        var onHandEl = row.querySelector('.ammo-onhand');
        if (onHandEl) {
          onHandEl.textContent = item.on_hand;
          onHandEl.style.color = item.on_hand === 0 ? 'var(--red)' : '#3cb83c';
        }
      });
    }).catch(function () {});
  }

  setInterval(refresh, 10000);
})();
