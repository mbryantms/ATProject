/**
 * Hide the trailing interpunct on whichever metadata span is visually
 * last on each wrapped flex line in the post-page #page-metadata block.
 *
 * CSS can't detect "last on a wrapped flex line" natively. We mark the
 * relevant spans with `.is-wrap-end`; CSS does the actual hiding via
 * `visibility: hidden` on the ::after pseudo (so the layout box and
 * side-margins stay, nothing shifts).
 *
 * Runs once on ready, re-runs on viewport resize and whenever the
 * metadata block itself changes size (e.g. font-loading reflow).
 */

const CONTAINER_SELECTOR = '#page-metadata .page-metadata-fields';
const ITEM_SELECTOR = ':scope > span';
const MARK = 'is-wrap-end';

function markLineEnds(container) {
  const items = Array.from(container.querySelectorAll(ITEM_SELECTOR));
  items.forEach((el) => el.classList.remove(MARK));
  if (items.length < 2) return;

  for (let i = 0; i < items.length - 1; i++) {
    const here = items[i];
    const next = items[i + 1];
    // Compare top of bounding rects. If the next span sits lower than
    // the current one, the current span is the last visible span on
    // its line and deserves the mark.
    if (next.offsetTop > here.offsetTop) {
      here.classList.add(MARK);
    }
  }
  // The true last span is already covered by the :last-child CSS rule,
  // so don't double-mark it here.
}

function init() {
  const containers = document.querySelectorAll(CONTAINER_SELECTOR);
  if (!containers.length) return;

  const recompute = () => containers.forEach(markLineEnds);
  recompute();

  // Re-run on viewport resize.
  let resizeTimer = null;
  window.addEventListener('resize', () => {
    if (resizeTimer) window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(recompute, 80);
  });

  // Also watch the metadata block itself for size changes that aren't
  // window resizes — e.g. webfont swap, late-loading tooltip content.
  if ('ResizeObserver' in window) {
    const ro = new ResizeObserver(() => recompute());
    containers.forEach((c) => ro.observe(c));
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
