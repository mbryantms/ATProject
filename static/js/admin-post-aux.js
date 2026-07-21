// Post admin editor auxiliary behaviors.
//
// Relocated from inline <script> blobs that engine/admin/post.py used to
// inject through readonly-field HTML. Loaded once as an external file via
// PostAdmin.Media, so it is CSP-safe (the site's nonce policy blocks inline
// event handlers and un-nonced <script>). Each block already guards against
// double-binding and delegates from document, so a single load is correct.

// --- Citation-style help popover ---
(function () {
  if (window.__mkCsHelpBound) return;
  window.__mkCsHelpBound = true;
  document.addEventListener('click', function (e) {
    if (e.target && e.target.classList.contains('mk-citestyle-help-btn')) {
      e.preventDefault();
      var p = e.target.nextElementSibling;
      var shown = p.style.display === 'block';
      document.querySelectorAll('.mk-citestyle-help-panel').forEach(function (el) {
        el.style.display = 'none';
      });
      if (!shown) {
        p.style.display = 'block';
        var r = e.target.getBoundingClientRect();
        p.style.left = window.scrollX + r.left + 'px';
        p.style.top = window.scrollY + r.bottom + 6 + 'px';
      }
    } else if (!(e.target.closest && e.target.closest('.mk-citestyle-help-panel'))) {
      document.querySelectorAll('.mk-citestyle-help-panel').forEach(function (el) {
        el.style.display = 'none';
      });
    }
  });
})();

// --- Citation picker modal ---
(function () {
  if (window.__mkCitePickerBound) return;
  window.__mkCitePickerBound = true;

  var state = { results: [], selected: 0, savedCursor: null };

  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function openModal() {
    var m = document.getElementById('mk-cite-modal');
    if (!m) return;
    // Remember cursor position before focus is stolen.
    var view = window.__atpPostEditorView;
    if (view) state.savedCursor = view.state.selection.main.head;
    m.style.display = 'flex';
    var input = document.getElementById('mk-cite-search');
    if (input) {
      input.value = '';
      setTimeout(function () {
        input.focus();
      }, 0);
    }
    renderResults([]);
    fetchResults('');
  }

  function closeModal() {
    var m = document.getElementById('mk-cite-modal');
    if (m) m.style.display = 'none';
  }

  function renderResults(rows) {
    var out = document.getElementById('mk-cite-results');
    if (!out) return;
    state.results = rows;
    if (state.selected >= rows.length) state.selected = 0;
    if (!rows.length) {
      out.innerHTML =
        '<div style="padding:14px 16px;color:var(--body-quiet-color);">' +
        'No matches — create a new source below.</div>';
      return;
    }
    out.innerHTML = rows
      .map(function (r, i) {
        var meta = [r.author, r.year].filter(Boolean).join(' ');
        return (
          '<div class="mk-cite-row' +
          (i === state.selected ? ' mk-active' : '') +
          '" data-idx="' +
          i +
          '">' +
          '<code>' +
          escapeHtml(r.key) +
          '</code>' +
          '<div class="mk-cite-title" title="' +
          escapeHtml(r.title) +
          '">' +
          escapeHtml(r.title) +
          '</div>' +
          '<div class="mk-cite-meta">' +
          escapeHtml(meta) +
          '</div>' +
          '</div>'
        );
      })
      .join('');
  }

  var fetchTimer = null;
  function fetchResults(q) {
    var wrap = document.querySelector('.mk-cite-controls');
    if (!wrap) return;
    var url = wrap.getAttribute('data-cite-url');
    if (fetchTimer) clearTimeout(fetchTimer);
    fetchTimer = setTimeout(function () {
      fetch(url + '?q=' + encodeURIComponent(q), { credentials: 'same-origin' })
        .then(function (r) {
          return r.ok ? r.json() : { results: [] };
        })
        .then(function (data) {
          renderResults(data.results || []);
        })
        .catch(function () {
          renderResults([]);
        });
    }, 180);
  }

  function insertAt(key) {
    if (!key) return;
    var view = window.__atpPostEditorView;
    var insertText = '[@' + key + ']';
    if (!view) {
      // Fall back to textarea for authors without CM6 (just in case).
      var ta = document.getElementById('id_content_markdown');
      if (!ta) {
        closeModal();
        return;
      }
      var p = ta.selectionStart || 0;
      ta.value = ta.value.slice(0, p) + insertText + ta.value.slice(p);
      ta.selectionStart = ta.selectionEnd = p + insertText.length;
      closeModal();
      return;
    }
    var pos =
      state.savedCursor != null ? state.savedCursor : view.state.selection.main.head;
    pos = Math.max(0, Math.min(pos, view.state.doc.length));
    view.dispatch({
      changes: { from: pos, insert: insertText },
      selection: { anchor: pos + insertText.length },
    });
    view.focus();
    closeModal();
  }

  function moveSelection(delta) {
    if (!state.results.length) return;
    state.selected = Math.max(
      0,
      Math.min(state.results.length - 1, state.selected + delta),
    );
    renderResults(state.results);
    var active = document.querySelector('.mk-cite-row.mk-active');
    if (active) active.scrollIntoView({ block: 'nearest' });
  }

  // --- Create & insert (new source from DOI/URL/ISBN/title) ---

  function setCreateStatus(text, isError) {
    var el = document.getElementById('mk-cite-create-status');
    if (!el) return;
    el.textContent = text || '';
    el.classList.toggle('mk-error', !!isError);
  }

  function getCsrfToken() {
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    return input ? input.value : '';
  }

  function createAndInsert() {
    var input = document.getElementById('mk-cite-create-input');
    var btn = document.getElementById('mk-cite-create-btn');
    var wrap = document.querySelector('.mk-cite-controls');
    if (!input || !wrap) return;
    var identifier = (input.value || '').trim();
    if (!identifier) {
      setCreateStatus('Paste a DOI, URL, ISBN, or title first.', true);
      return;
    }
    var url = wrap.getAttribute('data-cite-create-url');
    if (!url) return;

    if (btn) btn.disabled = true;
    setCreateStatus('Looking up metadata…', false);

    fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken(),
      },
      body: JSON.stringify({ identifier: identifier }),
    })
      .then(function (r) {
        return r.json().then(function (data) {
          return { ok: r.ok, data: data };
        });
      })
      .then(function (res) {
        if (btn) btn.disabled = false;
        if (!res.ok || !res.data.key) {
          setCreateStatus(res.data.error || 'Could not create the source.', true);
          return;
        }
        input.value = '';
        setCreateStatus('', false);
        insertAt(res.data.key);
      })
      .catch(function () {
        if (btn) btn.disabled = false;
        setCreateStatus('Network error — try again.', true);
      });
  }

  document.addEventListener('click', function (e) {
    if (e.target && e.target.classList.contains('mk-cite-picker-btn')) {
      e.preventDefault();
      openModal();
      return;
    }
    if (e.target && e.target.id === 'mk-cite-create-btn') {
      e.preventDefault();
      createAndInsert();
      return;
    }
    if (e.target && e.target.id === 'mk-cite-close') {
      closeModal();
      return;
    }
    if (e.target && e.target.id === 'mk-cite-modal') {
      closeModal();
      return;
    }
    var row = e.target && e.target.closest && e.target.closest('.mk-cite-row');
    if (row) {
      var idx = parseInt(row.getAttribute('data-idx'), 10);
      if (!isNaN(idx) && state.results[idx]) insertAt(state.results[idx].key);
    }
  });

  document.addEventListener('input', function (e) {
    if (e.target && e.target.id === 'mk-cite-search') {
      fetchResults(e.target.value || '');
      state.selected = 0;
    }
  });

  document.addEventListener('keydown', function (e) {
    var modal = document.getElementById('mk-cite-modal');
    if (!modal || modal.style.display !== 'flex') return;
    if (e.key === 'Escape') {
      closeModal();
      return;
    }
    // Enter inside the create input triggers create, not result insertion.
    if (e.target && e.target.id === 'mk-cite-create-input') {
      if (e.key === 'Enter') {
        e.preventDefault();
        createAndInsert();
      }
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      moveSelection(1);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      moveSelection(-1);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      var r = state.results[state.selected];
      if (r) insertAt(r.key);
    }
  });
})();

