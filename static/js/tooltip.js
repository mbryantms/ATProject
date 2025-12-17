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
