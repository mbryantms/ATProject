/**
 * Split live preview: a toggleable pane beside the editor that renders
 * the current markdown through the real pipeline (the admin preview
 * endpoint) on typing pauses. The endpoint caches by content hash, so
 * idle time and repeated content cost nothing server-side.
 */

import { EditorView } from '@codemirror/view';
import { StateEffect } from '@codemirror/state';

const DEBOUNCE_MS = 2000;

function csrfToken() {
  const input = document.querySelector('input[name="csrfmiddlewaretoken"]');
  return input ? input.value : '';
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

export function mountLivePreview(options) {
  const { view, previewUrl, getOwnerId, getOwnerType } = options;

  let timer = null;
  let dirty = true;
  let inFlight = false;
  let lastRendered = null;

  // Reuse the drawer's flex wrapper when present, otherwise create it.
  const editorDom = view.dom;
  let container = editorDom.parentElement;
  if (!container.classList.contains('atp-editor-flex')) {
    const wrapper = el('div', 'atp-editor-flex');
    container.insertBefore(wrapper, editorDom);
    wrapper.appendChild(editorDom);
    container = wrapper;
  }

  const pane = el('aside', 'atp-preview-pane collapsed');
  const drawerEl = container.querySelector('.atp-asset-drawer');
  container.insertBefore(pane, drawerEl || null);

  const toggle = el('button', 'atp-drawer-toggle', 'Preview');
  toggle.type = 'button';
  toggle.title = 'Show/hide the live preview';
  pane.appendChild(toggle);

  const body = el('div', 'atp-preview-body');
  pane.appendChild(body);

  const bar = el('div', 'atp-preview-bar');
  body.appendChild(bar);
  const lintNote = el('span', 'atp-preview-lint', '');
  bar.appendChild(lintNote);
  const spinner = el('span', 'atp-preview-spinner', 'rendering…');
  spinner.style.display = 'none';
  bar.appendChild(spinner);

  const iframe = el('iframe', 'atp-preview-iframe');
  iframe.setAttribute('title', 'Live markdown preview');
  body.appendChild(iframe);

  const isOpen = () => !pane.classList.contains('collapsed');

  async function renderNow() {
    const content = view.state.doc.toString();
    if (content === lastRendered || inFlight) return;
    inFlight = true;
    spinner.style.display = '';
    try {
      const form = new FormData();
      form.append('content', content);
      const ownerId = getOwnerId();
      if (ownerId) form.append('object_id', ownerId);
      form.append('owner_type', getOwnerType());
      const res = await fetch(previewUrl, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-CSRFToken': csrfToken() },
        body: form,
      });
      const data = await res.json().catch(() => ({}));
      if (data.ok && data.html) {
        iframe.srcdoc = data.html;
        lastRendered = content;
        dirty = false;
        const lint = data.lint || [];
        lintNote.textContent = lint.length
          ? `${lint.length} warning${lint.length === 1 ? '' : 's'}`
          : '';
        lintNote.title = lint.join('\n');
      } else if (data.error) {
        lintNote.textContent = data.error;
      }
    } catch {
      lintNote.textContent = 'preview unavailable';
    } finally {
      inFlight = false;
      spinner.style.display = 'none';
      // Content changed while rendering — catch up.
      if (isOpen() && view.state.doc.toString() !== lastRendered) schedule();
    }
  }

  function schedule() {
    dirty = true;
    if (!isOpen()) return;
    clearTimeout(timer);
    timer = setTimeout(renderNow, DEBOUNCE_MS);
  }

  toggle.addEventListener('click', () => {
    pane.classList.toggle('collapsed');
    if (isOpen() && dirty) renderNow();
  });

  // Re-render on typing pauses while the pane is open.
  view.dispatch({
    effects: StateEffect.appendConfig.of(
      EditorView.updateListener.of((update) => {
        if (update.docChanged) schedule();
      }),
    ),
  });

  return { renderNow };
}
