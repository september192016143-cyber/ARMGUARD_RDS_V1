/**
 * hot_key.js — Global keyboard shortcuts for ArmGuard RDS
 * Loaded once on every page via base.html.
 *
 * Alt+N  Navigate to New Transaction (works on every page)
 *
 * Per-page shortcuts (Alt+W / Alt+R) live in transaction_form.js.
 */
(function () {
  var NEW_TXN_URL = document.body.dataset.newTxnUrl || '/transactions/new/';

  // Timestamp debounce — ignores presses within 800 ms of the last one.
  // Using a timestamp (not a flag) means it can never get permanently stuck.
  var _lastNavAt = 0;
  var NAV_COOLDOWN = 800;

  // Single persistent listener — NOT tied to pjaxController.signal.
  // Attaching with a signal caused the listener to be silently removed on
  // every PJAX navigation, making Alt+N stop working if pjax:end missed.
  document.addEventListener('keydown', function (e) {
    if (!e.altKey || e.key.toLowerCase() !== 'n') return;
    e.preventDefault();
    // Already on the target page — nothing to do.
    if (window.location.pathname === NEW_TXN_URL) return;
    var now = Date.now();
    if (now - _lastNavAt < NAV_COOLDOWN) return;
    _lastNavAt = now;
    if (typeof window.pjaxNavigate === 'function') {
      // Pass pushState=true so the browser URL updates to NEW_TXN_URL.
      // Without it the URL stays unchanged and sidebar same-URL guards
      // swallow every subsequent click to the previously-current page.
      window.pjaxNavigate(NEW_TXN_URL, true);
    } else {
      window.location.href = NEW_TXN_URL;
    }
  });
}());
