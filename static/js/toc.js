// Simple collapse toggle for the in-article TOC
document.addEventListener("DOMContentLoaded", () => {
  const toc = document.querySelector("[data-toc-collapsible]");
  if (!toc) return;

  const toggle = toc.querySelector("[data-toc-toggle]");
  if (!toggle) return;

  const setState = (collapsed) => {
    toc.classList.toggle("collapsed", collapsed);
    toggle.setAttribute("aria-expanded", String(!collapsed));
    toggle.setAttribute(
      "title",
      collapsed ? "Expand table of contents" : "Collapse table of contents"
    );
  };

  toggle.addEventListener("click", (event) => {
    event.preventDefault();
    const nextState = !toc.classList.contains("collapsed");
    setState(nextState);
  });

  setState(toc.classList.contains("collapsed"));
});

// Minimal scroll-spy for headings referenced in the TOC
document.addEventListener("DOMContentLoaded", () => {
  const root = document.querySelector("[data-toc-root]");
  if (!root) return;

  const links = Array.from(root.querySelectorAll("[data-toc-link]"));
  const targets = new Map();
  links.forEach((a) => {
    const id = a.getAttribute("data-target-id");
    const el = id ? document.getElementById(id) : null;
    if (el) targets.set(el, a);
  });

  if (targets.size === 0) return;

  const clearActive = () => links.forEach((a) => a.dataset.active = "false");

  const obs = new IntersectionObserver((entries) => {
    // Choose the most visible heading in viewport
    const visible = entries
      .filter(e => e.isIntersecting)
      .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];

    if (visible) {
      clearActive();
      const link = targets.get(visible.target);
      if (link) link.dataset.active = "true";
    }
  }, {rootMargin: "0px 0px -70% 0px", threshold: [0.1, 0.5, 1]});

  targets.forEach((_, el) => obs.observe(el));

  // Optional: smooth scroll for in-page anchor clicks
  root.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-toc-link]");
    if (!a) return;
    const id = a.getAttribute("data-target-id");
    const tgt = id ? document.getElementById(id) : null;
    if (!tgt) return;
    e.preventDefault();
    // Adjust for sticky headers if you have them (e.g., 80px)
    const y = tgt.getBoundingClientRect().top + window.scrollY - 80;
    window.scrollTo({top: y, behavior: "smooth"});
    history.replaceState(null, "", `#${id}`);
  });
});


// static/js/toc-left.js
// Features:
// - Highlights active section as you scroll (IntersectionObserver)
// - Shows full TOC near top; after scrolling, only active branch (ancestors) remain visible
// - Sticky left rail already managed by CSS; we only toggle visibility
// - Page progress bar (0–100%) at bottom of TOC

(function () {
  const ready = (fn) => (
    document.readyState !== 'loading'
      ? fn()
      : document.addEventListener('DOMContentLoaded', fn)
  );

  ready(() => {
    const rail = document.querySelector('[data-toc-left]');
    if (!rail) return;

    const nav = rail.querySelector('[data-toc-nav]');
    const links = Array.from(rail.querySelectorAll('[data-toc-link]'));
    const nodes = Array.from(rail.querySelectorAll('[data-toc-node]'));
    const progressEl = rail.querySelector('[data-toc-progress]');
    const progressLabel = rail.querySelector('[data-toc-progress-label]');

    // Map heading element -> link
    const targets = new Map();
    links.forEach((a) => {
      const id = a.getAttribute('data-target-id');
      const el = id ? document.getElementById(id) : null;
      if (el) targets.set(el, a);
    });

    // Utility to mark visibility of nodes (collapse behavior)
    const setCollapsed = (li, collapsed) => {
      li.dataset.collapsed = collapsed ? 'true' : 'false';
      // Hide subtree by toggling a class or inline style
      const ul = li.querySelector(':scope > [data-toc-children]');
      if (ul) {
        ul.style.display = collapsed ? 'none' : '';
      }
    };

    // Initially: show the ENTIRE tree (requirement 4: top of page)
    nodes.forEach((li) => setCollapsed(li, false));

    // IntersectionObserver to compute active heading
    let currentActiveLink = null;

    const clearActive = () => {
      links.forEach((a) => (a.dataset.active = 'false'));
    };

    const revealActiveBranch = (link) => {
      // Collapse everything except the active branch (and its ancestors)
      const activeLi = link.closest('[data-toc-node]');
      // First collapse all
      nodes.forEach((li) => setCollapsed(li, true));
      // Walk up the tree to root, expanding along the way
      let li = activeLi;
      while (li) {
        setCollapsed(li, false);
        // also expand parent chain
        li = li.parentElement?.closest('[data-toc-node]') || null;
      }
      // Ensure direct children of active node are visible too
      const children = activeLi.querySelector(':scope > [data-toc-children]');
      if (children) children.style.display = '';
    };

    const observer = new IntersectionObserver((entries) => {
      // Consider the most visible in viewport
      const visible = entries
        .filter(e => e.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];

      if (visible && targets.has(visible.target)) {
        const link = targets.get(visible.target);
        if (link !== currentActiveLink) {
          currentActiveLink = link;
          clearActive();
          link.dataset.active = 'true';

          // After we’re away from the top, hide non-active branches
          const scrolledPastTop = window.scrollY > 20;
          if (scrolledPastTop) {
            revealActiveBranch(link);
          } else {
            // Near top: show full TOC
            nodes.forEach((li) => setCollapsed(li, false));
          }
        }
      }
    }, {
      // Tune rootMargin to your header height so we choose what’s “active” a bit before the heading hits the top
      rootMargin: '-80px 0px -60% 0px',
      threshold: [0.1, 0.5, 1.0]
    });

    // Observe headings
    targets.forEach((_, el) => observer.observe(el));

    // Smooth scroll on click (also plays nice with sticky headers)
    nav.addEventListener('click', (e) => {
      const a = e.target.closest('a[data-toc-link]');
      if (!a) return;
      const id = a.getAttribute('data-target-id');
      const target = id ? document.getElementById(id) : null;
      if (!target) return;
      e.preventDefault();
      const offset = 80; // match your sticky header height
      const y = target.getBoundingClientRect().top + window.scrollY - offset;
      window.scrollTo({top: y, behavior: 'smooth'});
      history.replaceState(null, '', `#${id}`);
    });

    // Page progress (bottom bar in TOC)
    const updateProgress = () => {
      const scrollTop = window.scrollY || document.documentElement.scrollTop;
      const docHeight = Math.max(
        document.body.scrollHeight, document.documentElement.scrollHeight,
        document.body.offsetHeight, document.documentElement.offsetHeight,
        document.body.clientHeight, document.documentElement.clientHeight
      );
      const winH = window.innerHeight;
      const max = Math.max(1, docHeight - winH);
      const pct = Math.min(100, Math.max(0, (scrollTop / max) * 100));
      if (progressEl) progressEl.style.width = `${pct}%`;
      if (progressLabel) progressLabel.textContent = `${Math.round(pct)}%`;
    };
    updateProgress();
    window.addEventListener('scroll', updateProgress, {passive: true});
    window.addEventListener('resize', updateProgress);
  });
})();
