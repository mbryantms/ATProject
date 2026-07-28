/* Behavior for the admin glyph-picker widget (engine/admin/widgets.py).
   Delegated listeners so any number of pickers (including ones added
   dynamically by inlines) work without per-widget wiring. */
(function () {
  'use strict';

  function closeAll(except) {
    document.querySelectorAll('.mk-glyph-panel').forEach(function (panel) {
      if (panel === except) return;
      panel.hidden = true;
      var toggle = panel.parentElement.querySelector('.mk-glyph-toggle');
      if (toggle) toggle.setAttribute('aria-expanded', 'false');
    });
  }

  document.addEventListener('click', function (e) {
    var toggle = e.target.closest('.mk-glyph-toggle');
    if (toggle) {
      var panel = toggle.closest('.mk-glyph-picker').querySelector('.mk-glyph-panel');
      var willOpen = panel.hidden;
      closeAll();
      panel.hidden = !willOpen;
      toggle.setAttribute('aria-expanded', String(willOpen));
      return;
    }

    var option = e.target.closest('.mk-glyph-option, .mk-glyph-clear');
    if (option) {
      var picker = option.closest('.mk-glyph-picker');
      var input = picker.querySelector('input');
      input.value = option.classList.contains('mk-glyph-clear')
        ? ''
        : option.dataset.glyph || '';
      input.dispatchEvent(new Event('change', { bubbles: true }));
      closeAll();
      input.focus();
      return;
    }

    if (!e.target.closest('.mk-glyph-picker')) closeAll();
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeAll();
  });
})();
