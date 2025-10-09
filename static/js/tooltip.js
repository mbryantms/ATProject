import {arrow, autoUpdate, computePosition, flip, limitShift, offset, shift, size} from "@floating-ui/dom";

// Make Floating UI available globally (optional, for compatibility)
window.FloatingUIDOM = {
  computePosition,
  flip,
  shift,
  offset,
  arrow,
  autoUpdate
};

// Tooltip functionality
document.addEventListener('DOMContentLoaded', function () {
    // Store active tooltip instances
    const tooltipInstances = new Map();

    // Initialize all tooltips2
    function initTooltips() {
      const triggers = document.querySelectorAll('[data-tooltip-target]');

      triggers.forEach(trigger => {
        // Skip if already initialized
        if (tooltipInstances.has(trigger)) return;

        const tooltipId = trigger.dataset.tooltipTarget;
        const tooltip = document.getElementById(tooltipId);

        if (!tooltip) return;

        const config = JSON.parse(trigger.dataset.tooltipConfig || '{}');

        // Create tooltip instance
        const instance = createTooltipInstance(trigger, tooltip, config);
        tooltipInstances.set(trigger, instance);
      });
    }

    function createTooltipInstance(trigger, tooltip, config) {
      let showTimeout, hideTimeout, cleanup;

      const show = () => {
        clearTimeout(hideTimeout);

        if (config.delay) {
          showTimeout = setTimeout(() => showTooltip(), config.delay);
        } else {
          showTooltip();
        }
      };

      const hide = () => {
        clearTimeout(showTimeout);
        hideTimeout = setTimeout(() => hideTooltip(), 100);
      };

      const showTooltip = async () => {
          tooltip.style.display = 'block';

          // Configure middleware
          const middleware = [
            offset(config.offset || 10),
            flip(),
            shift({padding: 8, limiter: limitShift({offset: 4})}),
            size({
              apply({availableWidth, availableHeight, elements}) {
                Object.assign(elements.floating.style, {
                  maxWidth: Math.min(availableWidth, 360) + "px",  // clamp to viewport
                });
              }
            }),
          ];

          // Add arrow middleware if enabled
          const arrowElement = tooltip.querySelector('[data-popper-arrow]');
          if (config.arrow && arrowElement) {
            middleware.push(arrow({element: arrowElement}));
          }

          // Compute position
          const {x, y, placement, middlewareData} = await computePosition(trigger, tooltip, {
            placement: config.position || 'top',
            middleware: middleware
          });

          // Apply positioning
          Object.assign(tooltip.style, {
            left: `${x}px`,
            top: `${y}px`,
            position: 'absolute'
          });

          // Position arrow if present
          if (config.arrow && arrowElement && middlewareData.arrow) {
            const {x: arrowX, y: arrowY} = middlewareData.arrow;

            Object.assign(arrowElement.style, {
              left: arrowX != null ? `${arrowX}px` : '',
              top: arrowY != null ? `${arrowY}px` : ''
            });
          }

          // Update placement attribute for CSS styling
          tooltip.setAttribute('data-popper-placement', placement);

          // Setup auto-update for dynamic positioning
          cleanup = autoUpdate(trigger, tooltip, async () => {
            const {x, y, placement, middlewareData} = await computePosition(trigger, tooltip, {
              placement: config.position || 'top',
              middleware: middleware
            });

            Object.assign(tooltip.style, {
              left: `${x}px`,
              top: `${y}px`
            });

            if (config.arrow && arrowElement && middlewareData.arrow) {
              const {x: arrowX, y: arrowY} = middlewareData.arrow;
              Object.assign(arrowElement.style, {
                left: arrowX != null ? `${arrowX}px` : '',
                top: arrowY != null ? `${arrowY}px` : ''
              });
            }

            tooltip.setAttribute('data-popper-placement', placement);
          });
        }
      ;

      const hideTooltip = () => {
        tooltip.style.display = 'none';
        if (cleanup) {
          cleanup();
          cleanup = null;
        }
      };

      // Event listeners based on trigger type
      if (config.trigger === 'hover') {
        trigger.addEventListener('mouseenter', show);
        trigger.addEventListener('mouseleave', hide);
        tooltip.addEventListener('mouseenter', () => clearTimeout(hideTimeout));
        tooltip.addEventListener('mouseleave', hide);
      } else if (config.trigger === 'click') {
        trigger.addEventListener('click', (e) => {
          e.preventDefault();
          if (tooltip.style.display === 'block') {
            hide();
          } else {
            show();
          }
        });

        // Close on outside click
        document.addEventListener('click', (e) => {
          if (!trigger.contains(e.target) && !tooltip.contains(e.target)) {
            hide();
          }
        });
      } else if (config.trigger === 'focus') {
        trigger.addEventListener('focus', show);
        trigger.addEventListener('blur', hide);
      }

      return {
        show,
        hide,
        destroy: () => {
          if (cleanup) cleanup();
          clearTimeout(showTimeout);
          clearTimeout(hideTimeout);
        }
      };
    }

    // API for manual tooltip control
    window.Tooltip = {
      init: initTooltips,
      show: (triggerId) => {
        const trigger = document.getElementById(triggerId);
        const instance = tooltipInstances.get(trigger);
        if (instance) instance.show();
      },
      hide: (triggerId) => {
        const trigger = document.getElementById(triggerId);
        const instance = tooltipInstances.get(trigger);
        if (instance) instance.hide();
      },
      destroy: (triggerId) => {
        const trigger = document.getElementById(triggerId);
        const instance = tooltipInstances.get(trigger);
        if (instance) {
          instance.destroy();
          tooltipInstances.delete(trigger);
        }
      },
      destroyAll: () => {
        tooltipInstances.forEach(instance => instance.destroy());
        tooltipInstances.clear();
      }
    };

    // Initialize tooltips
    initTooltips();

    // Re-initialize when new content is added dynamically
    const observer = new MutationObserver(() => {
      initTooltips();
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true
    });
  }
)
;

