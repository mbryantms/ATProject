'use strict';

/**
 * Search module — command palette modal (Cmd+K) and search page enhancement.
 *
 * Creates a modal overlay with as-you-type search results grouped by type
 * (Posts, Tags, Pages). Keyboard navigable. Links to full search page
 * via "View all N results."
 */
(function () {
  /* ── State ─────────────────────────────────────────────── */

  var isOpen = false;
  var selectedIndex = -1;
  var totalResults = 0;
  var abortController = null;
  var debounceTimer = null;

  /* ── DOM refs (set in setup) ───────────────────────────── */

  var overlay = null;
  var modal = null;
  var input = null;
  var resultsContainer = null;
  var footer = null;

  /* ── Constants ─────────────────────────────────────────── */

  var DEBOUNCE_MS = 200;
  var MIN_CHARS = 2;
  var API_URL = '/api/v1/search/';

  var SEARCH_ICON =
    '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>';

  /* ── Setup ─────────────────────────────────────────────── */

  function setup() {
    createModal();
    bindGlobalShortcut();
    bindTriggerButtons();
    enhanceSearchPage();
    applyHighlightsFromURL();
  }

  function createModal() {
    // Overlay
    overlay = document.createElement('div');
    overlay.className = 'search-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-label', 'Search');
    overlay.hidden = true;

    // Modal container
    modal = document.createElement('div');
    modal.className = 'search-modal';

    // Input area
    var inputWrap = document.createElement('div');
    inputWrap.className = 'search-input-wrap';
    inputWrap.innerHTML = SEARCH_ICON;

    input = document.createElement('input');
    input.className = 'search-input';
    input.type = 'text';
    input.placeholder = 'Search Architextual\u2026';
    input.setAttribute('aria-label', 'Search query');
    input.setAttribute('autocomplete', 'off');
    input.setAttribute('spellcheck', 'false');
    inputWrap.appendChild(input);

    // Results
    resultsContainer = document.createElement('div');
    resultsContainer.className = 'search-results';
    resultsContainer.setAttribute('role', 'listbox');
    resultsContainer.setAttribute('aria-label', 'Search results');

    // Footer
    footer = document.createElement('div');
    footer.className = 'search-footer';
    footer.hidden = true;

    modal.appendChild(inputWrap);
    modal.appendChild(resultsContainer);
    modal.appendChild(footer);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    // Events
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) close();
    });
    input.addEventListener('input', handleInput);
    input.addEventListener('keydown', handleKeyDown);
  }

  function bindGlobalShortcut() {
    document.addEventListener('keydown', function (e) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        toggle();
      }
      if (e.key === 'Escape' && isOpen) {
        e.preventDefault();
        close();
      }
    });
  }

  function bindTriggerButtons() {
    document.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-search-trigger]');
      if (btn) {
        e.preventDefault();
        open();
      }
    });
  }

  /* ── Open / Close ──────────────────────────────────────── */

  function open() {
    if (isOpen) return;
    isOpen = true;
    overlay.hidden = false;
    document.body.style.overflow = 'hidden';
    input.value = '';
    resultsContainer.innerHTML = '';
    footer.hidden = true;
    selectedIndex = -1;
    totalResults = 0;
    // Focus after a microtask so the browser paints the overlay first
    requestAnimationFrame(function () {
      input.focus();
    });
  }

  function close() {
    if (!isOpen) return;
    isOpen = false;
    overlay.hidden = true;
    document.body.style.overflow = '';
    if (abortController) {
      abortController.abort();
      abortController = null;
    }
    clearTimeout(debounceTimer);
  }

  function toggle() {
    isOpen ? close() : open();
  }

  /* ── Search logic ──────────────────────────────────────── */

  function handleInput() {
    clearTimeout(debounceTimer);
    var q = input.value.trim();
    if (q.length < MIN_CHARS) {
      resultsContainer.innerHTML = '';
      footer.hidden = true;
      selectedIndex = -1;
      totalResults = 0;
      return;
    }
    debounceTimer = setTimeout(function () {
      fetchResults(q);
    }, DEBOUNCE_MS);
  }

  function fetchResults(q) {
    if (abortController) abortController.abort();
    abortController = new AbortController();

    var url = API_URL + '?q=' + encodeURIComponent(q) + '&limit=5';

    fetch(url, { signal: abortController.signal })
      .then(function (res) {
        if (!res.ok) throw new Error('Search request failed');
        return res.json();
      })
      .then(function (data) {
        renderResults(data);
      })
      .catch(function (err) {
        if (err.name !== 'AbortError') {
          console.error('Search error:', err);
        }
      });
  }

  /* ── Rendering ─────────────────────────────────────────── */

  function renderResults(data) {
    resultsContainer.innerHTML = '';
    selectedIndex = -1;
    totalResults = 0;

    var posts = (data.results && data.results.posts) || [];
    var tags = (data.results && data.results.tags) || [];
    var pages = (data.results && data.results.pages) || [];

    if (posts.length === 0 && tags.length === 0 && pages.length === 0) {
      if (data.did_you_mean) {
        resultsContainer.innerHTML =
          '<div class="search-empty">No results found. Did you mean <a href="#" class="search-did-you-mean">' +
          escapeHtml(data.did_you_mean) +
          '</a>?</div>';
        var dymLink = resultsContainer.querySelector('.search-did-you-mean');
        if (dymLink) {
          dymLink.addEventListener('click', function (e) {
            e.preventDefault();
            input.value = data.did_you_mean;
            handleInput();
          });
        }
      } else {
        resultsContainer.innerHTML =
          '<div class="search-empty">No results found.</div>';
      }
      footer.hidden = true;
      return;
    }

    // Posts
    if (posts.length > 0) {
      appendGroup('Posts', posts, function (post) {
        var item = document.createElement('a');
        item.href = addHighlightParam(post.url, currentQuery());
        item.className = 'search-result-item';
        item.setAttribute('role', 'option');

        var titleEl = document.createElement('div');
        titleEl.className = 'search-result-title';
        titleEl.textContent = post.title;
        item.appendChild(titleEl);

        if (post.snippet) {
          var snippetEl = document.createElement('div');
          snippetEl.className = 'search-result-snippet';
          snippetEl.innerHTML = post.snippet;
          item.appendChild(snippetEl);
        }

        var metaEl = document.createElement('div');
        metaEl.className = 'search-result-meta';
        var metaParts = [];
        if (post.tags && post.tags.length > 0) {
          metaParts.push(
            post.tags
              .slice(0, 3)
              .map(function (t) {
                return t.name;
              })
              .join(' \u00b7 '),
          );
        }
        if (post.reading_time) {
          metaParts.push(post.reading_time + ' min');
        }
        metaEl.textContent = metaParts.join(' \u2014 ');
        item.appendChild(metaEl);

        return item;
      });
    }

    // Tags
    if (tags.length > 0) {
      appendGroup('Tags', tags, function (tag) {
        var item = document.createElement('a');
        item.href = addHighlightParam(tag.url, currentQuery());
        item.className = 'search-result-item';
        item.setAttribute('role', 'option');

        var titleEl = document.createElement('div');
        titleEl.className = 'search-result-title';
        titleEl.textContent = tag.name;

        var countEl = document.createElement('span');
        countEl.className = 'search-result-count';
        countEl.textContent = ' (' + tag.post_count + ')';
        titleEl.appendChild(countEl);

        item.appendChild(titleEl);
        return item;
      });
    }

    // Pages
    if (pages.length > 0) {
      appendGroup('Pages', pages, function (page) {
        var item = document.createElement('a');
        item.href = addHighlightParam(page.url, currentQuery());
        item.className = 'search-result-item';
        item.setAttribute('role', 'option');

        var titleEl = document.createElement('div');
        titleEl.className = 'search-result-title';
        titleEl.textContent = page.title;
        item.appendChild(titleEl);

        return item;
      });
    }

    // Footer
    footer.hidden = false;
    footer.innerHTML = '';

    var viewAll = document.createElement('a');
    viewAll.href = '/search/?q=' + encodeURIComponent(input.value.trim());
    viewAll.className = 'search-view-all';
    viewAll.textContent =
      'View all ' + data.total + ' result' + (data.total !== 1 ? 's' : '') + ' \u2192';
    viewAll.addEventListener('click', function () {
      close();
    });

    var hints = document.createElement('span');
    hints.className = 'search-hints';
    hints.innerHTML =
      '<kbd>\u2191\u2193</kbd> navigate <kbd>\u23ce</kbd> select <kbd>esc</kbd> close';

    footer.appendChild(viewAll);
    footer.appendChild(hints);
  }

  function appendGroup(label, items, buildItem) {
    var header = document.createElement('div');
    header.className = 'search-group-header';
    header.textContent = label;
    resultsContainer.appendChild(header);

    items.forEach(function (item) {
      var el = buildItem(item);
      var idx = totalResults;
      el.dataset.resultIndex = idx;

      el.addEventListener('mouseenter', function () {
        selectResult(idx);
      });

      resultsContainer.appendChild(el);
      totalResults++;
    });
  }

  /* ── Keyboard navigation ───────────────────────────────── */

  function handleKeyDown(e) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      selectResult(selectedIndex < totalResults - 1 ? selectedIndex + 1 : 0);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      selectResult(selectedIndex > 0 ? selectedIndex - 1 : totalResults - 1);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      var selected = resultsContainer.querySelector('.search-result-item.selected');
      if (selected) {
        close();
        window.location.href = selected.href;
      } else if (input.value.trim().length >= MIN_CHARS) {
        close();
        window.location.href = '/search/?q=' + encodeURIComponent(input.value.trim());
      }
    }
  }

  function selectResult(idx) {
    // Deselect current
    var items = resultsContainer.querySelectorAll('.search-result-item');
    items.forEach(function (el) {
      el.classList.remove('selected');
    });

    selectedIndex = idx;
    if (idx >= 0 && idx < items.length) {
      items[idx].classList.add('selected');
      items[idx].scrollIntoView({ block: 'nearest' });
    }
  }

  /* ── Search page enhancement ───────────────────────────── */

  function enhanceSearchPage() {
    var pageInput = document.querySelector('[data-search-page-input]');
    if (!pageInput) return;

    var pageResults = document.querySelector('[data-search-page-results]');
    if (!pageResults) return;

    var pageDebounce = null;
    var pageAbort = null;

    pageInput.addEventListener('input', function () {
      clearTimeout(pageDebounce);
      var q = pageInput.value.trim();
      if (q.length < MIN_CHARS) return;

      pageDebounce = setTimeout(function () {
        if (pageAbort) pageAbort.abort();
        pageAbort = new AbortController();

        // Update URL without reload
        var url = new URL(window.location);
        url.searchParams.set('q', q);
        history.replaceState(null, '', url);

        fetch(API_URL + '?q=' + encodeURIComponent(q) + '&limit=20', {
          signal: pageAbort.signal,
        })
          .then(function (res) {
            if (!res.ok) throw new Error('Search request failed');
            return res.json();
          })
          .then(function (data) {
            renderPageResults(pageResults, data);
          })
          .catch(function (err) {
            if (err.name !== 'AbortError') console.error('Search error:', err);
          });
      }, DEBOUNCE_MS);
    });
  }

  function renderPageResults(container, data) {
    var posts = (data.results && data.results.posts) || [];
    var pages = (data.results && data.results.pages) || [];
    var tags = (data.results && data.results.tags) || [];
    container.innerHTML = '';

    if (posts.length === 0 && pages.length === 0 && tags.length === 0) {
      var empty = document.createElement('p');
      empty.className = 'search-page-empty';
      if (data.did_you_mean) {
        empty.textContent =
          'No results found. Did you mean "' + data.did_you_mean + '"?';
      } else {
        empty.textContent = 'No results found.';
      }
      container.appendChild(empty);
      return;
    }

    var heading = document.createElement('p');
    heading.className = 'search-page-count';
    var totalCount = data.total || posts.length + pages.length + tags.length;
    heading.textContent =
      totalCount + ' result' + (totalCount !== 1 ? 's' : '') + ' found';
    container.appendChild(heading);

    var pi = document.querySelector('[data-search-page-input]');
    var queryStr = pi ? pi.value.trim() : data.query || '';

    // Pages
    if (pages.length > 0) {
      var pagesHeader = document.createElement('h2');
      pagesHeader.className = 'search-page-section-header';
      pagesHeader.textContent = 'Pages';
      container.appendChild(pagesHeader);

      pages.forEach(function (page) {
        var card = document.createElement('a');
        card.className = 'search-page-result';
        card.href = page.url;

        var title = document.createElement('div');
        title.className = 'search-page-result-title';
        title.textContent = page.title;
        card.appendChild(title);

        container.appendChild(card);
      });
    }

    // Tags
    if (tags.length > 0) {
      var tagsHeader = document.createElement('h2');
      tagsHeader.className = 'search-page-section-header';
      tagsHeader.textContent = 'Tags';
      container.appendChild(tagsHeader);

      tags.forEach(function (tag) {
        var card = document.createElement('a');
        card.className = 'search-page-result';
        card.href = tag.url;

        var title = document.createElement('div');
        title.className = 'search-page-result-title';
        title.textContent = tag.name;

        var countEl = document.createElement('span');
        countEl.className = 'search-result-count';
        countEl.textContent = ' (' + tag.post_count + ')';
        title.appendChild(countEl);
        card.appendChild(title);

        if (tag.description) {
          var desc = document.createElement('div');
          desc.className = 'search-page-result-snippet';
          desc.textContent = tag.description;
          card.appendChild(desc);
        }

        container.appendChild(card);
      });
    }

    // Posts
    if (posts.length > 0) {
      var postsHeader = document.createElement('h2');
      postsHeader.className = 'search-page-section-header';
      postsHeader.textContent = 'Posts';
      container.appendChild(postsHeader);

      posts.forEach(function (post) {
        var card = document.createElement('a');
        card.className = 'search-page-result';
        card.href = addHighlightParam(post.url, queryStr);

        var title = document.createElement('div');
        title.className = 'search-page-result-title';
        title.textContent = post.title;
        card.appendChild(title);

        if (post.snippet) {
          var snippet = document.createElement('div');
          snippet.className = 'search-page-result-snippet';
          snippet.innerHTML = post.snippet;
          card.appendChild(snippet);
        }

        var meta = document.createElement('div');
        meta.className = 'search-page-result-meta';
        var parts = [];
        if (post.published_at) {
          parts.push(new Date(post.published_at).toLocaleDateString());
        }
        if (post.reading_time) {
          parts.push(post.reading_time + ' min read');
        }
        if (post.tags && post.tags.length > 0) {
          parts.push(
            post.tags
              .map(function (t) {
                return t.name;
              })
              .join(', '),
          );
        }
        meta.textContent = parts.join(' \u2014 ');
        card.appendChild(meta);

        container.appendChild(card);
      });
    }
  }

  /* ── URL helpers ────────────────────────────────────────── */

  /**
   * Append ?highlight=<terms> to a destination URL, carrying the current
   * search query so the target page can mark up matching text.
   */
  function addHighlightParam(url, query) {
    if (!query) return url;
    // Strip field prefixes and quotes to get bare search terms
    var terms = query
      .replace(/\b(?:title|tag|author|category|series):\S+/g, '')
      .replace(/"/g, '')
      .trim();
    if (!terms) return url;
    var sep = url.indexOf('?') === -1 ? '?' : '&';
    return url + sep + 'highlight=' + encodeURIComponent(terms);
  }

  /** Return the current modal search query (bare terms only). */
  function currentQuery() {
    return input ? input.value.trim() : '';
  }

  /* ── Highlight on destination page ─────────────────────── */

  function applyHighlightsFromURL() {
    var params = new URLSearchParams(window.location.search);
    var raw = params.get('highlight');
    if (!raw) return;

    // Strip quotes and field prefixes (same cleanup as addHighlightParam)
    raw = raw
      .replace(/\b(?:title|tag|author|category|series):\S+/g, '')
      .replace(/"/g, '')
      .trim();

    var terms = raw
      .split(/\s+/)
      .filter(function (t) {
        return t.length >= 2;
      })
      .map(function (t) {
        return t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      });
    if (terms.length === 0) return;

    var pattern = new RegExp('(' + terms.join('|') + ')', 'gi');

    // Walk text nodes inside <article> (the main content area)
    var root = document.querySelector('article');
    if (!root) return;

    // Skip elements where highlighting would break things
    var SKIP = { SCRIPT: 1, STYLE: 1, TEXTAREA: 1, CODE: 1, PRE: 1, KBD: 1, MARK: 1 };

    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        if (SKIP[node.parentElement.tagName]) return NodeFilter.FILTER_REJECT;
        if (!pattern.test(node.nodeValue)) return NodeFilter.FILTER_REJECT;
        pattern.lastIndex = 0; // reset after test()
        return NodeFilter.FILTER_ACCEPT;
      },
    });

    // Collect nodes first (mutating during walk is unsafe)
    var textNodes = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode);

    var firstMark = null;

    textNodes.forEach(function (textNode) {
      var frag = document.createDocumentFragment();
      var text = textNode.nodeValue;
      var lastIndex = 0;
      pattern.lastIndex = 0;
      var match;
      while ((match = pattern.exec(text)) !== null) {
        // Text before match
        if (match.index > lastIndex) {
          frag.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));
        }
        // Wrapped match
        var mark = document.createElement('mark');
        mark.className = 'search-highlight';
        mark.textContent = match[0];
        frag.appendChild(mark);
        if (!firstMark) firstMark = mark;
        lastIndex = pattern.lastIndex;
      }
      // Remaining text
      if (lastIndex < text.length) {
        frag.appendChild(document.createTextNode(text.slice(lastIndex)));
      }
      textNode.parentNode.replaceChild(frag, textNode);
    });

    if (firstMark) {
      // Scroll to first match with a small offset
      requestAnimationFrame(function () {
        var rect = firstMark.getBoundingClientRect();
        window.scrollTo({
          top: window.scrollY + rect.top - 100,
          behavior: 'smooth',
        });
      });

      // Show a small banner to dismiss highlights
      showHighlightBanner(textNodes.length);
    }
  }

  function showHighlightBanner(count) {
    var banner = document.createElement('div');
    banner.className = 'search-highlight-banner';

    var text = document.createElement('span');
    text.textContent = count + ' match' + (count !== 1 ? 'es' : '') + ' highlighted';
    banner.appendChild(text);

    // Prev / Next navigation
    var nav = document.createElement('span');
    nav.className = 'search-highlight-nav';

    var currentIdx = 0;

    var prevBtn = document.createElement('button');
    prevBtn.textContent = '\u2191';
    prevBtn.title = 'Previous match';
    prevBtn.addEventListener('click', function () {
      var marks = document.querySelectorAll('mark.search-highlight');
      if (marks.length === 0) return;
      currentIdx = (currentIdx - 1 + marks.length) % marks.length;
      scrollToMark(marks[currentIdx]);
    });

    var nextBtn = document.createElement('button');
    nextBtn.textContent = '\u2193';
    nextBtn.title = 'Next match';
    nextBtn.addEventListener('click', function () {
      var marks = document.querySelectorAll('mark.search-highlight');
      if (marks.length === 0) return;
      currentIdx = (currentIdx + 1) % marks.length;
      scrollToMark(marks[currentIdx]);
    });

    nav.appendChild(prevBtn);
    nav.appendChild(nextBtn);
    banner.appendChild(nav);

    var dismiss = document.createElement('button');
    dismiss.className = 'search-highlight-dismiss';
    dismiss.textContent = '\u00d7';
    dismiss.title = 'Clear highlights';
    dismiss.addEventListener('click', function () {
      // Unwrap all <mark> highlights
      document.querySelectorAll('mark.search-highlight').forEach(function (mark) {
        var parent = mark.parentNode;
        parent.replaceChild(document.createTextNode(mark.textContent), mark);
        parent.normalize();
      });
      banner.remove();

      // Clean URL
      var url = new URL(window.location);
      url.searchParams.delete('highlight');
      history.replaceState(null, '', url);
    });
    banner.appendChild(dismiss);

    document.body.appendChild(banner);
  }

  function scrollToMark(el) {
    var rect = el.getBoundingClientRect();
    window.scrollTo({
      top: window.scrollY + rect.top - 100,
      behavior: 'smooth',
    });
  }

  /* ── Helpers ───────────────────────────────────────────── */

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  /* ── Init ──────────────────────────────────────────────── */

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setup);
  } else {
    setup();
  }
})();
