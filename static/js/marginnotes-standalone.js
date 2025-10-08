/**
 * Standalone Margin Notes Implementation
 * Processes .marginnote elements for responsive display
 */

(function () {
  'use strict';

  const MarginNotes = {
    // Configuration
    config: {
      breakpoint: 1497, // px - when to switch from inline to sidenote
    },

    /**
     * Initialize margin notes processing
     */
    init() {
      // Wait for DOM to be ready
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => this.process());
      } else {
        this.process();
      }
    },

    /**
     * Process all margin notes in the document
     */
    process() {
      this.wrapMarginNotes();
      // Note: Display mode (inline/sidenote) is managed by sidenotes-standalone.js
    },

    /**
     * Wrap margin note contents and calculate positions
     */
    wrapMarginNotes() {
      document.querySelectorAll('.marginnote').forEach((marginnote) => {
        // Skip if already processed
        if (marginnote.querySelector('.marginnote-inner-wrapper')) {
          return;
        }

        // Create inner wrapper
        const innerWrapper = document.createElement('span');
        innerWrapper.className = 'marginnote-inner-wrapper';

        // Move all child nodes into wrapper
        while (marginnote.firstChild) {
          innerWrapper.appendChild(marginnote.firstChild);
        }
        marginnote.appendChild(innerWrapper);

        // Check if it's icon-only (single character or emoji)
        if (innerWrapper.textContent.trim().length <= 1) {
          marginnote.classList.add('only-icon');
        }

        // Get containing paragraph
        const graf = marginnote.closest('p');
        if (!graf) return;

        // Mark paragraph as containing a margin note
        graf.classList.add('has-margin-note');

        // Calculate position within paragraph
        const nodesBefore = [];
        for (let i = 0; i < graf.childNodes.length; i++) {
          const node = graf.childNodes[i];
          if (
            marginnote.compareDocumentPosition(node) &
            Node.DOCUMENT_POSITION_PRECEDING
          ) {
            if (
              node.nodeType === Node.ELEMENT_NODE ||
              node.nodeType === Node.TEXT_NODE
            ) {
              nodesBefore.push(node);
            }
          } else {
            break;
          }
        }

        const textBefore = nodesBefore.map((node) => node.textContent).join('');
        const totalText = graf.textContent;
        const fractionalPosition = textBefore.length / totalText.length;
        const percentPosition = Math.round(100 * fractionalPosition);

        marginnote.style.setProperty(
          '--marginnote-vertical-position',
          `${percentPosition}%`
        );
      });
    },
  };

  // Auto-initialize
  MarginNotes.init();

  // Expose globally if needed
  window.MarginNotes = MarginNotes;
})();
