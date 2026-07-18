// Shared admin clipboard behavior.
//
// Delegated click handling for copy affordances, loaded via ModelAdmin.Media on
// the admins that use them (Post, Asset). Uses data attributes instead of inline
// onclick handlers, which the site's nonce-based CSP blocks — so the copy
// buttons actually work in production.
//
//   <button class="mk-copy-btn" data-clipboard-text="...">Copy</button>
//   <div class="mk-asset-card" data-ref="...">…</div>   (whole card copies data-ref)
(function () {
  if (window.__mkClipboardBound) return;
  window.__mkClipboardBound = true;

  function flash(el, activeText) {
    var orig = el.textContent;
    if (activeText) el.textContent = activeText;
    el.classList.add('mk-copied');
    setTimeout(function () {
      if (activeText) el.textContent = orig;
      el.classList.remove('mk-copied');
    }, 2000);
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-clipboard-text]');
    if (btn) {
      e.preventDefault();
      var text = btn.getAttribute('data-clipboard-text');
      if (text && text !== '-' && navigator.clipboard) {
        navigator.clipboard.writeText(text).then(function () {
          flash(btn, '✓ Copied');
        });
      }
      return;
    }
    var card = e.target.closest('.mk-asset-card[data-ref]');
    if (card && navigator.clipboard) {
      var ref = card.getAttribute('data-ref');
      navigator.clipboard.writeText(ref).then(function () {
        flash(card, null);
      });
    }
  });
})();
