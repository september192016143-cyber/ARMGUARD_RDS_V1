/**
 * personnel_detail.js — CSP-safe flip-card interaction for the personnel
 * detail page.  Replaces the CSP-blocked onclick= attribute on #idFlipCard.
 */
(function () {
  'use strict';
  function init() {
    const card = document.getElementById('idFlipCard');
    if (card) card.addEventListener('click', function () {
      card.classList.toggle('flipped');
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
}());
