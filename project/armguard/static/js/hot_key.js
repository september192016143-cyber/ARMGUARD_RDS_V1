/**
 * hot_key.js — Global keyboard shortcuts for ArmGuard RDS
 * Loaded on every page via base.html.
 *
 * Alt+N  Navigate to New Transaction (works on every page)
 *
 * (Per-page shortcuts like Alt+W / Alt+R live in transaction_form.js)
 */
(function () {
  // URL is on <body data-new-txn-url="..."> — always available, never undefined.
  var NEW_TXN_URL = document.body.dataset.newTxnUrl || '/transactions/new/';

  // Guard: ignore rapid repeated presses while navigation is in flight.
  var _navigating = false;

  function navigate() {
    if (_navigating) return;
    _navigating = true;
    if (typeof window.pjaxNavigate === 'function') {
      window.pjaxNavigate(NEW_TXN_URL);
    } else {
      window.location.href = NEW_TXN_URL;
    }
    // Reset the guard once the navigation completes (or after 2 s fallback).
    var reset = function () { _navigating = false; };
    document.addEventListener('pjax:end', reset, { once: true });
    setTimeout(reset, 2000);
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