// Export functions if using as a module elsewhere
export {computePosition, flip, shift, offset, arrow, autoUpdate};

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


document.addEventListener('click', function (e) {
  const a = e.target.closest('a.anchor-link.header-anchor');
  if (!a) return;

  // Don’t navigate immediately—copy the deep link instead.
  e.preventDefault();

  // The header id is the hash target in the href (e.g., "#h3-header-with-auto-id")
  const hash = a.getAttribute('href') || '';
  const url = new URL(hash, window.location.href).toString();

  // Copy to clipboard (best effort)
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(url).catch(() => {/* ignore */
    });
  } else {
    // Fallback
    const ta = document.createElement('textarea');
    ta.value = url;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand('copy');
    } catch (e) {
    }
    document.body.removeChild(ta);
  }

  // Quick flip animation
  a.classList.add('copied');
  setTimeout(() => a.classList.remove('copied'), 220);

  // Optional: update URL hash without scrolling
  if (hash.startsWith('#')) {
    history.replaceState(null, '', hash);
  }
}, {passive: false});

(function () {
  const SCROLL_OFFSET = 80; // px

  // 1) Inject a real clickable icon element into each anchor
  document.querySelectorAll('a.anchor-link.header-anchor').forEach(a => {
    // Avoid duplicating if re-run
    if (!a.querySelector('.hdr-link-icon')) {
      const icon = document.createElement('span');
      icon.className = 'hdr-link-icon';
      icon.setAttribute('aria-hidden', 'true');
      a.appendChild(icon);
    }
  });

  // Helper: smooth-scroll to a hash target with offset
  function smoothScrollToHash(hash) {
    if (!hash || !hash.startsWith('#')) return;
    const el = document.getElementById(hash.slice(1));
    if (!el) return;

    const y = el.getBoundingClientRect().top + window.pageYOffset - SCROLL_OFFSET;
    window.scrollTo({top: y, behavior: 'smooth'});

    // Update the URL hash without causing a jump
    history.replaceState(null, '', hash);
  }

  // Helper: copy absolute URL of the hash to clipboard
  function copyLink(hash, iconEl) {
    const url = new URL(hash, window.location.href).toString();
    (navigator.clipboard?.writeText?.(url) ?? Promise.reject())
      .catch(() => {
        const ta = document.createElement('textarea');
        ta.value = url;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        try {
          document.execCommand('copy');
        } catch (e) {
        }
        document.body.removeChild(ta);
      })
      .finally(() => {
        // Flip animation feedback
        if (iconEl) {
          iconEl.classList.add('copied');
          setTimeout(() => iconEl.classList.remove('copied'), 220);
        }
      });
  }

  // 2) Delegate clicks
  document.addEventListener('click', function (e) {
    const a = e.target.closest('a.anchor-link.header-anchor');
    if (!a) return;

    const hash = a.getAttribute('href') || '';
    const icon = e.target.closest('.hdr-link-icon');

    // If clicking the icon -> copy link
    if (icon) {
      e.preventDefault();
      e.stopPropagation();
      copyLink(hash, icon);
      return;
    }

    // Otherwise clicking the header/anchor text -> smooth scroll with 80px offset
    e.preventDefault();
    smoothScrollToHash(hash);
  }, {passive: false});

  // Optional: if the page loads with a hash, apply the offset scroll once
  if (location.hash) {
    // Delay to allow layout to settle (fonts, images)
    window.addEventListener('load', () => smoothScrollToHash(location.hash));
  }
})();

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('a.anchor-link.header-anchor').forEach(a => {
    if (!a.querySelector('.hdr-link-icon')) {
      const s = document.createElement('span');
      s.className = 'hdr-link-icon';
      s.setAttribute('aria-hidden', 'true');
      a.appendChild(s);
    }
  });
});

