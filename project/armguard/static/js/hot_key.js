/**
 * hot_key.js — Global keyboard shortcuts for ArmGuard RDS
 * Loaded on every page via base.html.
 *
 * Alt+N  Navigate to New Transaction (works on every page)
 *
 * (Per-page shortcuts like Alt+W / Alt+R live in transaction_form.js)
 */
(function () {
  var NEW_TXN_URL = document.body.dataset.newTxnUrl || '/transactions/new/';

  // Timestamp debounce: ignore repeated Alt+N within 800 ms.
  // Using a timestamp instead of a boolean flag means it can never get stuck —
  // it resets automatically regardless of whether pjax:end fires.
  var _lastNavAt = 0;
  var NAV_COOLDOWN = 800;

  function navigate() {
    var now = Date.now();
    if (now - _lastNavAt < NAV_COOLDOWN) return;
    _lastNavAt = now;
    if (typeof window.pjaxNavigate === 'function') {
      window.pjaxNavigate(NEW_TXN_URL);
    } else {
      window.location.href = NEW_TXN_URL;
    }
  }

  function handleGlobal(e) {
    if (!e.altKey) return;
    if (e.key.toLowerCase() === 'n') {
      e.preventDefault();
      navigate();
    }
  }

  function attach() {
    document.addEventListener(
      'keydown',
      handleGlobal,
      window.pjaxController
        ? { signal: window.pjaxController.signal }
        : {}
    );
  }

  attach();
  document.addEventListener('pjax:end', attach);
}());
