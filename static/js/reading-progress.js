// Reading progress + active-heading breadcrumb widget.
//
// Mounts on individual post pages (any page that renders a #markdownBody
// container with at least two H2 headings). Bails out silently otherwise so
// nothing needs to know about post-vs-archive routing.
//
// Active heading derivation walks the section ancestor chain produced by
// engine/markdown/filters/heading_sectionizer.lua — `<section class="block
// levelN">` wraps each heading and nests child sections inside their parent.
// If that filter ever flattens nesting, the breadcrumb derivation here has
// to change.

(function () {
  const SCROLL_OFFSET = 80; // matches anchor-links.js / scroll-margin-top
  const ACTIVATION_RATIO = 0.15; // heading is "active" once its top crosses 15% from viewport top

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

    // Content headings — H1 included so posts that use H1 inside the body
    // (not just as the page title) still get a top-level breadcrumb entry.
    const headings = Array.from(
      body.querySelectorAll('h1[id], h2[id], h3[id], h4[id]'),
    );
    const topLevelCount = headings.filter(
      (h) => h.tagName === 'H1' || h.tagName === 'H2',
    ).length;
    if (topLevelCount < 2) return; // Single-section post — widget adds nothing.

    const postTitle = articleH1.textContent.trim();

    // Build widget DOM — slots are <button> so click and keyboard work for free.
    const widget = document.createElement('aside');
    widget.className = 'reading-progress';
    widget.setAttribute('aria-hidden', 'true');
    widget.innerHTML = `
      <div class="rp-title"></div>
      <button class="rp-h1" type="button" hidden></button>
      <button class="rp-h2" type="button" hidden></button>
      <button class="rp-h3" type="button" hidden></button>
      <button class="rp-h4" type="button" hidden></button>
      <div class="rp-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
        <div class="rp-bar-fill"></div>
      </div>
    `;
    widget.querySelector('.rp-title').textContent = postTitle;
    document.body.appendChild(widget);

    const slotH1 = widget.querySelector('.rp-h1');
    const slotH2 = widget.querySelector('.rp-h2');
    const slotH3 = widget.querySelector('.rp-h3');
    const slotH4 = widget.querySelector('.rp-h4');
    const bar = widget.querySelector('.rp-bar');
    const barFill = widget.querySelector('.rp-bar-fill');

    // Active heading state — heading elements (not text) so click handlers
    // can scroll to them directly.
    let activeH1 = null;
    let activeH2 = null;
    let activeH3 = null;
    let activeH4 = null;
    let lastCandidate = null;

    const cleanHeadingText = (h) => {
      if (!h) return null;
      // Strip the trailing self-link anchor and copy button content.
      const clone = h.cloneNode(true);
      clone
        .querySelectorAll('button, .copy-section-link-button')
        .forEach((n) => n.remove());
      return clone.textContent.trim();
    };

    const setSlot = (slot, heading) => {
      const text = cleanHeadingText(heading);
      if (text) {
        if (slot.textContent !== text) slot.textContent = text;
        slot.hidden = false;
      } else {
        slot.hidden = true;
      }
    };

    const updateBreadcrumb = () => {
      // "Active" = the most recent heading whose top has crossed the
      // activation line. More robust than IntersectionObserver-on-headings
      // for deeply-nested H4s, which can scroll past a narrow rootMargin
      // strip without ever firing as visible.
      const triggerY = window.innerHeight * ACTIVATION_RATIO;
      let candidate = null;
      for (const h of headings) {
        if (h.getBoundingClientRect().top <= triggerY) {
          candidate = h;
        } else {
          break; // headings are in document order
        }
      }
      if (candidate === lastCandidate) return;
      lastCandidate = candidate;

      if (!candidate) {
        activeH1 = activeH2 = activeH3 = activeH4 = null;
      } else {
        const sec1 = candidate.closest('section.level1');
        const sec2 = candidate.closest('section.level2');
        const sec3 = candidate.closest('section.level3');
        const sec4 = candidate.closest('section.level4');
        activeH1 = sec1 ? sec1.querySelector(':scope > h1') : null;
        activeH2 = sec2 ? sec2.querySelector(':scope > h2') : null;
        activeH3 = sec3 ? sec3.querySelector(':scope > h3') : null;
        activeH4 = sec4 ? sec4.querySelector(':scope > h4') : null;
      }
      setSlot(slotH1, activeH1);
      setSlot(slotH2, activeH2);
      setSlot(slotH3, activeH3);
      setSlot(slotH4, activeH4);
    };

    // Click-to-scroll on each slot. Mirrors anchor-links.js behavior.
    const scrollToHeading = (h) => {
      if (!h || !h.id) return;
      const y = h.getBoundingClientRect().top + window.scrollY - SCROLL_OFFSET;
      window.scrollTo({ top: y, behavior: 'smooth' });
      history.replaceState(null, '', `#${h.id}`);
    };
    slotH1.addEventListener('click', () => scrollToHeading(activeH1));
    slotH2.addEventListener('click', () => scrollToHeading(activeH2));
    slotH3.addEventListener('click', () => scrollToHeading(activeH3));
    slotH4.addEventListener('click', () => scrollToHeading(activeH4));

    // Eclipse: hide the widget while any full-width element is in viewport
    // so it never covers a wide image, table, code block, etc. Sidenotes
    // are still allowed underneath (z-index handles that).
    const fullWidthElements = body.querySelectorAll('.width-full');
    if (fullWidthElements.length > 0) {
      const fwIntersecting = new Set();
      const fwObserver = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) fwIntersecting.add(entry.target);
            else fwIntersecting.delete(entry.target);
          });
          widget.classList.toggle('rp-eclipsed', fwIntersecting.size > 0);
        },
        { threshold: 0.05 },
      );
      fullWidthElements.forEach((el) => fwObserver.observe(el));
    }

    // Progress bar + visibility — both driven by the same rAF tick along
    // with the breadcrumb update so it all stays in sync per frame.
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

      const visible = scrollY > h1Bottom && scrollY < bodyBottom - 200;
      widget.classList.toggle('rp-visible', visible);

      const range = Math.max(1, body.offsetHeight - viewportH);
      const pct = Math.max(0, Math.min(100, ((scrollY - bodyTop) / range) * 100));
      barFill.style.width = `${pct}%`;
      bar.setAttribute('aria-valuenow', String(Math.round(pct)));

      updateBreadcrumb();
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
