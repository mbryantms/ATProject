/**
 * Paste/drop file upload for the CM6 markdown editor.
 *
 * Dropping or pasting a file into the editor uploads it to the admin
 * upload endpoint, which creates a ready Asset on the spot (the normal
 * save pipeline generates the key, metadata, and renditions). A
 * placeholder is inserted immediately and replaced with the returned
 * `@asset:key` markdown when the upload completes — no page reload and
 * no post save. Text pastes and drops are untouched: the handlers only
 * engage when actual files are present.
 */

import { EditorView } from '@codemirror/view';

let placeholderCounter = 0;

function csrfToken() {
  const input = document.querySelector('input[name="csrfmiddlewaretoken"]');
  return input ? input.value : '';
}

function showUploadError(message) {
  const notice = document.createElement('div');
  notice.className = 'cm-atp-upload-error';
  notice.setAttribute('role', 'alert');
  notice.textContent = message;
  notice.style.cssText =
    'position:fixed;bottom:1em;right:1em;z-index:10000;max-width:24em;' +
    'padding:0.6em 1em;border-radius:4px;font-size:13px;cursor:pointer;' +
    'background:var(--message-error-bg, #ba2121);color:#fff;';
  notice.addEventListener('click', () => notice.remove());
  document.body.appendChild(notice);
  setTimeout(() => notice.remove(), 8000);
}

async function uploadFile(url, file, getOwnerId, getOwnerType) {
  const form = new FormData();
  form.append('file', file, file.name);
  const ownerId = getOwnerId && getOwnerId();
  const ownerType = getOwnerType && getOwnerType();
  if (ownerId) form.append('object_id', ownerId);
  if (ownerType) form.append('owner_type', ownerType);

  const res = await fetch(url, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'X-CSRFToken': csrfToken() },
    body: form,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `upload failed (HTTP ${res.status})`);
  }
  return data;
}

function replacePlaceholder(view, placeholder, replacement) {
  const index = view.state.doc.toString().indexOf(placeholder);
  if (index === -1) return; // author deleted it; drop the result silently
  view.dispatch({
    changes: { from: index, to: index + placeholder.length, insert: replacement },
  });
}

function handleFiles(view, files, from, to, url, getOwnerId, getOwnerType) {
  const accepted = Array.from(files || []).filter((f) => f && f.name);
  if (accepted.length === 0) return false;

  // One placeholder per file, inserted in a single transaction so undo is
  // one step; each is unique so the async replacement can find its own.
  const placeholders = accepted.map((file) => {
    placeholderCounter += 1;
    return `![Uploading ${file.name}… #${placeholderCounter}]()`;
  });
  view.dispatch({
    changes: { from, to, insert: placeholders.join('\n') },
  });

  accepted.forEach((file, i) => {
    uploadFile(url, file, getOwnerId, getOwnerType)
      .then((data) => {
        replacePlaceholder(view, placeholders[i], data.markdown || '');
      })
      .catch((err) => {
        replacePlaceholder(view, placeholders[i], '');
        showUploadError(`${file.name}: ${err.message}`);
      });
  });
  return true;
}

export function makeAssetUploadExtension(url, getOwnerId, getOwnerType) {
  return EditorView.domEventHandlers({
    paste: (event, view) => {
      const files = event.clipboardData && event.clipboardData.files;
      if (!files || files.length === 0) return false;
      event.preventDefault();
      const sel = view.state.selection.main;
      return handleFiles(view, files, sel.from, sel.to, url, getOwnerId, getOwnerType);
    },
    drop: (event, view) => {
      const files = event.dataTransfer && event.dataTransfer.files;
      if (!files || files.length === 0) return false;
      event.preventDefault();
      const pos =
        view.posAtCoords({ x: event.clientX, y: event.clientY }) ??
        view.state.selection.main.head;
      return handleFiles(view, files, pos, pos, url, getOwnerId, getOwnerType);
    },
    dragover: (event) => {
      const types = (event.dataTransfer && event.dataTransfer.types) || [];
      if (Array.from(types).includes('Files')) {
        event.preventDefault();
        return true;
      }
      return false;
    },
  });
}
