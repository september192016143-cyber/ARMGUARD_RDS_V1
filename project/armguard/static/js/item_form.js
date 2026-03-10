(function () {
  var cfgEl = document.getElementById('item-form-config');
  if (!cfgEl) return;
  var cfg = JSON.parse(cfgEl.textContent);
  var itemType = cfg.itemType;

  /* ── Rifle-specific: M4 model toggle + QR auto-fill ─────────── */
  if (itemType === 'rifle') {
    var modelSel    = document.getElementById(cfg.modelFieldId);
    var qrGroup     = document.getElementById('factory-qr-group');
    var qrInput     = document.getElementById(cfg.factoryQrFieldId);
    var serialInput = document.getElementById(cfg.serialFieldId);
    var descInput   = document.getElementById(cfg.descFieldId);
    var serialHint  = document.getElementById('serial-hint');
    var M4 = 'M4 Carbine DSAR-15 5.56mm';

    function toggle() {
      var isM4 = modelSel.value === M4;
      qrGroup.style.display = isM4 ? '' : 'none';
      if (serialHint) serialHint.style.display = isM4 ? '' : 'none';
    }

    if (modelSel) {
      modelSel.addEventListener('change', toggle);
      toggle();
    }

    function autofillFromQR() {
      var qr = qrInput.value.trim();
      if (!qr) return;
      var match = qr.match(/PAF\d{8}/);
      if (match) {
        var serial = match[0];
        var idx    = qr.indexOf(serial);
        var before = qr.slice(0, idx);
        var after  = qr.slice(idx + serial.length);
        if (serialInput && !serialInput.value) serialInput.value = serial;
        if (descInput   && !descInput.value)   descInput.value   = (before + after).trim();
      }
    }

    if (qrInput) {
      qrInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { e.preventDefault(); autofillFromQR(); }
      });
      qrInput.addEventListener('change', autofillFromQR);
    }
  }

  /* ── Pistol + Rifle: Serial image crop modal ─────────────────── */
  if (itemType === 'pistol' || itemType === 'rifle') {
    var fileInput   = document.getElementById(cfg.serialImageFieldId);
    var overlay     = document.getElementById('serial-crop-modal-overlay');
    var canvas      = document.getElementById('serial-crop-canvas');
    if (!fileInput || !overlay || !canvas) return;
    var ctx         = canvas.getContext('2d');
    var applyBtn    = document.getElementById('serial-crop-apply');
    var cancelBtn   = document.getElementById('serial-crop-cancel');
    var confirmBtn  = document.getElementById('serial-crop-confirm');
    var recropModal = document.getElementById('serial-crop-recrop');
    var previewRow  = document.getElementById('serial-crop-preview-row');
    var previewImg  = document.getElementById('serial-crop-thumb');
    var recropBtn   = document.getElementById('serial-recrop-btn');
    var enhPanel    = document.getElementById('enhance-panel');
    var prevBanner  = document.getElementById('crop-preview-banner');
    var zoomInBtn   = document.getElementById('zoom-in-btn');
    var zoomOutBtn  = document.getElementById('zoom-out-btn');
    var zoomRstBtn  = document.getElementById('zoom-reset-btn');
    var zoomLevelEl = document.getElementById('zoom-level');
    var enhBrightness = document.getElementById('enh-brightness');
    var enhContrast   = document.getElementById('enh-contrast');
    var enhSaturation = document.getElementById('enh-saturation');
    var enhSharpness  = document.getElementById('enh-sharpness');
    var enhResetBtn   = document.getElementById('enhance-reset');

    var HS = 7;
    var img = new Image();
    var viewZoom = 1;
    var viewPan  = {x: 0, y: 0};
    var sel  = null;
    var drag = null;
    var originalFile  = null;
    var hasCropped    = false;
    var previewMode   = false;
    var croppedCanvas = null;

    function visW() { return img.naturalWidth  / viewZoom; }
    function visH() { return img.naturalHeight / viewZoom; }

    function c2i(cx, cy) {
      return { x: cx / canvas.width  * visW() + viewPan.x,
               y: cy / canvas.height * visH() + viewPan.y };
    }
    function i2c(ix, iy) {
      return { x: (ix - viewPan.x) / visW() * canvas.width,
               y: (iy - viewPan.y) / visH() * canvas.height };
    }

    function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

    function clampPan() {
      viewPan.x = clamp(viewPan.x, 0, img.naturalWidth  - visW());
      viewPan.y = clamp(viewPan.y, 0, img.naturalHeight - visH());
    }

    function normSel(s) {
      return { x: s.w >= 0 ? s.x : s.x + s.w, y: s.h >= 0 ? s.y : s.y + s.h,
               w: Math.abs(s.w), h: Math.abs(s.h) };
    }

    function selCanvas() {
      if (!sel) return null;
      var s = normSel(sel);
      var tl = i2c(s.x, s.y);
      var br = i2c(s.x + s.w, s.y + s.h);
      return {x: tl.x, y: tl.y, w: br.x - tl.x, h: br.y - tl.y};
    }

    function getHandles(x, y, w, h) {
      return [{id:'nw',x:x,y:y},{id:'n',x:x+w/2,y:y},{id:'ne',x:x+w,y:y},
              {id:'w',x:x,y:y+h/2},                   {id:'e',x:x+w,y:y+h/2},
              {id:'sw',x:x,y:y+h},{id:'s',x:x+w/2,y:y+h},{id:'se',x:x+w,y:y+h}];
    }

    function hitHandle(mx, my) {
      var sc = selCanvas(); if (!sc) return null;
      for (var i = 0; i < (function () { return getHandles(sc.x, sc.y, sc.w, sc.h); })().length; i++) {
        var hp = getHandles(sc.x, sc.y, sc.w, sc.h)[i];
        if (Math.abs(mx - hp.x) <= HS + 2 && Math.abs(my - hp.y) <= HS + 2) return hp.id;
      }
      return null;
    }

    function insideSel(mx, my) {
      var sc = selCanvas(); if (!sc) return false;
      return mx > sc.x && mx < sc.x + sc.w && my > sc.y && my < sc.y + sc.h;
    }

    function getPos(e) {
      var r  = canvas.getBoundingClientRect();
      var sx = canvas.width  / r.width;
      var sy = canvas.height / r.height;
      var src = e.touches ? e.touches[0] : e;
      return {x: (src.clientX - r.left) * sx, y: (src.clientY - r.top) * sy};
    }

    function setCursor(id) {
      var map = {nw:'nw-resize',n:'n-resize',ne:'ne-resize',w:'w-resize',
                 e:'e-resize',sw:'sw-resize',s:'s-resize',se:'se-resize',
                 move:'move',pan:'grab',draw:'crosshair'};
      canvas.style.cursor = map[id] || 'crosshair';
    }

    function getFilter() {
      return 'brightness(' + enhBrightness.value + '%) contrast(' + enhContrast.value + '%) saturate(' + enhSaturation.value + '%)';
    }
    function updateEnhLabels() {
      document.getElementById('enh-brightness-val').textContent = enhBrightness.value + '%';
      document.getElementById('enh-contrast-val').textContent   = enhContrast.value + '%';
      document.getElementById('enh-saturation-val').textContent = enhSaturation.value + '%';
      document.getElementById('enh-sharpness-val').textContent  = enhSharpness.value;
    }
    [enhBrightness, enhContrast, enhSaturation, enhSharpness].forEach(function (sl) {
      sl.addEventListener('input', function () { updateEnhLabels(); draw(); });
    });
    enhResetBtn.addEventListener('click', function () {
      enhBrightness.value = 100; enhContrast.value = 100;
      enhSaturation.value = 100; enhSharpness.value = 0;
      updateEnhLabels(); draw();
    });

    function applySharpness(srcCanvas, level) {
      if (level <= 0) return srcCanvas;
      var w = srcCanvas.width, h = srcCanvas.height;
      var tmp = document.createElement('canvas'); tmp.width = w; tmp.height = h;
      var tc = tmp.getContext('2d', {willReadFrequently: true});
      var amount = level * 0.4;
      tc.filter = 'none'; tc.drawImage(srcCanvas, 0, 0);
      var bd = tc.getImageData(0, 0, w, h).data;
      tc.clearRect(0, 0, w, h);
      tc.filter = 'blur(' + (1 + level * 0.3) + 'px)'; tc.drawImage(srcCanvas, 0, 0);
      var blur = tc.getImageData(0, 0, w, h).data;
      var out = tc.createImageData(w, h); var od = out.data;
      for (var i = 0; i < bd.length; i += 4) {
        od[i  ] = clamp(bd[i  ] + amount * (bd[i  ] - blur[i  ]), 0, 255);
        od[i+1] = clamp(bd[i+1] + amount * (bd[i+1] - blur[i+1]), 0, 255);
        od[i+2] = clamp(bd[i+2] + amount * (bd[i+2] - blur[i+2]), 0, 255);
        od[i+3] = bd[i+3];
      }
      tc.putImageData(out, 0, 0); return tmp;
    }

    function updateZoomUI() {
      zoomLevelEl.textContent = viewZoom.toFixed(1) + '×';
      zoomOutBtn.disabled = viewZoom <= 1.01;
      zoomInBtn.disabled  = viewZoom >= 8;
    }

    function zoomAt(cx, cy, factor) {
      var before = c2i(cx, cy);
      viewZoom = clamp(viewZoom * factor, 1, 8);
      viewPan.x = before.x - cx / canvas.width  * visW();
      viewPan.y = before.y - cy / canvas.height * visH();
      clampPan(); updateZoomUI(); draw();
    }

    canvas.addEventListener('wheel', function (e) {
      e.preventDefault();
      var cp = getPos(e);
      zoomAt(cp.x, cp.y, e.deltaY < 0 ? 1.2 : 1 / 1.2);
    }, {passive: false});

    zoomInBtn.addEventListener ('click', function () { zoomAt(canvas.width / 2, canvas.height / 2, 1.5); });
    zoomOutBtn.addEventListener('click', function () { zoomAt(canvas.width / 2, canvas.height / 2, 1 / 1.5); });
    zoomRstBtn.addEventListener('click', function () { viewZoom = 1; viewPan = {x:0, y:0}; updateZoomUI(); draw(); });

    function draw() {
      var cw = canvas.width, ch = canvas.height;
      ctx.clearRect(0, 0, cw, ch);
      ctx.filter = getFilter();
      ctx.drawImage(img, viewPan.x, viewPan.y, visW(), visH(), 0, 0, cw, ch);
      ctx.filter = 'none';

      var sc = selCanvas();
      if (!sc || sc.w < 2 || sc.h < 2) return;
      var x = sc.x, y = sc.y, w = sc.w, h = sc.h;
      var ns = normSel(sel);

      ctx.fillStyle = 'rgba(0,0,0,.55)';
      ctx.fillRect(0, 0, cw, ch);
      ctx.save();
      ctx.globalCompositeOperation = 'destination-out';
      ctx.fillRect(x, y, w, h);
      ctx.restore();
      ctx.filter = getFilter();
      ctx.drawImage(img, ns.x, ns.y, ns.w, ns.h, x, y, w, h);
      ctx.filter = 'none';
      ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5;
      ctx.strokeRect(x + .5, y + .5, w - 1, h - 1);
      ctx.strokeStyle = 'rgba(255,255,255,.3)'; ctx.lineWidth = .7;
      [1, 2].forEach(function (i) {
        ctx.beginPath(); ctx.moveTo(x + w * i / 3, y); ctx.lineTo(x + w * i / 3, y + h); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(x, y + h * i / 3); ctx.lineTo(x + w, y + h * i / 3); ctx.stroke();
      });
      getHandles(x, y, w, h).forEach(function (hp) {
        ctx.fillStyle = '#fff'; ctx.strokeStyle = '#333'; ctx.lineWidth = 1;
        ctx.fillRect(hp.x - HS, hp.y - HS, HS * 2, HS * 2);
        ctx.strokeRect(hp.x - HS, hp.y - HS, HS * 2, HS * 2);
      });
    }

    canvas.addEventListener('pointerdown', function (e) {
      if (previewMode) return;
      e.preventDefault(); canvas.setPointerCapture(e.pointerId);
      var cp = getPos(e), ip = c2i(cp.x, cp.y);
      var handle = hitHandle(cp.x, cp.y);
      if (handle) {
        drag = {mode:'resize', handle:handle, oImg:ip, origSel: Object.assign({}, normSel(sel))}; setCursor(handle);
      } else if (insideSel(cp.x, cp.y)) {
        drag = {mode:'move', oImg:ip, origSel: Object.assign({}, normSel(sel))}; setCursor('move');
      } else if (e.buttons === 4 || e.altKey) {
        drag = {mode:'pan', oImg:ip}; setCursor('pan');
      } else {
        drag = {mode:'draw', oImg:ip};
        sel = {x:ip.x, y:ip.y, w:0, h:0}; setCursor('draw');
      }
    });

    canvas.addEventListener('pointermove', function (e) {
      if (previewMode) return;
      e.preventDefault();
      var cp = getPos(e), ip = c2i(cp.x, cp.y);
      if (!drag) {
        var h = hitHandle(cp.x, cp.y);
        setCursor(h || (insideSel(cp.x, cp.y) ? 'move' : 'draw')); return;
      }
      var dx = ip.x - drag.oImg.x, dy = ip.y - drag.oImg.y;
      var IW = img.naturalWidth, IH = img.naturalHeight;
      if (drag.mode === 'draw') {
        sel = {x:drag.oImg.x, y:drag.oImg.y,
               w:clamp(ip.x, 0, IW) - drag.oImg.x,
               h:clamp(ip.y, 0, IH) - drag.oImg.y};
      } else if (drag.mode === 'move') {
        var o = drag.origSel;
        sel = {x:clamp(o.x + dx, 0, IW - o.w), y:clamp(o.y + dy, 0, IH - o.h), w:o.w, h:o.h};
      } else if (drag.mode === 'resize') {
        var o2 = drag.origSel, id = drag.handle;
        var rx = o2.x, ry = o2.y, rw = o2.w, rh = o2.h;
        if (id.indexOf('e') !== -1) rw = Math.max(2, o2.w + dx);
        if (id.indexOf('s') !== -1) rh = Math.max(2, o2.h + dy);
        if (id.indexOf('w') !== -1) { var nw = Math.max(2, o2.w - dx); rx = o2.x + o2.w - nw; rw = nw; }
        if (id.indexOf('n') !== -1) { var nh = Math.max(2, o2.h - dy); ry = o2.y + o2.h - nh; rh = nh; }
        sel = {x:clamp(rx, 0, IW), y:clamp(ry, 0, IH), w:rw, h:rh};
      } else if (drag.mode === 'pan') {
        viewPan.x -= dx; viewPan.y -= dy; clampPan();
      }
      draw();
    });

    canvas.addEventListener('pointerup', function (e) {
      if (previewMode) return;
      e.preventDefault(); drag = null;
      if (sel) { sel = normSel(sel); if (sel.w < 2 || sel.h < 2) sel = null; }
      draw(); setCursor('draw');
    });

    function openCropModal(file) {
      overlay.style.display = 'flex';
      sel = null; drag = null; viewZoom = 1; viewPan = {x:0, y:0};
      exitPreviewMode();
      enhBrightness.value = 100; enhContrast.value = 100;
      enhSaturation.value = 100; enhSharpness.value = 0;
      updateEnhLabels(); updateZoomUI();
      var url = URL.createObjectURL(file);
      img.onload = function () {
        URL.revokeObjectURL(url);
        var wrap = document.getElementById('serial-crop-wrap');
        var maxW = wrap.clientWidth || 680;
        var maxH = Math.round(window.innerHeight * 0.55);
        var cw = maxW, ch = Math.round(img.naturalHeight * maxW / img.naturalWidth);
        if (ch > maxH) { ch = maxH; cw = Math.round(img.naturalWidth * maxH / img.naturalHeight); }
        canvas.width = cw; canvas.height = ch;
        draw();
      };
      img.src = url;
    }

    fileInput.addEventListener('change', function () {
      var file = fileInput.files[0]; if (!file) return;
      originalFile = file; hasCropped = false; openCropModal(file);
    });

    if (recropBtn) recropBtn.addEventListener('click', function () {
      if (originalFile) { hasCropped = false; openCropModal(originalFile); }
    });

    applyBtn.addEventListener('click', function () {
      var s = sel ? normSel(sel) : null;
      if (!s || s.w < 2 || s.h < 2) { alert('Draw a crop area first.'); return; }
      var full = document.createElement('canvas');
      full.width = img.naturalWidth; full.height = img.naturalHeight;
      var fc = full.getContext('2d');
      fc.filter = getFilter(); fc.drawImage(img, 0, 0); fc.filter = 'none';
      var sharpened = applySharpness(full, parseInt(enhSharpness.value));
      var out = document.createElement('canvas');
      out.width = Math.round(s.w); out.height = Math.round(s.h);
      out.getContext('2d').drawImage(sharpened, s.x, s.y, s.w, s.h, 0, 0, s.w, s.h);
      // Show the enlarged cropped result for review before saving
      croppedCanvas = out;
      previewMode = true;
      drawPreview(out);
      applyBtn.style.display    = 'none';
      confirmBtn.style.display  = '';
      recropModal.style.display = '';
      enhPanel.style.display    = 'none';
      prevBanner.style.display  = '';
      canvas.style.cursor       = 'default';
    });

    confirmBtn.addEventListener('click', function () {
      if (!croppedCanvas) return;
      croppedCanvas.toBlob(function (blob) {
        var fname = (originalFile ? originalFile.name.replace(/\.[^.]+$/, '') : 'serial') + '_cropped.jpg';
        var f = new File([blob], fname, {type: 'image/jpeg'});
        var dt = new DataTransfer(); dt.items.add(f); fileInput.files = dt.files;
        var pu = URL.createObjectURL(f);
        previewImg.onload = function () { URL.revokeObjectURL(pu); };
        previewImg.src = pu;
        previewRow.style.display = 'flex';
        hasCropped = true;
        exitPreviewMode();
        closeModal();
      }, 'image/jpeg', 0.93);
    });

    recropModal.addEventListener('click', function () {
      exitPreviewMode();
      draw();
    });

    cancelBtn.addEventListener('click', function () {
      exitPreviewMode();
      closeModal();
      if (!hasCropped) { fileInput.value = ''; previewRow.style.display = 'none'; originalFile = null; }
    });
    overlay.addEventListener('click', function (e) { if (e.target === overlay) cancelBtn.click(); });
    function closeModal() { overlay.style.display = 'none'; }

    function exitPreviewMode() {
      previewMode   = false;
      croppedCanvas = null;
      applyBtn.style.display    = '';
      confirmBtn.style.display  = 'none';
      recropModal.style.display = 'none';
      enhPanel.style.display    = '';
      prevBanner.style.display  = 'none';
      canvas.style.cursor       = 'crosshair';
    }

    function drawPreview(cropped) {
      var cw = canvas.width, ch = canvas.height;
      ctx.clearRect(0, 0, cw, ch);
      ctx.fillStyle = '#0d0f17';
      ctx.fillRect(0, 0, cw, ch);
      var scale = Math.min(cw / cropped.width, ch / cropped.height) * 0.94;
      var dw = Math.round(cropped.width  * scale);
      var dh = Math.round(cropped.height * scale);
      var dx = Math.round((cw - dw) / 2);
      var dy = Math.round((ch - dh) / 2);
      ctx.drawImage(cropped, dx, dy, dw, dh);
      ctx.strokeStyle = 'rgba(201,149,43,0.75)';
      ctx.lineWidth   = 2;
      ctx.strokeRect(dx, dy, dw, dh);
    }
  }
})();
