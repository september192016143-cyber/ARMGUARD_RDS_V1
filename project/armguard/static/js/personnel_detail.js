/**
 * personnel_detail.js — CSP-safe flip-card interaction for the personnel
 * detail page.  Replaces the CSP-blocked onclick= attribute on #idFlipCard.
 *
 * Uses direct inline-style manipulation on .flip-card-inner so the transform
 * cannot be overridden by any stylesheet rule (highest CSS specificity).
 */
(function () {
  'use strict';
  var card = document.getElementById('idFlipCard');
  if (!card) return;
  var inner = card.querySelector('.flip-card-inner');
  if (!inner) return;
  var flipped = false;
  card.addEventListener('click', function () {
    flipped = !flipped;
    var t = flipped ? 'rotateY(180deg)' : 'rotateY(0deg)';
    inner.style.webkitTransform = t;
    inner.style.transform = t;
  });
}());
