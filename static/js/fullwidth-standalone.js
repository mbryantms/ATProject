/*	fullwidth-standalone.js: standalone full-width block expansion functionality
	that works with elements enhanced by various postprocessors (table_enhancer.py, etc).

	This is a simplified, framework-independent implementation that:
	- Automatically detects full-width elements (with .width-full class)
	- Calculates proper margins to expand to viewport width
	- Handles responsive layout (disabled on mobile)
	- Works with nested elements (e.g., tables in lists)
	- Supports any element type with .width-full class

	Based on concepts from fullwidth.js but rewritten for standalone use.
	License: MIT
 */

(function() {
	'use strict';

	/*****************/
	/*	Configuration.
	 */
	const FullWidthStandalone = {
		config: {
			// Selectors
			containerSelector: '#markdownBody',
			fullWidthSelector: '.width-full',

			// Layout settings
			sideMargin: 25, // Minimum margin on both sides of viewport
			mobileBreakpoint: 649, // Max width for mobile (no full-width)

			// Debug
			debug: false
		},

		/******************/
		/*	State storage.
		 */
		layoutState: {
			pageWidth: 0,
			leftAdjustment: 0,
			isMobile: false
		},

		/*****************/
		/* Utilities.
		 */
		log: (message, level = 1) => {
			if (FullWidthStandalone.config.debug && console && level <= 1) {
				console.log(`[FullWidth] ${message}`);
			}
		},

		/*****************/
		/* Layout calculation.
		 */
		updateLayoutMetrics: () => {
			FullWidthStandalone.log('Updating layout metrics');

			const root = document.documentElement;
			const container = document.querySelector(FullWidthStandalone.config.containerSelector);

			if (!container) {
				FullWidthStandalone.log('Container not found');
				return;
			}

			// Get viewport width
			FullWidthStandalone.layoutState.pageWidth = root.offsetWidth;

			// Check if mobile
			FullWidthStandalone.layoutState.isMobile =
				window.innerWidth <= FullWidthStandalone.config.mobileBreakpoint;

			// Calculate left adjustment (to account for asymmetric content positioning)
			const containerRect = container.getBoundingClientRect();
			const rightMargin = FullWidthStandalone.layoutState.pageWidth - containerRect.right;
			FullWidthStandalone.layoutState.leftAdjustment = containerRect.left - rightMargin;

			// Update CSS custom properties
			root.style.setProperty(
				'--fullwidth-side-margin',
				`${FullWidthStandalone.config.sideMargin}px`
			);
			root.style.setProperty(
				'--fullwidth-page-width',
				`${FullWidthStandalone.layoutState.pageWidth}px`
			);
			root.style.setProperty(
				'--fullwidth-left-adjustment',
				`${FullWidthStandalone.layoutState.leftAdjustment}px`
			);

			FullWidthStandalone.log(
				`Metrics: pageWidth=${FullWidthStandalone.layoutState.pageWidth}, ` +
				`leftAdjustment=${FullWidthStandalone.layoutState.leftAdjustment}, ` +
				`isMobile=${FullWidthStandalone.layoutState.isMobile}`
			);
		},

		/*****************/
		/* Margin calculation for individual elements.
		 */
		calculateAdditionalLeftAdjustment: (element) => {
			// Compensate for block indentation due to nesting (e.g., in lists)
			const enclosingListItem = element.closest('li');

			// Don't adjust for collapsed blocks
			if (element.closest('.collapse-block')) {
				return 0;
			}

			if (enclosingListItem) {
				const container = document.querySelector(FullWidthStandalone.config.containerSelector);
				if (!container) return 0;

				const containerRect = container.getBoundingClientRect();
				const listItemFirstChild = enclosingListItem.firstElementChild;

				if (listItemFirstChild) {
					const listRect = listItemFirstChild.getBoundingClientRect();
					return containerRect.x - listRect.x;
				}
			}

			return 0;
		},

		applyFullWidthMargins: (element) => {
			if (FullWidthStandalone.layoutState.isMobile) {
				// Remove margins on mobile
				element.style.marginLeft = '';
				element.style.marginRight = '';
				return;
			}

			const additionalLeftAdjustment = FullWidthStandalone.calculateAdditionalLeftAdjustment(element);

			// Calculate margins using CSS custom properties and additional adjustment
			element.style.marginLeft = `calc(
				(-1 * (var(--fullwidth-left-adjustment) / 2.0))
				+ var(--fullwidth-side-margin)
				- ((var(--fullwidth-page-width) - 100%) / 2.0)
				+ (${additionalLeftAdjustment}px / 2.0)
			)`;

			element.style.marginRight = `calc(
				(1 * (var(--fullwidth-left-adjustment) / 2.0))
				+ var(--fullwidth-side-margin)
				- ((var(--fullwidth-page-width) - 100%) / 2.0)
				- (${additionalLeftAdjustment}px / 2.0)
			)`;

			FullWidthStandalone.log(`Applied margins to ${element.tagName} with additional adjustment: ${additionalLeftAdjustment}px`);
		},

		/*****************/
		/* Process all full-width elements.
		 */
		processFullWidthElements: () => {
			FullWidthStandalone.log('Processing full-width elements');

			// Update layout metrics first
			FullWidthStandalone.updateLayoutMetrics();

			// Find all full-width elements
			const fullWidthElements = document.querySelectorAll(FullWidthStandalone.config.fullWidthSelector);

			FullWidthStandalone.log(`Found ${fullWidthElements.length} full-width elements`);

			// Apply margins to each element
			fullWidthElements.forEach(element => {
				FullWidthStandalone.applyFullWidthMargins(element);
			});
		},

		/*****************/
		/* Initialization.
		 */
		init: () => {
			FullWidthStandalone.log('FullWidthStandalone initializing');

			// Process elements on load
			FullWidthStandalone.processFullWidthElements();

			// Re-process on window resize
			let resizeTimeout;
			window.addEventListener('resize', () => {
				clearTimeout(resizeTimeout);
				resizeTimeout = setTimeout(() => {
					FullWidthStandalone.processFullWidthElements();
				}, 100); // Debounce resize events
			});

			// Watch for dynamically added full-width elements
			if (window.MutationObserver) {
				const observer = new MutationObserver((mutations) => {
					let shouldReprocess = false;

					mutations.forEach(mutation => {
						mutation.addedNodes.forEach(node => {
							if (node.nodeType === Node.ELEMENT_NODE) {
								// Check if the node itself or any descendant has .width-full
								if (node.matches && node.matches(FullWidthStandalone.config.fullWidthSelector)) {
									shouldReprocess = true;
								} else if (node.querySelector && node.querySelector(FullWidthStandalone.config.fullWidthSelector)) {
									shouldReprocess = true;
								}
							}
						});
					});

					if (shouldReprocess) {
						FullWidthStandalone.processFullWidthElements();
					}
				});

				const container = document.querySelector(FullWidthStandalone.config.containerSelector);
				if (container) {
					observer.observe(container, {
						childList: true,
						subtree: true
					});
				}
			}

			FullWidthStandalone.log('FullWidthStandalone initialized');
		},

		// Manual re-processing (useful for dynamically loaded content)
		refresh: () => {
			FullWidthStandalone.processFullWidthElements();
		}
	};

	/*****************/
	/* Auto-initialize on DOM ready.
	 */
	if (document.readyState === 'loading') {
		document.addEventListener('DOMContentLoaded', () => FullWidthStandalone.init());
	} else {
		FullWidthStandalone.init();
	}

	// Export for manual use
	window.FullWidthStandalone = FullWidthStandalone;
})();
