/*	tablesorter-standalone.js: standalone table sorting functionality
	that works with tables enhanced by table_enhancer.py postprocessor.

	This is a simplified, framework-independent implementation that:
	- Automatically detects sortable tables (with <thead>)
	- Adds sort indicators to column headers
	- Sorts by clicking column headers
	- Supports text, numeric, and date sorting
	- Works with the table-wrapper structure from table_enhancer.py

	Based on concepts from tablesorter.js but rewritten for standalone use.
	License: MIT
 */

(function() {
	'use strict';

	/*****************/
	/*	Configuration.
	 */
	const TablesorterStandalone = {
		config: {
			// Selectors
			tableSelector: '.table-wrapper table',
			headerSelector: 'thead th',

			// CSS classes
			sortableClass: 'tablesorter-header',
			sortAscClass: 'tablesorter-headerDesc',  // Swapped to fix arrow direction
			sortDescClass: 'tablesorter-headerAsc',  // Swapped to fix arrow direction
			noSortClass: 'tablesorter-noSort',

			// Sort direction
			initialSortAsc: true,

			// Debug
			debug: false
		},

		/******************/
		/*	State storage.
		 */
		tables: new Map(),

		/*****************/
		/* Utilities.
		 */
		log: (message, level = 1) => {
			if (TablesorterStandalone.config.debug && console && level <= 1) {
				console.log(`[Tablesorter] ${message}`);
			}
		},

		/*****************/
		/* Sort types and detection.
		 */
		sortTypes: {
			numeric: {
				is: (value) => {
					return /^[\d\s,.-]+$/.test(value) && !isNaN(parseFloat(value.replace(/[,\s]/g, '')));
				},
				compare: (a, b) => {
					const numA = parseFloat(a.replace(/[,\s]/g, '')) || 0;
					const numB = parseFloat(b.replace(/[,\s]/g, '')) || 0;
					return numA - numB;
				}
			},
			text: {
				is: () => true, // Default fallback
				compare: (a, b) => {
					return a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });
				}
			}
		},

		detectColumnType: (table, columnIndex) => {
			const tbody = table.querySelector('tbody');
			if (!tbody) return 'text';

			// Sample first 10 rows to detect type
			const rows = Array.from(tbody.querySelectorAll('tr')).slice(0, 10);
			let numericCount = 0;

			for (const row of rows) {
				const cells = row.querySelectorAll('td');
				if (cells[columnIndex]) {
					const value = TablesorterStandalone.getCellValue(cells[columnIndex]).trim();
					if (value && TablesorterStandalone.sortTypes.numeric.is(value)) {
						numericCount++;
					}
				}
			}

			// If more than 70% are numeric, treat as numeric column
			return (numericCount / rows.length) > 0.7 ? 'numeric' : 'text';
		},

		getCellValue: (cell) => {
			// Get text content, excluding any nested elements we want to ignore
			let text = cell.textContent || '';
			// Remove link icons and other decorative elements
			const clone = cell.cloneNode(true);
			const iconsToRemove = clone.querySelectorAll('.link-icon-hook, .indicator-hook');
			iconsToRemove.forEach(el => el.remove());
			text = clone.textContent || '';
			return text.trim();
		},

		/*****************/
		/* Sorting logic.
		 */
		sortTable: (table, columnIndex, direction) => {
			const tbody = table.querySelector('tbody');
			if (!tbody) return;

			TablesorterStandalone.log(`Sorting column ${columnIndex} in ${direction} order`);

			// Get column type
			const columnType = TablesorterStandalone.detectColumnType(table, columnIndex);
			const sortFunction = TablesorterStandalone.sortTypes[columnType].compare;

			// Get all rows
			const rows = Array.from(tbody.querySelectorAll('tr'));

			// Sort rows
			rows.sort((rowA, rowB) => {
				const cellA = rowA.querySelectorAll('td')[columnIndex];
				const cellB = rowB.querySelectorAll('td')[columnIndex];

				if (!cellA || !cellB) return 0;

				const valueA = TablesorterStandalone.getCellValue(cellA);
				const valueB = TablesorterStandalone.getCellValue(cellB);

				// Handle empty values
				if (!valueA && !valueB) return 0;
				if (!valueA) return 1;
				if (!valueB) return -1;

				const result = sortFunction(valueA, valueB);
				return direction === 'asc' ? result : -result;
			});

			// Re-append rows in sorted order
			rows.forEach(row => tbody.appendChild(row));

			// Update zebra striping classes (odd/even)
			rows.forEach((row, index) => {
				row.classList.remove('odd', 'even');
				row.classList.add(index % 2 === 0 ? 'odd' : 'even');
			});
		},

		/*****************/
		/* Header interaction.
		 */
		handleHeaderClick: (event) => {
			const th = event.currentTarget;
			const table = th.closest('table');

			// Don't sort if header has no-sort class
			if (th.classList.contains(TablesorterStandalone.config.noSortClass)) {
				return;
			}

			// Get column index
			const headerRow = th.parentElement;
			const columnIndex = Array.from(headerRow.children).indexOf(th);

			// Get current state
			const tableState = TablesorterStandalone.tables.get(table);
			if (!tableState) return;

			// Determine new direction
			let newDirection;
			if (tableState.sortColumn === columnIndex) {
				// Toggle direction
				newDirection = tableState.sortDirection === 'asc' ? 'desc' : 'asc';
			} else {
				// New column, start with ascending
				newDirection = 'asc';
			}

			// Remove sort classes from all headers
			const allHeaders = headerRow.querySelectorAll('th');
			allHeaders.forEach(header => {
				header.classList.remove(
					TablesorterStandalone.config.sortAscClass,
					TablesorterStandalone.config.sortDescClass
				);
			});

			// Add sort class to clicked header
			const sortClass = newDirection === 'asc'
				? TablesorterStandalone.config.sortAscClass
				: TablesorterStandalone.config.sortDescClass;
			th.classList.add(sortClass);

			// Update state
			tableState.sortColumn = columnIndex;
			tableState.sortDirection = newDirection;

			// Sort the table
			TablesorterStandalone.sortTable(table, columnIndex, newDirection);
		},

		/*****************/
		/* Initialization.
		 */
		makeTableSortable: (table) => {
			TablesorterStandalone.log(`Making table sortable`);

			const thead = table.querySelector('thead');
			if (!thead) {
				TablesorterStandalone.log('Table has no thead, skipping');
				return;
			}

			// Check if table has sortable attribute
			if (!table.hasAttribute('data-sortable') || table.getAttribute('data-sortable') !== 'true') {
				TablesorterStandalone.log('Table does not have data-sortable="true", skipping');
				return;
			}

			// Store table state
			TablesorterStandalone.tables.set(table, {
				sortColumn: null,
				sortDirection: 'asc'
			});

			// Add sortable class to headers
			const headers = thead.querySelectorAll(TablesorterStandalone.config.headerSelector);
			headers.forEach((th, index) => {
				// Skip if already has no-sort class
				if (th.classList.contains(TablesorterStandalone.config.noSortClass)) {
					return;
				}

				// Add sortable class
				th.classList.add(TablesorterStandalone.config.sortableClass);

				// Add click handler
				th.addEventListener('click', TablesorterStandalone.handleHeaderClick);

				// Make it clear it's clickable
				th.style.cursor = 'pointer';
			});
		},

		initializeTables: () => {
			TablesorterStandalone.log('Initializing tables');

			// Find all tables within table wrappers
			const tables = document.querySelectorAll(TablesorterStandalone.config.tableSelector);

			TablesorterStandalone.log(`Found ${tables.length} tables`);

			tables.forEach(table => {
				// Skip if already initialized
				if (TablesorterStandalone.tables.has(table)) {
					return;
				}

				TablesorterStandalone.makeTableSortable(table);
			});
		},

		/*****************/
		/* Public API.
		 */
		init: () => {
			TablesorterStandalone.log('TablesorterStandalone initializing');

			// Initialize existing tables
			TablesorterStandalone.initializeTables();

			// Watch for dynamically added tables
			if (window.MutationObserver) {
				const observer = new MutationObserver((mutations) => {
					let shouldReinitialize = false;

					mutations.forEach(mutation => {
						mutation.addedNodes.forEach(node => {
							if (node.nodeType === Node.ELEMENT_NODE) {
								if (node.matches && node.matches('.table-wrapper')) {
									shouldReinitialize = true;
								} else if (node.querySelector && node.querySelector('.table-wrapper')) {
									shouldReinitialize = true;
								}
							}
						});
					});

					if (shouldReinitialize) {
						TablesorterStandalone.initializeTables();
					}
				});

				observer.observe(document.body, {
					childList: true,
					subtree: true
				});
			}

			TablesorterStandalone.log('TablesorterStandalone initialized');
		},

		// Manual re-initialization (useful for dynamically loaded content)
		refresh: () => {
			TablesorterStandalone.initializeTables();
		}
	};

	/*****************/
	/* Auto-initialize on DOM ready.
	 */
	if (document.readyState === 'loading') {
		document.addEventListener('DOMContentLoaded', () => TablesorterStandalone.init());
	} else {
		TablesorterStandalone.init();
	}

	// Export for manual use
	window.TablesorterStandalone = TablesorterStandalone;
})();
