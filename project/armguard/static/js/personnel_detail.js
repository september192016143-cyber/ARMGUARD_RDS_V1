/**
 * personnel_detail.js — CSP-safe flip-card interaction for the personnel
 * detail page.  Replaces the CSP-blocked onclick= attribute on #idFlipCard.
 */
(function () {
  'use strict';
  const card = document.getElementById('idFlipCard');
  if (card) card.addEventListener('click', () => card.classList.toggle('flipped'));
}());
