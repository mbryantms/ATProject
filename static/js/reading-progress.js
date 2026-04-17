// Reading progress + active-heading breadcrumb widget.
//
// Mounts on individual post pages (any page that renders a .markdownBody
// container with at least two H2 headings). Bails out silently otherwise so
// nothing needs to know about post-vs-archive routing.
//
// Active heading derivation walks the section ancestor chain produced by
// engine/markdown/filters/heading_sectionizer.lua — `<section class="block
// levelN">` wraps each heading. If that filter ever flattens nesting, the
// breadcrumb derivation here has to change.

(function () {
  const ready = (fn) =>
    document.readyState !== 'loading'
      ? fn()
      : document.addEventListener('DOMContentLoaded', fn);

  ready(() => {
    // Article body — target by id, not .markdownBody, since the page-metadata
    // block also uses that class and appears earlier in the DOM.
    const body = document.getElementById('markdownBody');
    if (!body) return;

    const articleH1 = document.querySelector('article > header > h1');
    if (!articleH1) return;

    const headings = Array.from(body.querySelectorAll('h2[id], h3[id], h4[id]'));
    const h2Count = headings.filter((h) => h.tagName === 'H2').length;
    if (h2Count < 2) return; // Single-section post — widget adds nothing.

    const postTitle = articleH1.textContent.trim();

    // Build widget DOM
    const widget = document.createElement('aside');
    widget.className = 'reading-progress';
    widget.setAttribute('aria-hidden', 'true');
    widget.innerHTML = `
      <div class="rp-title"></div>
      <div class="rp-h2" hidden></div>
      <div class="rp-h3" hidden></div>
      <div class="rp-h4" hidden></div>
      <div class="rp-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
        <div class="rp-bar-fill"></div>
      </div>
    `;
    widget.querySelector('.rp-title').textContent = postTitle;
    document.body.appendChild(widget);

    const slotH2 = widget.querySelector('.rp-h2');
    const slotH3 = widget.querySelector('.rp-h3');
    const slotH4 = widget.querySelector('.rp-h4');
    const bar = widget.querySelector('.rp-bar');
    const barFill = widget.querySelector('.rp-bar-fill');

    // Active heading state
    const intersecting = new Set();
    let lastActive = null;

    const headingTextFor = (section) => {
      if (!section) return null;
      const h = section.querySelector(':scope > h2, :scope > h3, :scope > h4');
      if (!h) return null;
      // Strip the trailing self-link icon and copy button content
      const clone = h.cloneNode(true);
      clone
        .querySelectorAll('button, .copy-section-link-button')
        .forEach((n) => n.remove());
      return clone.textContent.trim();
    };

    const setSlot = (slot, text) => {
      if (text) {
        if (slot.textContent !== text) slot.textContent = text;
        slot.hidden = false;
      } else {
        slot.hidden = true;
      }
    };

    const updateBreadcrumb = () => {
      // Pick the topmost intersecting heading (smallest top, but still > 0
      // when possible — an "above viewport" heading should still drive the
      // breadcrumb so the user sees the section they're in even after the
      // heading scrolls offscreen).
      if (intersecting.size === 0) return;
      const sorted = Array.from(intersecting).sort((a, b) => {
        return a.getBoundingClientRect().top - b.getBoundingClientRect().top;
      });
      const active = sorted[0];
      if (active === lastActive) return;
      lastActive = active;

      const sec2 = active.closest('section.level2');
      const sec3 = active.closest('section.level3');
      const sec4 = active.closest('section.level4');
      setSlot(slotH2, headingTextFor(sec2));
      setSlot(slotH3, headingTextFor(sec3));
      setSlot(slotH4, headingTextFor(sec4));
    };

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            intersecting.add(entry.target);
          } else {
            intersecting.delete(entry.target);
          }
        });
        updateBreadcrumb();
      },
      {
        rootMargin: '-15% 0px -75% 0px',
        threshold: [0, 0.25, 0.5, 0.75, 1],
      },
    );
    headings.forEach((h) => observer.observe(h));

    // Progress bar + visibility — both driven by the same rAF tick.
    let bodyTop = 0;
    let bodyBottom = 0;
    let h1Bottom = 0;
    const measure = () => {
      const rect = body.getBoundingClientRect();
      bodyTop = rect.top + window.scrollY;
      bodyBottom = bodyTop + body.offsetHeight;
      h1Bottom = articleH1.getBoundingClientRect().bottom + window.scrollY;
    };
    measure();

    let ticking = false;
    const tick = () => {
      ticking = false;
      const scrollY = window.scrollY;
      const viewportH = window.innerHeight;

      // Visibility: shown after user scrolls past the inline title, hidden as
      // they leave the article body. The 200px lead-out keeps the widget
      // present until the user is clearly past the content.
      const visible = scrollY > h1Bottom && scrollY < bodyBottom - 200;
      widget.classList.toggle('rp-visible', visible);

      // Progress: 0 when the article top hits the viewport top, 100 when the
      // article bottom hits the viewport bottom.
      const range = Math.max(1, body.offsetHeight - viewportH);
      const pct = Math.max(0, Math.min(100, ((scrollY - bodyTop) / range) * 100));
      barFill.style.width = `${pct}%`;
      bar.setAttribute('aria-valuenow', String(Math.round(pct)));
    };
    const schedule = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(tick);
    };
    tick();

    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener(
      'resize',
      () => {
        measure();
        schedule();
      },
      { passive: true },
    );
  });
})();
