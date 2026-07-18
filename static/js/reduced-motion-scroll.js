// Respect prefers-reduced-motion for programmatic smooth scrolls.
//
// The CSS `scroll-behavior: smooth` rule is already gated behind the
// prefers-reduced-motion media query, but explicit `{ behavior: 'smooth' }`
// calls in JavaScript (TOC/anchor navigation, scroll-to-top, search, citation
// jumps, image focus) override that gate. This module patches the native
// scroll APIs once to downgrade those calls to instant scrolls when the user
// has asked for reduced motion — no change for everyone else.
(function () {
  if (window.__rmScrollPatched) return;
  window.__rmScrollPatched = true;

  const prefersReduced = () =>
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const sanitize = (options) => {
    if (
      options &&
      typeof options === 'object' &&
      options.behavior === 'smooth' &&
      prefersReduced()
    ) {
      return Object.assign({}, options, { behavior: 'auto' });
    }
    return options;
  };

  const patchWindowMethod = (name) => {
    const original = window[name];
    if (typeof original !== 'function') return;
    window[name] = function (x, y) {
      if (typeof x === 'object') return original.call(window, sanitize(x));
      return original.call(window, x, y);
    };
  };

  patchWindowMethod('scrollTo');
  patchWindowMethod('scroll');

  const originalScrollIntoView = Element.prototype.scrollIntoView;
  Element.prototype.scrollIntoView = function (arg) {
    if (typeof arg === 'object') {
      return originalScrollIntoView.call(this, sanitize(arg));
    }
    return originalScrollIntoView.call(this, arg);
  };
})();
