/**
 * In-editor "Markdown helper" command palette.
 *
 * A searchable overlay listing every project markdown feature (fed by
 * engine/markdown/cheatsheet.py, stamped onto the textarea as JSON). Typing
 * filters across syntax + description + section; Enter or click inserts the
 * item's CodeMirror snippet at the cursor using the same `snippet()` machinery
 * as the `{.` autocompletions, so tab-stops work identically.
 *
 * Opened by the "Markdown helper" button in the readonly reference field
 * (`[data-md-helper-open]`) or the Ctrl/Cmd-/ shortcut. CSP-safe: no inline
 * scripts or styles — all classes live in admin-post.css.
 */

import { snippet } from '@codemirror/autocomplete';

const MAX_RESULTS = 60;

function flatten(sections) {
  const items = [];
  (sections || []).forEach((section) => {
    (section.items || []).forEach((item) => {
      items.push({
        section: section.title,
        icon: section.icon || '',
        syntax: item.syntax || '',
        insert: item.insert || null,
        desc: item.desc || '',
        haystack: `${section.title} ${item.syntax} ${item.desc}`.toLowerCase(),
      });
    });
  });
  return items;
}

// Render backtick spans in a description as <code>, escaping everything else.
function descToHtml(text) {
  const escaped = text.replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
  );
  return escaped.replace(/`([^`]+)`/g, '<code>$1</code>');
}

function escapeText(text) {
  return text.replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
  );
}

export function mountCheatsheetPalette(view, sections) {
  const items = flatten(sections);
  if (!items.length) return null;

  // --- Build the overlay once ------------------------------------------------
  const overlay = document.createElement('div');
  overlay.className = 'mdh-overlay';
  overlay.hidden = true;
  overlay.setAttribute('role', 'dialog');
  overlay.setAttribute('aria-modal', 'true');
  overlay.setAttribute('aria-label', 'Markdown helper');

  const panel = document.createElement('div');
  panel.className = 'mdh-panel';

  const header = document.createElement('div');
  header.className = 'mdh-header';
  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'mdh-search';
  input.placeholder =
    'Search markdown syntax — e.g. “footnote”, “admonition”, “@asset”';
  input.setAttribute('aria-label', 'Search markdown syntax');
  input.autocomplete = 'off';
  input.spellcheck = false;
  const hint = document.createElement('div');
  hint.className = 'mdh-hint';
  hint.innerHTML =
    '<kbd>↑</kbd><kbd>↓</kbd> move · <kbd>↵</kbd> insert · <kbd>Esc</kbd> close';
  header.appendChild(input);
  header.appendChild(hint);

  const list = document.createElement('ul');
  list.className = 'mdh-list';
  list.setAttribute('role', 'listbox');

  panel.appendChild(header);
  panel.appendChild(list);
  overlay.appendChild(panel);
  document.body.appendChild(overlay);

  let filtered = [];
  let active = 0;

  function render(query) {
    const q = query.trim().toLowerCase();
    const terms = q ? q.split(/\s+/) : [];
    filtered = items
      .filter((it) => terms.every((t) => it.haystack.includes(t)))
      .slice(0, MAX_RESULTS);
    active = 0;
    list.innerHTML = '';

    if (!filtered.length) {
      const empty = document.createElement('li');
      empty.className = 'mdh-empty';
      empty.textContent = 'No matching syntax.';
      list.appendChild(empty);
      return;
    }

    let lastSection = null;
    filtered.forEach((it, idx) => {
      if (it.section !== lastSection) {
        const head = document.createElement('li');
        head.className = 'mdh-section';
        head.textContent = `${it.icon} ${it.section}`.trim();
        head.setAttribute('aria-hidden', 'true');
        list.appendChild(head);
        lastSection = it.section;
      }
      const li = document.createElement('li');
      li.className = 'mdh-item';
      li.setAttribute('role', 'option');
      li.dataset.idx = String(idx);
      if (!it.insert) li.classList.add('mdh-item--info');
      li.innerHTML =
        `<code class="mdh-syntax">${escapeText(it.syntax)}</code>` +
        `<span class="mdh-desc">${descToHtml(it.desc)}</span>` +
        (it.insert
          ? '<span class="mdh-insert-tag">insert</span>'
          : '<span class="mdh-insert-tag mdh-insert-tag--info">reference</span>');
      li.addEventListener('mousemove', () => setActive(idx));
      li.addEventListener('click', () => choose(idx));
      list.appendChild(li);
    });
    highlight();
  }

  function itemNodes() {
    return Array.from(list.querySelectorAll('.mdh-item'));
  }

  function highlight() {
    itemNodes().forEach((node) => {
      const on = Number(node.dataset.idx) === active;
      node.classList.toggle('mdh-item--active', on);
      if (on) {
        node.setAttribute('aria-selected', 'true');
        node.scrollIntoView({ block: 'nearest' });
      } else {
        node.removeAttribute('aria-selected');
      }
    });
  }

  function setActive(idx) {
    if (idx === active) return;
    active = idx;
    highlight();
  }

  function move(delta) {
    if (!filtered.length) return;
    active = (active + delta + filtered.length) % filtered.length;
    highlight();
  }

  function choose(idx) {
    const it = filtered[idx];
    if (!it) return;
    if (it.insert) {
      // Collapse to the selection end so we never clobber selected text,
      // then let snippet() lay in the template + tab-stops.
      const at = view.state.selection.main.to;
      snippet(it.insert)(view, null, at, at);
    }
    close();
  }

  function open() {
    if (!overlay.hidden) return;
    overlay.hidden = false;
    input.value = '';
    render('');
    input.focus();
  }

  function close() {
    if (overlay.hidden) return;
    overlay.hidden = true;
    view.focus();
  }

  function toggle() {
    if (overlay.hidden) open();
    else close();
  }

  // --- Wiring ----------------------------------------------------------------
  input.addEventListener('input', () => render(input.value));

  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      move(1);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      move(-1);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      choose(active);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      close();
    }
  });

  overlay.addEventListener('mousedown', (e) => {
    if (e.target === overlay) close();
  });

  document.querySelectorAll('[data-md-helper-open]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      open();
    });
  });

  // Global shortcut: Ctrl/Cmd-/. Bound at document level so it works from the
  // editor or anywhere on the change form.
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === '/') {
      e.preventDefault();
      toggle();
    }
  });

  const api = { open, close, toggle };
  window.__atpMarkdownHelper = api;
  return api;
}
