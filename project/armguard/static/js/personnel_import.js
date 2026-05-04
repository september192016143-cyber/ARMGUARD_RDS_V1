'use strict';

function switchTab(tab) {
  var tabs = ['xlsx', 'gsheet'];
  tabs.forEach(function (t) {
    var btn   = document.getElementById('tab-' + t);
    var panel = document.getElementById('panel-' + t);
    if (!btn || !panel) return;
    var active = (t === tab);
    btn.style.color             = active ? 'var(--primary,#c9952b)' : 'var(--muted)';
    btn.style.borderBottomColor = active ? 'var(--primary,#c9952b)' : 'transparent';
    panel.style.display         = active ? '' : 'none';
  });
}
