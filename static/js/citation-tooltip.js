/**
 * Citation tooltip and scroll-to-reference behavior.
 *
 * - Hover over an inline citation: shows a tooltip with the full formatted reference.
 * - Click an inline citation: smooth-scrolls to the bibliography entry and highlights it.
 * - Mobile: tap shows tooltip, tap elsewhere dismisses.
 *
 * Uses @floating-ui/dom for positioning (same library as the existing tooltip system).
 */

import {
  computePosition,
  flip,
  offset,
  shift,
  limitShift,
  size,
} from '@floating-ui/dom';

document.addEventListener('DOMContentLoaded', function () {
  // Single shared tooltip element
  let tooltip = null;
  let activeCleanup = null;
  let showTimeout = null;
  let hideTimeout = null;
  const isTouchDevice = 'ontouchstart' in window || navigator.maxTouchPoints > 0;

  function getTooltip() {
    if (!tooltip) {
      tooltip = document.createElement('div');
      tooltip.className = 'citation-tooltip';
      tooltip.setAttribute('role', 'tooltip');
      document.body.appendChild(tooltip);
    }
    return tooltip;
  }

  function showTooltipFor(citation) {
    // Get all bibliography entries for this citation's keys
    const keys = (citation.dataset.citationKeys || '').split(' ');
    let content = '';

    // Try to get content from the bibliography entries on the page
    for (const key of keys) {
      const entry = document.getElementById('ref-' + key);
      if (entry) {
        const refText = entry.querySelector('.reference-text');
        if (refText) {
          if (content) content += '';
          content += refText.innerHTML;
        }
      }
    }

    // Fallback: use the data-citation attribute (plain text)
    if (!content) {
      content = citation.dataset.citation || '';
    }

    if (!content) return;

    const tip = getTooltip();
    tip.innerHTML = content;
    tip.setAttribute('data-show', '');

    // Position using Floating UI
    computePosition(citation, tip, {
      placement: 'top',
      middleware: [
        offset(8),
        flip({ fallbackPlacements: ['bottom', 'right', 'left'] }),
        shift({ padding: 8, limiter: limitShift({ offset: 4 }) }),
        size({
          apply({ availableWidth, elements }) {
            Object.assign(elements.floating.style, {
              maxWidth: Math.min(availableWidth - 16, 360) + 'px',
            });
          },
        }),
      ],
    }).then(({ x, y }) => {
      Object.assign(tip.style, {
        left: x + 'px',
        top: y + 'px',
      });
    });
  }

  function hideTooltip() {
    clearTimeout(showTimeout);
    if (tooltip) {
      tooltip.removeAttribute('data-show');
    }
    if (activeCleanup) {
      activeCleanup();
      activeCleanup = null;
    }
  }

  // Highlight a bibliography entry when scrolled to
  function highlightEntry(entryId) {
    const entry = document.getElementById(entryId);
    if (!entry) return;

    // Remove highlight from any previously highlighted entry
    document
      .querySelectorAll('.reference-highlight')
      .forEach((el) => el.classList.remove('reference-highlight'));

    entry.classList.add('reference-highlight');

    // Remove highlight after animation
    setTimeout(() => {
      entry.classList.remove('reference-highlight');
    }, 2000);
  }

  // Set up event listeners on all citations
  function initCitations() {
    const citations = document.querySelectorAll('a.citation[data-citation-keys]');

    citations.forEach((citation) => {
      if (citation.dataset.citationInit) return;
      citation.dataset.citationInit = 'true';

      if (isTouchDevice) {
        // Mobile: tap to show/hide tooltip
        citation.addEventListener('click', function (e) {
          e.preventDefault();

          if (
            tooltip &&
            tooltip.hasAttribute('data-show') &&
            tooltip._activeCitation === citation
          ) {
            hideTooltip();
            tooltip._activeCitation = null;
          } else {
            hideTooltip();
            showTooltipFor(citation);
            if (tooltip) tooltip._activeCitation = citation;
          }
        });
      } else {
        // Desktop: hover to show tooltip
        citation.addEventListener('mouseenter', function () {
          clearTimeout(hideTimeout);
          showTimeout = setTimeout(() => showTooltipFor(citation), 120);
        });

        citation.addEventListener('mouseleave', function () {
          clearTimeout(showTimeout);
          hideTimeout = setTimeout(hideTooltip, 150);
        });

        // Click scrolls to reference
        citation.addEventListener('click', function (e) {
          e.preventDefault();
          hideTooltip();
          const href = citation.getAttribute('href');
          if (href && href.startsWith('#ref-')) {
            const target = document.getElementById(href.substring(1));
            if (target) {
              target.scrollIntoView({ behavior: 'smooth', block: 'center' });
              highlightEntry(href.substring(1));
            }
          }
        });
      }
    });
  }

  // Dismiss tooltip on outside tap (mobile)
  if (isTouchDevice) {
    document.addEventListener('click', function (e) {
      if (tooltip && tooltip.hasAttribute('data-show')) {
        if (!tooltip.contains(e.target) && !e.target.closest('a.citation')) {
          hideTooltip();
          tooltip._activeCitation = null;
        }
      }
    });

    // Dismiss on scroll (mobile)
    document.addEventListener(
      'scroll',
      function () {
        if (tooltip && tooltip.hasAttribute('data-show')) {
          hideTooltip();
          tooltip._activeCitation = null;
        }
      },
      { passive: true },
    );
  }

  // Keep tooltip visible when hovering over it (desktop)
  document.addEventListener(
    'mouseenter',
    function (e) {
      if (e.target === tooltip || (tooltip && tooltip.contains(e.target))) {
        clearTimeout(hideTimeout);
      }
    },
    true,
  );

  document.addEventListener(
    'mouseleave',
    function (e) {
      if (e.target === tooltip || (tooltip && tooltip.contains(e.target))) {
        hideTimeout = setTimeout(hideTooltip, 150);
      }
    },
    true,
  );

  initCitations();
});
