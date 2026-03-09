/**
 * user_list.js — Delete-confirmation modal for User Management page.
 *
 * Replaces CSP-blocked onclick= handlers on the Delete buttons.
 * Expects:
 *   - #deleteModal, #deleteMsg, #deleteForm
 *   - Delete buttons have data-username and data-delete-url attributes
 *   - Cancel button has id="deleteModalCancel"
 */
(function () {
  'use strict';

  function confirmDelete(username, url) {
    document.getElementById('deleteMsg').textContent =
      'Delete user "' + username + '"? This action cannot be undone.';
    document.getElementById('deleteForm').action = url;
    document.getElementById('deleteModal').style.display = 'flex';
  }

  function closeDelete() {
    document.getElementById('deleteModal').style.display = 'none';
  }

  // Wire all delete buttons (data-username + data-delete-url)
  document.querySelectorAll('[data-username][data-delete-url]').forEach(btn => {
    btn.addEventListener('click', () =>
      confirmDelete(btn.dataset.username, btn.dataset.deleteUrl));
  });

  // Wire cancel button
  const cancelBtn = document.getElementById('deleteModalCancel');
  if (cancelBtn) cancelBtn.addEventListener('click', closeDelete);

  // Close on backdrop click
  const modal = document.getElementById('deleteModal');
  if (modal) {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeDelete();
    });
  }
}());