(function () {
  const SCROLL_OFFSET = 80; // px
  const SUPPRESS_MS = 400;  // how long to hide hover UI

  // (Keep your icon injection code as-is)

  function smoothScrollToHash(hash) {
    if (!hash || !hash.startsWith('#')) return;
    const el = document.getElementById(hash.slice(1));
    if (!el) return;

    const y = el.getBoundingClientRect().top + window.pageYOffset - SCROLL_OFFSET;
    window.scrollTo({top: y, behavior: 'smooth'});
    history.replaceState(null, '', hash);
  }

  function suppressHoverUI(ms = SUPPRESS_MS) {
    const root = document.documentElement;
    root.classList.add('suppress-header-hover');
    setTimeout(() => root.classList.remove('suppress-header-hover'), ms);
  }

  function copyLink(hash, iconEl) {
    const url = new URL(hash, window.location.href).toString();
    (navigator.clipboard?.writeText?.(url) ?? Promise.reject())
      .catch(() => {
        const ta = document.createElement('textarea');
        ta.value = url;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        try {
          document.execCommand('copy');
        } catch (e) {
        }
        document.body.removeChild(ta);
      })
      .finally(() => {
        if (iconEl) {
          iconEl.classList.add('copied');
          setTimeout(() => iconEl.classList.remove('copied'), 220);
        }
      });
  }

  document.addEventListener('click', function (e) {
    const a = e.target.closest('a.anchor-link.header-anchor');
    if (!a) return;

    const hash = a.getAttribute('href') || '';
    const icon = e.target.closest('.hdr-link-icon');

    if (icon) {
      // Clicked the icon: copy link
      e.preventDefault();
      e.stopPropagation();
      copyLink(hash, icon);
      return;
    }

    // Clicked the header/anchor text: smooth scroll + hide hover UI briefly
    e.preventDefault();
    suppressHoverUI();
    smoothScrollToHash(hash);
    // also blur to remove :focus-within styles, if any
    a.blur?.();
  }, {passive: false});
})();
