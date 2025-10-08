/**
 * Math Copy Button Functionality
 *
 * Handles copying LaTeX source from display block math equations to clipboard.
 * Works with MathJax-rendered equations that have copy buttons added by the
 * math_copy_button postprocessor.
 */

/*************/
/* CLIPBOARD */
/*************/

/*******************************************/
/*  Copy the provided text to the clipboard.
 */
function copyTextToClipboard(text) {
    let scratchpad = document.querySelector("#scratchpad");

    //  Perform copy operation.
    scratchpad.innerText = text;
    selectElementContents(scratchpad);
    document.execCommand("copy");
    scratchpad.innerText = "";
}

/****************************************************/
/*  Select the full contents of a given DOM element.
 */
function selectElementContents(element) {
    let range = document.createRange();
    range.selectNodeContents(element);
    let selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
}

/***************************************************/
/*  Create scratchpad for synthetic copy operations.
 */
doWhenDOMContentLoaded(() => {
    document.body.append(newElement("SPAN", { "id": "scratchpad" }));
});

/******************************/
/*  Create a new HTML element.
 */
function newElement(tagName, attributes = {}) {
    let element = document.createElement(tagName);
    for (let [attr, value] of Object.entries(attributes)) {
        element.setAttribute(attr, value);
    }
    return element;
}

/********************************************************/
/*  Run the provided function when DOM content is loaded.
 */
function doWhenDOMContentLoaded(f) {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', f);
    } else {
        f();
    }
}

/****************************************/
/*  Initialize math copy button handlers.
 */
doWhenDOMContentLoaded(() => {
    // Use event delegation on the document to handle all copy buttons
    document.addEventListener('click', function(event) {
        // Check if the clicked element is a copy button or inside one
        const button = event.target.closest('.block-button-bar button.copy');

        if (button) {
            event.preventDefault();
            event.stopPropagation();
            handleMathCopyClick(button);
        }
    }, true); // Use capture phase to catch events early
});

/************************************/
/*  Handle math copy button click.
 */
function handleMathCopyClick(button) {
    const title = button.getAttribute('title');

    // Extract LaTeX source from title attribute
    // Title format: "Copy LaTeX source of this equation to clipboard: <latex>"
    // Use [\s\S]* to match across newlines
    const match = title.match(/Copy LaTeX source of this equation to clipboard:\s*([\s\S]*)$/);

    if (!match) {
        console.error('Could not extract LaTeX source from button title:', title);
        return;
    }

    // Unescape HTML entities in the correct order
    const latexSource = match[1]
        .replace(/&quot;/g, '"')
        .replace(/&#x27;/g, "'")
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&amp;/g, '&')  // Must be last
        .trim();

    // Copy to clipboard
    if (navigator.clipboard && navigator.clipboard.writeText) {
        // Modern clipboard API
        navigator.clipboard.writeText(latexSource)
            .then(() => {
                showMathCopySuccess(button);
            })
            .catch(err => {
                console.error('Failed to copy LaTeX source:', err);
                fallbackMathCopy(latexSource, button);
            });
    } else {
        // Fallback for older browsers
        fallbackMathCopy(latexSource, button);
    }
}

/****************************************************/
/*  Fallback copy method using scratchpad element.
 */
function fallbackMathCopy(text, button) {
    let scratchpad = document.querySelector("#scratchpad");
    if (!scratchpad) {
        console.error('Scratchpad element not found for fallback copy');
        return;
    }

    scratchpad.innerText = text;
    selectElementContents(scratchpad);

    try {
        const successful = document.execCommand('copy');
        if (successful) {
            showMathCopySuccess(button);
        } else {
            console.error('Copy command was unsuccessful');
        }
    } catch (err) {
        console.error('Failed to copy LaTeX source:', err);
    }

    scratchpad.innerText = "";
}

/*********************************************/
/*  Show visual feedback for successful copy.
 */
function showMathCopySuccess(button) {
    // Find the parent math span and its mjx-container
    const mathSpan = button.closest('.math.display, .math.block');
    if (!mathSpan) return;

    const mjxContainer = mathSpan.querySelector('mjx-container[display="true"]');
    if (!mjxContainer) return;

    // Add flash class to trigger CSS animation
    mjxContainer.classList.add('flash');

    // Remove flash class after animation completes
    setTimeout(() => {
        mjxContainer.classList.remove('flash');
    }, 150);
}