// --- Markdown preview modal ---
(function () {
  if (window.__markdownPreviewBound) return;
  window.__markdownPreviewBound = true;

  function getCookie(name) {
    var cookies = document.cookie ? document.cookie.split('; ') : [];
    for (var i = 0; i < cookies.length; i++) {
      var parts = cookies[i].split('=');
      if (parts[0] === name) return decodeURIComponent(parts.slice(1).join('='));
    }
    return '';
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c];
    });
  }

  function openModal() {
    document.getElementById('markdown-preview-modal').style.display = 'flex';
  }
  function closeModal() {
    document.getElementById('markdown-preview-modal').style.display = 'none';
  }

  function renderLint(items) {
    var box = document.getElementById('markdown-preview-lint');
    if (!items || !items.length) {
      box.innerHTML = '';
      return;
    }
    var html = '<div class="mk-lint-box"><strong>⚠️ Lint warnings:</strong><ul>';
    items.forEach(function (m) {
      html += '<li>' + escapeHtml(m) + '</li>';
    });
    html += '</ul></div>';
    box.innerHTML = html;
  }

  function setIframeDoc(doc) {
    var iframe = document.getElementById('markdown-preview-iframe');
    iframe.srcdoc = doc;
  }

  function errorDoc(msg) {
    return (
      '<!DOCTYPE html><html><body style="font-family:system-ui;' +
      'padding:20px;color:#b00;">' +
      escapeHtml(msg) +
      '</body></html>'
    );
  }

  function loadingDoc() {
    return (
      '<!DOCTYPE html><html><body style="font-family:system-ui;' +
      'padding:20px;color:#888;"><em>Rendering…</em></body></html>'
    );
  }

  document.addEventListener('click', function (e) {
    if (e.target && e.target.classList.contains('markdown-preview-btn')) {
      e.preventDefault();
      var wrap = e.target.closest('.markdown-preview-controls');
      var url = wrap.getAttribute('data-preview-url');
      var postId = wrap.getAttribute('data-post-id');
      var textarea = document.getElementById('id_content_markdown');
      if (!textarea) {
        alert('Content textarea not found.');
        return;
      }

      setIframeDoc(loadingDoc());
      renderLint([]);
      openModal();

      var form = new FormData();
      form.append('content', textarea.value || '');
      if (postId) form.append('post_id', postId);

      fetch(url, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCookie('csrftoken') },
        body: form,
        credentials: 'same-origin',
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (json) {
          renderLint(json.lint || []);
          if (json.ok) {
            setIframeDoc(json.html);
          } else {
            setIframeDoc(errorDoc(json.error || 'Preview failed.'));
          }
        })
        .catch(function (err) {
          setIframeDoc(errorDoc('Preview failed: ' + err));
        });
    }
    if (e.target && e.target.id === 'markdown-preview-close') {
      closeModal();
    }
    if (e.target && e.target.id === 'markdown-preview-modal') {
      closeModal();
    }
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      var modal = document.getElementById('markdown-preview-modal');
      if (modal && modal.style.display !== 'none') closeModal();
    }
  });
})();
