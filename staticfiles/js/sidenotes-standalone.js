/*	sidenotes-standalone.js: standalone JS library for parsing HTML documents with
	Pandoc-style footnotes and dynamically repositioning them into the
	left/right margins, when browser windows are wide enough.

	This is a standalone version that works without external framework dependencies.

	Based on sidenotes.js by Said Achmiz (2019-03-11)
	Standalone adaptation: 2025
	License: MIT
 */

(function() {
	'use strict';

	/*****************/
	/*	Configuration.
	 */
	const SidenotesStandalone = {
		/*  Configuration options (can be overridden before init)
		 */
		config: {
			// Selectors
			containerSelector: '#markdownBody',
			citationSelector: 'a.footnote-ref',
			footnoteSelector: 'li.footnote',

			// Spacing
			sidenoteSpacing: 60.0,
			sidenotePadding: 13.0,

			// Breakpoints (must match CSS)
			minimumViewportWidthForSidenotes: 1761,
			minimumViewportWidthForSidenoteMarginNotes: 1497,

			// Column usage
			useLeftColumn: false,
			useRightColumn: true,

			// Elements that can overlap sidenotes
			potentiallyOverlappingElementsSelectors: [
				".width-full img",
				".width-full video",
				".width-full .caption-wrapper",
				".width-full table",
				".width-full pre",
				".marginnote"
			],

			// Constrain margin notes within these
			constrainMarginNotesWithinSelectors: [
				".backlink-context",
				".margin-notes-block",
				".footnote",
				".sidenote > *"
			]
		},

		/******************/
		/*	State.
		 */
		sidenotes: null,
		citations: null,
		sidenoteColumnLeft: null,
		sidenoteColumnRight: null,
		positionUpdateQueued: false,
		mediaQueries: {},

		/*****************/
		/* Utilities.
		 */

		/**
		 * Log messages with level filtering.
		 * Levels: 0 = error, 1 = warn, 2+ = debug (development only)
		 * Production shows levels 0-1 only. Set DEBUG = true for development logging.
		 */
		DEBUG: false, // DEV: Set to true for development logging

		log: (message, level = 2) => {
			if (!console) return;

			const maxLevel = SidenotesStandalone.DEBUG ? 99 : 1;
			if (level > maxLevel) return;

			if (level === 0) {
				console.error(`[Sidenotes] ${message}`);
			} else if (level === 1) {
				console.warn(`[Sidenotes] ${message}`);
			} else {
				// DEV: Debug logging (only when DEBUG = true)
				console.log(`[Sidenotes] ${message}`);
			}
		},

		newElement: (tag, attrs = {}, props = {}) => {
			const element = document.createElement(tag);
			Object.entries(attrs).forEach(([key, value]) => {
				if (key === 'class') {
					element.className = Array.isArray(value) ? value.join(' ') : value;
				} else {
					element.setAttribute(key, value);
				}
			});
			Object.entries(props).forEach(([key, value]) => {
				element[key] = value;
			});
			return element;
		},

		/*****************/
		/* Note utilities.
		 */

		noteNumber: (element) => {
			if (!element) return null;

			// Extract number from id like "fnref1", "fn1", "sn1"
			const match = element.id?.match(/(?:fnref|fn|sn)(\d+)/);
			return match ? match[1] : null;
		},

		footnoteIdForNumber: (number) => `fn${number}`,
		sidenoteIdForNumber: (number) => `sn${number}`,
		citationIdForNumber: (number) => `fnref${number}`,

		sidenoteOfNumber: (number) => {
			return SidenotesStandalone.sidenotes?.find(sn =>
				SidenotesStandalone.noteNumber(sn) == number
			) ?? null;
		},

		citationOfNumber: (number) => {
			return SidenotesStandalone.citations?.find(cit =>
				SidenotesStandalone.noteNumber(cit) == number
			) ?? null;
		},

		counterpart: (element) => {
			if (!element) return null;

			const number = SidenotesStandalone.noteNumber(element);
			return element.classList.contains('sidenote')
				? SidenotesStandalone.citationOfNumber(number)
				: SidenotesStandalone.sidenoteOfNumber(number);
		},

		/*****************/
		/* Layout utilities.
		 */

		isWithinCollapsedBlock: (element) => {
			// Simplified - no collapse block support in standalone
			return false;
		},

		/*****************/
		/* Positioning.
		 */

		updateSidenotePositionsIfNeeded: () => {
			if (!SidenotesStandalone.sidenoteColumnLeft && !SidenotesStandalone.sidenoteColumnRight)
				return;

			if (SidenotesStandalone.positionUpdateQueued)
				return;

			SidenotesStandalone.positionUpdateQueued = true;
			requestIdleCallback(() => {
				SidenotesStandalone.positionUpdateQueued = false;
				SidenotesStandalone.updateSidenotePositions();
			});
		},

		updateSidenoteDispositions: () => {
			const config = SidenotesStandalone.config;

			for (let [index, sidenote] of SidenotesStandalone.sidenotes.entries()) {
				// Hide sidenotes within collapsed blocks (none in standalone version)
				sidenote.classList.toggle('hidden', SidenotesStandalone.isWithinCollapsedBlock(
					SidenotesStandalone.citations[index]
				));

				// Determine which side the sidenote should go on
				const sidenoteNumber = parseInt(SidenotesStandalone.noteNumber(sidenote));
				let side = null;

				if (config.useLeftColumn && !config.useRightColumn) {
					side = SidenotesStandalone.sidenoteColumnLeft;
				} else if (!config.useLeftColumn && config.useRightColumn) {
					side = SidenotesStandalone.sidenoteColumnRight;
				} else if (config.useLeftColumn && config.useRightColumn) {
					// Odd - left; even - right
					side = (sidenoteNumber % 2)
						? SidenotesStandalone.sidenoteColumnLeft
						: SidenotesStandalone.sidenoteColumnRight;
				}

				// Inject sidenote into column if needed
				if (sidenote.parentElement != side && side) {
					side.append(sidenote);
				}
			}
		},

		updateSidenotePositions: () => {
			SidenotesStandalone.log("updateSidenotePositions", 2); // DEV: Debug - called frequently

			const config = SidenotesStandalone.config;

			// Check viewport width
			if (!SidenotesStandalone.mediaQueries.viewportWidthBreakpoint.matches)
				return;

			// Update dispositions
			SidenotesStandalone.updateSidenoteDispositions();

			// Get column bounding rects
			const leftColumnBoundingRect = SidenotesStandalone.sidenoteColumnLeft.getBoundingClientRect();
			const rightColumnBoundingRect = SidenotesStandalone.sidenoteColumnRight.getBoundingClientRect();

			// Find proscribed vertical ranges (areas where sidenotes can't go)
			let proscribedVerticalRangesLeft = [];
			let proscribedVerticalRangesRight = [];

			document.querySelectorAll(config.potentiallyOverlappingElementsSelectors.join(", ")).forEach(element => {
				if (SidenotesStandalone.isWithinCollapsedBlock(element))
					return;

				const elementBoundingRect = element.getBoundingClientRect();

				if (!(elementBoundingRect.left > leftColumnBoundingRect.right ||
					  elementBoundingRect.right < leftColumnBoundingRect.left)) {
					proscribedVerticalRangesLeft.push({
						top: (elementBoundingRect.top - config.sidenoteSpacing) - leftColumnBoundingRect.top,
						bottom: (elementBoundingRect.bottom + config.sidenoteSpacing) - leftColumnBoundingRect.top,
						element: element
					});
				}

				if (!(elementBoundingRect.left > rightColumnBoundingRect.right ||
					  elementBoundingRect.right < rightColumnBoundingRect.left)) {
					proscribedVerticalRangesRight.push({
						top: (elementBoundingRect.top - config.sidenoteSpacing) - rightColumnBoundingRect.top,
						bottom: (elementBoundingRect.bottom + config.sidenoteSpacing) - rightColumnBoundingRect.top,
						element: element
					});
				}
			});

			// Add bottom edges as proscribed ranges
			proscribedVerticalRangesLeft.push({
				top: SidenotesStandalone.sidenoteColumnLeft.clientHeight,
				bottom: SidenotesStandalone.sidenoteColumnLeft.clientHeight
			});
			proscribedVerticalRangesRight.push({
				top: SidenotesStandalone.sidenoteColumnRight.clientHeight,
				bottom: SidenotesStandalone.sidenoteColumnRight.clientHeight
			});

			// Sort and merge ranges
			[proscribedVerticalRangesLeft, proscribedVerticalRangesRight].forEach(ranges => {
				ranges.sort((a, b) => a.top - b.top);

				for (let i = 0; i < ranges.length - 1; i++) {
					const thisRange = ranges[i];
					const nextRange = ranges[i + 1];

					if (nextRange.top <= thisRange.bottom) {
						thisRange.bottom = nextRange.bottom;
						ranges.splice(i + 1, 1);
						i++;
					}
				}
			});

			// Mark cut-off sidenotes
			SidenotesStandalone.sidenotes.forEach(sidenote => {
				const sidenoteOuterWrapper = sidenote.firstElementChild;
				sidenote.classList.toggle('cut-off',
					sidenoteOuterWrapper.scrollHeight > sidenoteOuterWrapper.offsetHeight + 2
				);
			});

			// Construct layout cells
			let layoutCells = [];
			let columnSpecs = [];

			if (config.useLeftColumn)
				columnSpecs.push([SidenotesStandalone.sidenoteColumnLeft, leftColumnBoundingRect, proscribedVerticalRangesLeft]);
			if (config.useRightColumn)
				columnSpecs.push([SidenotesStandalone.sidenoteColumnRight, rightColumnBoundingRect, proscribedVerticalRangesRight]);

			columnSpecs.forEach(columnSpec => {
				const [column, columnRect, proscribedVerticalRanges] = columnSpec;
				let prevRangeBottom = 0;

				proscribedVerticalRanges.forEach(range => {
					layoutCells.push({
						sidenotes: [],
						column: column,
						columnRect: columnRect,
						left: columnRect.left,
						right: columnRect.right,
						width: columnRect.width,
						top: columnRect.top + prevRangeBottom,
						bottom: columnRect.top + range.top,
						height: range.top - prevRangeBottom,
						room: range.top - prevRangeBottom
					});

					prevRangeBottom = range.bottom;
				});
			});

			// Default position for sidenote in cell
			const defaultNotePosInCellForCitation = (cell, citation) => {
				return Math.max(0, Math.round((citation.getBoundingClientRect().top - cell.top) + 4));
			};

			// Assign sidenotes to layout cells
			for (let [index, citation] of SidenotesStandalone.citations.entries()) {
				const sidenote = SidenotesStandalone.sidenotes[index];

				if (sidenote.classList.contains('hidden'))
					continue;

				// Get cells that fit this sidenote
				const fittingLayoutCells = layoutCells.filter(cell =>
					cell.room >= sidenote.offsetHeight
				);

				if (fittingLayoutCells.length == 0) {
					SidenotesStandalone.log("Too many sidenotes - cannot fit all", 1); // PROD: Warning
					SidenotesStandalone.sidenotes.forEach(sn => sn.remove());
					return;
				}

				// Sort cells by best fit
				const citationBoundingRect = citation.getBoundingClientRect();

				const vDistanceToCell = (cell) => {
					if (citationBoundingRect.top > cell.top && citationBoundingRect.top < cell.bottom)
						return 0;
					return citationBoundingRect.top < cell.top
						? Math.abs(citationBoundingRect.top - cell.top)
						: Math.abs(citationBoundingRect.top - cell.bottom);
				};

				const hDistanceToCell = (cell) => {
					return Math.abs(citationBoundingRect.left - (cell.left + cell.width / 2));
				};

				const overlapWithNote = (cell, note) => {
					const notePosInCell = defaultNotePosInCellForCitation(cell, citation);
					const otherNoteCitation = SidenotesStandalone.counterpart(note);
					const otherNotePosInCell = defaultNotePosInCellForCitation(cell, otherNoteCitation);

					return (otherNotePosInCell > notePosInCell + sidenote.offsetHeight + config.sidenoteSpacing ||
							notePosInCell > otherNotePosInCell + note.offsetHeight + config.sidenoteSpacing)
						? 0
						: Math.max(
							notePosInCell + sidenote.offsetHeight + config.sidenoteSpacing - otherNotePosInCell,
							otherNotePosInCell + note.offsetHeight + config.sidenoteSpacing - notePosInCell
						);
				};

				const cellCrowdedness = (cell) => {
					return cell.sidenotes.reduce((total, note) => total + overlapWithNote(cell, note), 0);
				};

				fittingLayoutCells.sort((cellA, cellB) => {
					return ((vDistanceToCell(cellA) + cellCrowdedness(cellA)) -
							(vDistanceToCell(cellB) + cellCrowdedness(cellB))) ||
						   (hDistanceToCell(cellA) - hDistanceToCell(cellB));
				});

				const closestFittingLayoutCell = fittingLayoutCells[0];
				closestFittingLayoutCell.room -= (sidenote.offsetHeight + config.sidenoteSpacing);
				closestFittingLayoutCell.sidenotes.push(sidenote);
			}

			// Position sidenotes within cells
			const getDistance = (noteA, noteB) => {
				return noteB.posInCell - (noteA.posInCell + noteA.offsetHeight + config.sidenoteSpacing);
			};

			layoutCells.forEach(cell => {
				if (cell.sidenotes.length == 0)
					return;

				// Set default positions
				cell.sidenotes.forEach(sidenote => {
					const citation = SidenotesStandalone.counterpart(sidenote);
					sidenote.posInCell = defaultNotePosInCellForCitation(cell, citation);
				});

				// Sort sidenotes vertically
				cell.sidenotes.sort((noteA, noteB) => {
					return (noteA.posInCell - noteB.posInCell) ||
						   (parseInt(noteA.id.slice(2)) - parseInt(noteB.id.slice(2)));
				});

				// Helper functions for pushing notes up
				const shiftNotesUp = (noteIndexes, shiftUpDistance) => {
					noteIndexes.forEach(idx => {
						cell.sidenotes[idx].posInCell -= shiftUpDistance;
					});
				};

				const pushNotesUp = (pushUpWhich, pushUpForce, bruteStrength = false) => {
					const roomToPush = pushUpWhich[0] == 0
						? cell.sidenotes[pushUpWhich[0]].posInCell
						: Math.max(0, getDistance(cell.sidenotes[pushUpWhich[0] - 1], cell.sidenotes[pushUpWhich[0]]));

					const pushUpDistance = bruteStrength
						? pushUpForce
						: Math.floor(pushUpForce / pushUpWhich.length);

					if (pushUpDistance <= roomToPush) {
						shiftNotesUp(pushUpWhich, pushUpDistance);
						return pushUpForce - pushUpDistance;
					} else {
						shiftNotesUp(pushUpWhich, roomToPush);
						if (pushUpWhich[0] == 0)
							return pushUpForce - roomToPush;

						pushUpWhich.splice(0, 0, pushUpWhich[0] - 1);
						return pushNotesUp(pushUpWhich, pushUpForce - roomToPush, bruteStrength);
					}
				};

				// Resolve overlaps
				for (let i = 1; i < cell.sidenotes.length; i++) {
					const prevNote = cell.sidenotes[i - 1];
					const thisNote = cell.sidenotes[i];

					const overlapAbove = Math.max(0, -1 * getDistance(prevNote, thisNote));
					if (overlapAbove == 0)
						continue;

					const pushUpForce = Math.round(overlapAbove / 2);
					thisNote.posInCell += (overlapAbove - pushUpForce) + pushNotesUp([i - 1], pushUpForce);
				}

				// Check bottom overlap
				const overlapOfBottom = Math.max(0,
					(cell.sidenotes[cell.sidenotes.length - 1].posInCell +
					 cell.sidenotes[cell.sidenotes.length - 1].offsetHeight) - cell.height
				);
				if (overlapOfBottom > 0)
					pushNotesUp([cell.sidenotes.length - 1], overlapOfBottom, true);

				// Set positions via inline styles
				cell.sidenotes.forEach(sidenote => {
					sidenote.style.top = Math.round(sidenote.posInCell) +
						(cell.top - cell.columnRect.top) + 'px';
				});
			});

				// Un-hide columns
			SidenotesStandalone.sidenoteColumnLeft.style.visibility = '';
			SidenotesStandalone.sidenoteColumnRight.style.visibility = '';
		},

		/******************/
		/* Hover adjustment.
		 */

		adjustSidenotePositionOnHover: (sidenote) => {
			// Get viewport and sidenote dimensions
			const viewportHeight = window.innerHeight;
			const sidenoteRect = sidenote.getBoundingClientRect();
			const sidenoteOuterWrapper = sidenote.querySelector('.sidenote-outer-wrapper');

			if (!sidenoteOuterWrapper) return;

			const sidenoteContentHeight = sidenoteOuterWrapper.scrollHeight;
			const sidenoteTop = sidenoteRect.top;
			const sidenoteBottom = sidenoteRect.bottom;

			// Store original position if not already stored
			if (!sidenote.dataset.originalTop) {
				sidenote.dataset.originalTop = sidenote.style.top;
			}

			// Check if sidenote runs off top of screen
			if (sidenoteTop < 0) {
				const offscreenAmount = Math.abs(sidenoteTop);
				const currentTop = parseFloat(sidenote.style.top) || 0;

				// Slide down to bring top into view
				const newTop = currentTop + offscreenAmount + 20; // 20px padding
				sidenote.style.top = newTop + 'px';
				sidenote.style.transition = 'top 0.2s ease-out';
				sidenote.classList.add('position-adjusted');
				return;
			}

			// Check if sidenote runs off bottom of screen
			if (sidenoteBottom > viewportHeight) {
				const offscreenAmount = sidenoteBottom - viewportHeight;
				const currentTop = parseFloat(sidenote.style.top) || 0;

				// Slide up to bring bottom into view
				const newTop = currentTop - offscreenAmount - 20; // 20px padding

				// Make sure we don't slide past the top
				const wouldBeTop = sidenoteRect.top - offscreenAmount - 20;
				if (wouldBeTop >= 0) {
					sidenote.style.top = newTop + 'px';
					sidenote.style.transition = 'top 0.2s ease-out';
					sidenote.classList.add('position-adjusted');
				} else {
					// If sliding all the way up would go off top, slide as much as possible
					const maxSlideUp = sidenoteRect.top - 20;
					sidenote.style.top = (currentTop - maxSlideUp) + 'px';
					sidenote.style.transition = 'top 0.2s ease-out';
					sidenote.classList.add('position-adjusted');
				}
			}
		},

		resetSidenotePosition: (sidenote) => {
			// Restore original position
			if (sidenote.dataset.originalTop) {
				sidenote.style.top = sidenote.dataset.originalTop;
				sidenote.style.transition = 'top 0.2s ease-out';
				sidenote.classList.remove('position-adjusted');

				// Clean up after transition
				setTimeout(() => {
					if (!sidenote.classList.contains('position-adjusted')) {
						sidenote.style.transition = '';
					}
				}, 200);
			}
		},

		/*****************/
		/* Construction.
		 */

		deconstructSidenotes: () => {
			SidenotesStandalone.log("deconstructSidenotes", 2); // DEV: Debug - lifecycle

			SidenotesStandalone.sidenotes = null;
			SidenotesStandalone.citations = null;

			if (SidenotesStandalone.sidenoteColumnLeft) {
				SidenotesStandalone.sidenoteColumnLeft.remove();
				SidenotesStandalone.sidenoteColumnLeft = null;
			}

			if (SidenotesStandalone.sidenoteColumnRight) {
				SidenotesStandalone.sidenoteColumnRight.remove();
				SidenotesStandalone.sidenoteColumnRight = null;
			}
		},

		constructSidenotes: () => {
			SidenotesStandalone.log("constructSidenotes", 2); // DEV: Debug - lifecycle

			const config = SidenotesStandalone.config;
			const container = document.querySelector(config.containerSelector);

			if (!container) {
				SidenotesStandalone.log("Container not found: " + config.containerSelector, 0); // PROD: Error
				return;
			}

			// Create columns if needed
			if (!SidenotesStandalone.sidenoteColumnLeft && !SidenotesStandalone.sidenoteColumnRight) {
				SidenotesStandalone.sidenoteColumnLeft = SidenotesStandalone.newElement('DIV', {
					id: 'sidenote-column-left',
					class: 'footnotes sidenote-column'
				});
				SidenotesStandalone.sidenoteColumnLeft.style.visibility = 'hidden';

				SidenotesStandalone.sidenoteColumnRight = SidenotesStandalone.newElement('DIV', {
					id: 'sidenote-column-right',
					class: 'footnotes sidenote-column'
				});
				SidenotesStandalone.sidenoteColumnRight.style.visibility = 'hidden';

				container.append(SidenotesStandalone.sidenoteColumnLeft);
				container.append(SidenotesStandalone.sidenoteColumnRight);

				SidenotesStandalone.sidenotes = [];
				SidenotesStandalone.citations = [];
			}

			// Get all citations
			const allCitations = Array.from(document.querySelectorAll(config.citationSelector));
			const newCitations = allCitations.filter(citation => {
				return SidenotesStandalone.citationOfNumber(
					SidenotesStandalone.noteNumber(citation)
				) == null;
			});

			if (newCitations.length == 0)
				return;

			// Add citations
			SidenotesStandalone.citations.push(...newCitations);
			SidenotesStandalone.citations.sort((a, b) =>
				SidenotesStandalone.noteNumber(a) - SidenotesStandalone.noteNumber(b)
			);

			// Remove existing sidenotes
			SidenotesStandalone.sidenotes.forEach(sn => sn.remove());
			SidenotesStandalone.sidenotes = [];

			// Create sidenotes
			SidenotesStandalone.citations.forEach(citation => {
				const noteNumber = SidenotesStandalone.noteNumber(citation);
				const footnoteId = SidenotesStandalone.footnoteIdForNumber(noteNumber);
				const footnote = document.getElementById(footnoteId);

				if (!footnote) {
					SidenotesStandalone.log(`Footnote ${footnoteId} not found for citation`, 1); // PROD: Warning
					return;
				}

				// Create sidenote
				const sidenote = SidenotesStandalone.newElement('DIV', {
					class: 'sidenote',
					id: SidenotesStandalone.sidenoteIdForNumber(noteNumber)
				});
				sidenote.style.visibility = 'hidden';

				// Create wrappers
				const outerWrapper = SidenotesStandalone.newElement('DIV', {
					class: 'sidenote-outer-wrapper'
				});
				const innerWrapper = SidenotesStandalone.newElement('DIV', {
					class: 'sidenote-inner-wrapper'
				});

				outerWrapper.appendChild(innerWrapper);
				sidenote.appendChild(outerWrapper);

				// Create self-link
				const selfLink = SidenotesStandalone.newElement('A', {
					class: 'sidenote-self-link',
					href: '#' + SidenotesStandalone.sidenoteIdForNumber(noteNumber)
				}, {
					textContent: noteNumber
				});
				sidenote.appendChild(selfLink);

				// Copy footnote content (excluding self-link)
				const footnoteClone = footnote.cloneNode(true);
				const footnoteContent = Array.from(footnoteClone.childNodes).filter(node => {
					if (node.nodeType === Node.ELEMENT_NODE) {
						return !node.classList.contains('footnote-self-link');
					}
					return true;
				});

				footnoteContent.forEach(node => innerWrapper.appendChild(node));

				// Add to array
				SidenotesStandalone.sidenotes.push(sidenote);

				// Bind hover events for bidirectional highlighting
				// When hovering over sidenote, highlight both sidenote and citation
				sidenote.addEventListener('mouseenter', () => {
					citation.classList.add('highlighted');
					sidenote.classList.add('highlighted', 'hovering');

					// Check if sidenote runs off screen and adjust position
					SidenotesStandalone.adjustSidenotePositionOnHover(sidenote);
				});

				sidenote.addEventListener('mouseleave', () => {
					citation.classList.remove('highlighted');
					sidenote.classList.remove('highlighted', 'hovering');

					// Reset to original position
					SidenotesStandalone.resetSidenotePosition(sidenote);
				});

				// When hovering over citation, highlight both citation and sidenote
				citation.addEventListener('mouseenter', () => {
					citation.classList.add('highlighted');
					sidenote.classList.add('highlighted', 'hovering');

					// Check if sidenote runs off screen and adjust position
					SidenotesStandalone.adjustSidenotePositionOnHover(sidenote);
				});

				citation.addEventListener('mouseleave', () => {
					citation.classList.remove('highlighted');
					sidenote.classList.remove('highlighted', 'hovering');

					// Reset to original position
					SidenotesStandalone.resetSidenotePosition(sidenote);
				});

				// Intercept clicks on citation to scroll to sidenote instead of footnote
				citation.addEventListener('click', (event) => {
					// Only intercept if sidenotes are currently active
					if (SidenotesStandalone.mediaQueries.viewportWidthBreakpoint.matches) {
						event.preventDefault();

						// Update hash to sidenote
						const sidenoteId = SidenotesStandalone.sidenoteIdForNumber(noteNumber);
						history.pushState(null, '', '#' + sidenoteId);

						// Scroll sidenote into view with some padding
						const sidenotePadding = SidenotesStandalone.config.sidenotePadding;
						const sidenoteRect = sidenote.getBoundingClientRect();
						const scrollOffset = window.scrollY + sidenoteRect.top - sidenotePadding - 10;

						window.scrollTo({
							top: scrollOffset,
							behavior: 'smooth'
						});

						// Add temporary visual feedback
						sidenote.classList.add('targeted');
						setTimeout(() => {
							sidenote.classList.remove('targeted');
						}, 2000);
					}
				});
			});

			// Update dispositions
			SidenotesStandalone.updateSidenoteDispositions();

			// Update positions after layout
			requestAnimationFrame(() => {
				SidenotesStandalone.updateSidenotePositions();

				// Make sidenotes visible
				SidenotesStandalone.sidenotes.forEach(sn => {
					sn.style.visibility = '';
				});
			});
		},

		/*****************/
		/* Initialization.
		 */

		updateMarginNoteStyle: () => {
			const config = SidenotesStandalone.config;

			document.querySelectorAll('.marginnote').forEach(marginNote => {
				const inline = marginNote.closest(config.constrainMarginNotesWithinSelectors.join(', ')) ||
							   !SidenotesStandalone.mediaQueries.marginNoteViewportWidthBreakpoint.matches;

				if (inline) {
					marginNote.classList.remove('sidenote');
					marginNote.classList.add('inline');
				} else {
					marginNote.classList.remove('inline');
					marginNote.classList.add('sidenote');
				}
			});
		},

		setup: () => {
			SidenotesStandalone.log("setup", 2); // DEV: Debug - lifecycle

			const config = SidenotesStandalone.config;

			// Create media queries
			SidenotesStandalone.mediaQueries.viewportWidthBreakpoint =
				matchMedia(`(min-width: ${config.minimumViewportWidthForSidenotes}px)`);
			SidenotesStandalone.mediaQueries.marginNoteViewportWidthBreakpoint =
				matchMedia(`(min-width: ${config.minimumViewportWidthForSidenoteMarginNotes}px)`);

			// Handle viewport width changes for sidenotes
			const handleSidenoteViewportChange = (mq) => {
				if (mq.matches) {
					SidenotesStandalone.constructSidenotes();
				} else {
					SidenotesStandalone.deconstructSidenotes();
				}
			};

			SidenotesStandalone.mediaQueries.viewportWidthBreakpoint.addListener(handleSidenoteViewportChange);

			// Handle margin note style changes
			const handleMarginNoteViewportChange = () => {
				SidenotesStandalone.updateMarginNoteStyle();
			};

			SidenotesStandalone.mediaQueries.marginNoteViewportWidthBreakpoint.addListener(handleMarginNoteViewportChange);

			// Initial setup
			if (SidenotesStandalone.mediaQueries.viewportWidthBreakpoint.matches) {
				SidenotesStandalone.constructSidenotes();
			}

			SidenotesStandalone.updateMarginNoteStyle();

			// Add resize listener
			let resizeTimeout;
			window.addEventListener('resize', () => {
				clearTimeout(resizeTimeout);
				resizeTimeout = setTimeout(() => {
					if (SidenotesStandalone.mediaQueries.viewportWidthBreakpoint.matches) {
						SidenotesStandalone.updateSidenotePositionsIfNeeded();
					}
				}, 100);
			});

			// Add scroll listener for reflow
			let scrollTimeout;
			window.addEventListener('scroll', () => {
				clearTimeout(scrollTimeout);
				scrollTimeout = setTimeout(() => {
					if (SidenotesStandalone.mediaQueries.viewportWidthBreakpoint.matches) {
						SidenotesStandalone.updateSidenotePositionsIfNeeded();
					}
				}, 150);
			}, {passive: true});

			SidenotesStandalone.log("setup complete", 2); // DEV: Debug - lifecycle
		},

		init: (customConfig = {}) => {
			// Merge custom config
			Object.assign(SidenotesStandalone.config, customConfig);

			// Wait for DOM to be ready
			if (document.readyState === 'loading') {
				document.addEventListener('DOMContentLoaded', () => {
					SidenotesStandalone.setup();
				});
			} else {
				SidenotesStandalone.setup();
			}
		}
	};

	// Expose globally
	window.SidenotesStandalone = SidenotesStandalone;

	// Auto-initialize if no config needed
	SidenotesStandalone.init();

})();
