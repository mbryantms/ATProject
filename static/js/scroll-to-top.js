/**
 * Floating scroll-to-top button.
 * Shows when scrolled past threshold, smooth-scrolls to top on click.
 */
(function () {
  const btn = document.querySelector('.scroll-to-top');
  if (!btn) return;

  const THRESHOLD = 400;

  window.addEventListener(
    'scroll',
    function () {
      if (window.scrollY > THRESHOLD) {
        btn.classList.add('visible');
      } else {
        btn.classList.remove('visible');
      }
    },
    { passive: true },
  );

  btn.addEventListener('click', function (e) {
    e.preventDefault();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
})();
