/**
 * hot_key.js — Global keyboard shortcuts for ArmGuard RDS
 * Loaded on every page via base.html.
 *
 * Alt+N  Navigate to New Transaction (works on every page)
 *
 * (Per-page shortcuts like Alt+W / Alt+R live in transaction_form.js)
 */
(function () {
  var scriptEl = document.currentScript ||
    document.querySelector('script[data-new-txn-url]');
  var NEW_TXN_URL = scriptEl ? scriptEl.dataset.newTxnUrl : '/transactions/new/';

  function handleGlobal(e) {
    if (!e.altKey) return;
    var key = e.key.toLowerCase();

    // Alt+N — New Transaction
    if (key === 'n') {
      e.preventDefault();
      if (typeof window.pjaxNavigate === 'function') {
        window.pjaxNavigate(NEW_TXN_URL);
      } else {
        window.location.href = NEW_TXN_URL;
      }
    }
  }

  // Re-attach after every PJAX swap so the signal stays current
  function attach() {
    document.addEventListener(
      'keydown',
      handleGlobal,
      window.pjaxController
        ? { signal: window.pjaxController.signal }
        : {}
    );
  }

  // Initial attach
  attach();

  // Re-attach after each PJAX navigation (pjax:end fires after DOM swap)
  document.addEventListener('pjax:end', attach);
}());
