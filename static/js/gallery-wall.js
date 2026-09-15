/*  Justified rows for gallery walls (::: {.gallery .wall}).
 *
 *  gallery_enhancer.py stamps each tile with --ar (width / height) and the
 *  block with data-row-height. This packs tiles into rows whose height is close to
 *  the target and whose width fills the container exactly, then pins each
 *  figure's width and its .image-wrapper's height. Grid and strip layouts
 *  need nothing from JS. Re-runs when the container's width changes.
 */
(function () {
  'use strict';

  const GAP = 8;
  const PRESETS = { short: 150, medium: 210, tall: 300 };
  const PHONE_SCALE = 0.7;

  function targetHeight(gallery, width, count) {
    const rows = gallery.dataset.rowHeight || 'auto';
    const phone = width < 650;
    const scale = phone ? PHONE_SCALE : 1;
    if (/^\d+$/.test(rows)) return Math.round(parseInt(rows, 10) * scale);
    if (PRESETS[rows]) return Math.round(PRESETS[rows] * scale);
    // auto: taller rows for small galleries, shorter for big ones, within a
    // band so a two-image wall never becomes a pair of billboards and a
    // thirty-image wall never becomes thumbnails.
    const min = phone ? 110 : 140;
    const max = Math.round(width * 0.45);
    return Math.round(Math.min(max, Math.max(min, (width * 0.8) / Math.sqrt(count))));
  }

  function ratioOf(tile) {
    const inline = parseFloat(tile.style.getPropertyValue('--ar'));
    if (inline > 0) return inline;
    const img = tile.querySelector('img');
    const w = img && parseFloat(img.getAttribute('width'));
    const h = img && parseFloat(img.getAttribute('height'));
    return w > 0 && h > 0 ? w / h : 1.5;
  }

  function layout(gallery) {
    const items = gallery.querySelector('.gallery-items');
    if (!items) return;
    const tiles = Array.from(items.children).filter(
      (el) => el.matches && el.matches('figure.gallery-item'),
    );
    const width = items.clientWidth;
    if (!width || tiles.length === 0) return;

    const target = targetHeight(gallery, width, tiles.length);
    let row = [];
    let sum = 0;

    const flush = (last) => {
      const gaps = GAP * (row.length - 1);
      let height = (width - gaps) / sum;
      // A short final row shouldn't balloon to fill the width.
      if (last && height > target * 1.25) height = target * 1.25;
      const h = Math.round(height);
      row.forEach(({ tile, ar }) => {
        tile.style.width = `${Math.floor(ar * height)}px`;
        const wrap = tile.querySelector('.image-wrapper');
        if (wrap) wrap.style.height = `${h}px`;
      });
      row = [];
      sum = 0;
    };

    tiles.forEach((tile, i) => {
      const ar = ratioOf(tile);
      row.push({ tile, ar });
      sum += ar;
      if (sum * target + GAP * (row.length - 1) >= width) flush(false);
      if (i === tiles.length - 1 && row.length) flush(true);
    });

    gallery.classList.add('is-justified');
  }

  function init() {
    const walls = document.querySelectorAll('.markdownBody .gallery.wall');
    if (walls.length === 0) return;
    walls.forEach(layout);

    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', () => walls.forEach(layout));
      return;
    }
    const observer = new ResizeObserver((entries) => {
      entries.forEach((entry) => {
        const gallery = entry.target.closest('.gallery');
        if (gallery) layout(gallery);
      });
    });
    walls.forEach((gallery) => {
      const items = gallery.querySelector('.gallery-items');
      if (items) observer.observe(items);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
