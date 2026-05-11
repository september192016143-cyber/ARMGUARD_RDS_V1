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

// ── Excel import progress ──────────────────────────────────────────────────────
(function () {
  var form        = document.getElementById('form-xlsx');
  var xlsxPanel   = document.getElementById('panel-xlsx');
  var progressPanel = document.getElementById('import-progress-panel');
  if (!form || !progressPanel) return;

  // Elements inside progress panel
  var bar         = document.getElementById('import-bar');
  var lblStatus   = document.getElementById('import-status-label');
  var spinner     = document.getElementById('import-spinner');
  var elCurrent   = document.getElementById('import-current');
  var elTotal     = document.getElementById('import-total');
  var elCreated   = document.getElementById('import-created');
  var elUpdated   = document.getElementById('import-updated');
  var elSkipped   = document.getElementById('import-skipped');
  var skipMsgs    = document.getElementById('import-skip-msgs');
  var skipList    = document.getElementById('import-skip-list');
  var skipMore    = document.getElementById('import-skip-more');
  var doneActions = document.getElementById('import-done-actions');
  var btnAgain    = document.getElementById('import-btn-again');

  function showProgress() {
    xlsxPanel.style.display   = 'none';
    progressPanel.style.display = '';
  }

  function updateBar(current, total) {
    var pct = total > 0 ? Math.round((current / total) * 100) : 0;
    bar.style.width = pct + '%';
    elCurrent.textContent = current;
    elTotal.textContent   = total;
  }

  function updateCounters(created, updated, skipped) {
    elCreated.textContent = created;
    elUpdated.textContent = updated;
    elSkipped.textContent = skipped;
  }

  function showDone(evt) {
    spinner.style.display = 'none';
    lblStatus.textContent = 'Import complete';

    // Final bar at 100%
    bar.style.width       = '100%';
    bar.style.background  = evt.created > 0 || evt.updated > 0
      ? 'var(--green,#22c55e)'
      : 'var(--yellow,#eab308)';

    // Skipped messages
    if (evt.skipped_msgs && evt.skipped_msgs.length > 0) {
      skipList.innerHTML = '';
      evt.skipped_msgs.forEach(function (msg) {
        var li = document.createElement('li');
        li.textContent = msg;
        skipList.appendChild(li);
      });
      if (evt.skipped_extra > 0) {
        skipMore.style.display = '';
        skipMore.textContent   = '…and ' + evt.skipped_extra + ' more skipped row(s).';
      }
      skipMsgs.style.display = '';
    }

    // Show done action buttons
    doneActions.style.display = 'flex';
  }

  function showError(msg) {
    spinner.style.display = 'none';
    lblStatus.textContent = 'Error: ' + msg;
    bar.style.background  = 'var(--red,#ef4444)';
    bar.style.width       = '100%';
    doneActions.style.display = 'flex';
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    showProgress();

    var formData = new FormData(form);

    fetch(form.action, {
      method: 'POST',
      body: formData,
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    }).then(function (response) {
      if (!response.ok) {
        showError('Server returned ' + response.status);
        return;
      }
      var reader  = response.body.getReader();
      var decoder = new TextDecoder();
      var buffer  = '';

      function processChunk(value) {
        buffer += decoder.decode(value || new Uint8Array(), { stream: !!value });
        var parts = buffer.split('\n\n');
        buffer = parts.pop(); // keep incomplete tail

        parts.forEach(function (part) {
          part = part.trim();
          if (!part.startsWith('data:')) return;
          var jsonStr = part.slice(5).trim();
          try {
            var evt = JSON.parse(jsonStr);
            if (evt.error) {
              showError(evt.error);
              return;
            }
            updateBar(evt.current || 0, evt.total || 0);
            updateCounters(evt.created || 0, evt.updated || 0, evt.skipped || 0);
            if (evt.done) {
              showDone(evt);
            }
          } catch (_) {}
        });
      }

      function pump() {
        reader.read().then(function (result) {
          processChunk(result.value);
          if (!result.done) {
            pump();
          }
        }).catch(function (err) {
          showError('Stream error: ' + err.message);
        });
      }
      pump();

    }).catch(function (err) {
      showError('Network error: ' + err.message);
    });
  });

  // "Import Another" resets the page
  if (btnAgain) {
    btnAgain.addEventListener('click', function () {
      progressPanel.style.display = 'none';
      // Reset the form
      form.reset();
      xlsxPanel.style.display = '';
      // Reset progress UI for next use
      bar.style.width       = '0%';
      bar.style.background  = 'var(--primary,#c9952b)';
      lblStatus.textContent = 'Importing…';
      spinner.style.display = '';
      elCurrent.textContent = '0';
      elTotal.textContent   = '0';
      elCreated.textContent = '0';
      elUpdated.textContent = '0';
      elSkipped.textContent = '0';
      skipMsgs.style.display    = 'none';
      skipList.innerHTML        = '';
      skipMore.style.display    = 'none';
      doneActions.style.display = 'none';
    });
  }
}());
