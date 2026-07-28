/* Behavior for the admin picker widgets (engine/admin/widgets.py):
   glyph/icon picker (popover, search, lazy-built Lucide grid, live preview)
   and color picker (hex readout + preset swatches kept in sync).
   Delegated listeners so any number of widgets work without per-widget
   wiring. */
(function () {
  'use strict';

  var LUCIDE_PREFIX = 'lucide:';
  var SVG_NS = 'http://www.w3.org/2000/svg';

  function svgUse(spriteUrl, name) {
    var svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('class', 'lucide-icon');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    svg.setAttribute('aria-hidden', 'true');
    var use = document.createElementNS(SVG_NS, 'use');
    use.setAttribute('href', spriteUrl + '#' + name);
    svg.appendChild(use);
    return svg;
  }

  function updatePreview(picker) {
    var preview = picker.querySelector('.mk-glyph-preview');
    var input = picker.querySelector('.mk-glyph-input');
    if (!preview || !input) return;
    preview.textContent = '';
    var value = input.value.trim();
    if (value.indexOf(LUCIDE_PREFIX) === 0) {
      preview.appendChild(
        svgUse(picker.dataset.spriteUrl, value.slice(LUCIDE_PREFIX.length)),
      );
    } else {
      preview.textContent = value;
    }
  }

  /* The Lucide grid (~1,700 buttons) is built on first open from the
     json_script name list, keeping the initial page light. */
  function buildLucideGrid(picker) {
    var grid = picker.querySelector('[data-lucide-grid]');
    if (!grid || grid.childElementCount > 0) return;
    var script = picker.querySelector('script[type="application/json"]');
    if (!script) return;
    var names;
    try {
      names = JSON.parse(script.textContent);
    } catch {
      return;
    }
    var frag = document.createDocumentFragment();
    names.forEach(function (name) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'mk-glyph-option';
      btn.dataset.glyph = LUCIDE_PREFIX + name;
      btn.title = name;
      btn.appendChild(svgUse(picker.dataset.spriteUrl, name));
      frag.appendChild(btn);
    });
    grid.appendChild(frag);
  }

  function applySearch(panel, query) {
    var q = query.trim().toLowerCase();
    panel.querySelectorAll('.mk-glyph-option').forEach(function (btn) {
      var hay = ((btn.title || '') + ' ' + (btn.dataset.glyph || '')).toLowerCase();
      btn.hidden = q !== '' && hay.indexOf(q) === -1;
    });
    panel.querySelectorAll('.mk-glyph-group').forEach(function (group) {
      group.hidden = !group.querySelector('.mk-glyph-option:not([hidden])');
    });
  }

  function closeAll(except) {
    document.querySelectorAll('.mk-glyph-panel').forEach(function (panel) {
      if (panel === except) return;
      panel.hidden = true;
      var toggle = panel.parentElement.querySelector('.mk-glyph-toggle');
      if (toggle) toggle.setAttribute('aria-expanded', 'false');
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.mk-glyph-picker').forEach(updatePreview);
  });

  document.addEventListener('click', function (e) {
    var toggle = e.target.closest('.mk-glyph-toggle');
    if (toggle) {
      var picker = toggle.closest('.mk-glyph-picker');
      var panel = picker.querySelector('.mk-glyph-panel');
      var willOpen = panel.hidden;
      closeAll();
      if (willOpen) {
        buildLucideGrid(picker);
        panel.hidden = false;
        var search = panel.querySelector('.mk-glyph-search');
        if (search) search.focus();
      }
      toggle.setAttribute('aria-expanded', String(willOpen));
      return;
    }

    var option = e.target.closest('.mk-glyph-option, .mk-glyph-clear');
    if (option) {
      var optPicker = option.closest('.mk-glyph-picker');
      var input = optPicker.querySelector('.mk-glyph-input');
      input.value = option.classList.contains('mk-glyph-clear')
        ? ''
        : option.dataset.glyph || '';
      input.dispatchEvent(new Event('change', { bubbles: true }));
      updatePreview(optPicker);
      closeAll();
      input.focus();
      return;
    }

    var swatch = e.target.closest('.mk-color-swatch');
    if (swatch) {
      var wrap = swatch.closest('.mk-color-picker');
      var colorInput = wrap.querySelector('.mk-color-input');
      var hexInput = wrap.querySelector('.mk-color-hex');
      colorInput.value = swatch.dataset.color;
      if (hexInput) hexInput.value = swatch.dataset.color;
      colorInput.dispatchEvent(new Event('change', { bubbles: true }));
      return;
    }

    if (!e.target.closest('.mk-glyph-picker')) closeAll();
  });

  document.addEventListener('input', function (e) {
    var t = e.target;
    if (t.classList.contains('mk-glyph-search')) {
      applySearch(t.closest('.mk-glyph-panel'), t.value);
    } else if (t.classList.contains('mk-glyph-input')) {
      updatePreview(t.closest('.mk-glyph-picker'));
    } else if (t.classList.contains('mk-color-input')) {
      var hex = t.closest('.mk-color-picker').querySelector('.mk-color-hex');
      if (hex) hex.value = t.value;
    } else if (t.classList.contains('mk-color-hex')) {
      var raw = t.value.trim();
      if (raw && raw[0] !== '#') raw = '#' + raw;
      if (/^#[0-9a-fA-F]{6}$/.test(raw)) {
        var color = t.closest('.mk-color-picker').querySelector('.mk-color-input');
        color.value = raw;
        color.dispatchEvent(new Event('change', { bubbles: true }));
      }
    }
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeAll();
  });
})();
