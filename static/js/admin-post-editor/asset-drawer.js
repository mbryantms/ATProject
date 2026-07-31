/**
 * The asset drawer: a collapsible panel beside the markdown editor for
 * browsing, uploading, and editing assets without leaving the page.
 *
 * Two tabs — "This post" (the owner's attachment rows, live) and
 * "Library" (ready assets, newest first, searchable, type-filterable,
 * paged). Per-asset actions: insert a reference at the cursor, copy the
 * reference, edit title/alt/caption inline. Uploads (button or drop
 * onto the drawer) go through the same endpoint as editor paste/drop.
 */

import { invalidateAssetInfo } from './asset-hover.js';

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

function referenceFor(item) {
  return item.alias ? `@${item.alias}` : `@asset:${item.key}`;
}

function markdownFor(item) {
  const ref = referenceFor(item);
  if (item.asset_type === 'image') return `![](${ref})`;
  return `[${item.title || item.key}](${ref})`;
}

export function mountAssetDrawer(options) {
  const { view, panelUrl, uploadUrl, updateUrl, attachUrl, getOwnerId, getOwnerType } =
    options;

  let currentTab = getOwnerId() ? 'attached' : 'library';
  let query = '';
  let typeFilter = '';
  let offset = 0;
  let data = { attached: [], library: [], library_total: 0 };
  let loaded = false;
  let searchTimer = null;

  // --- Layout: wrap the editor and hang the drawer beside it (reusing the
  // flex wrapper if the live preview already created it) ---
  const editorDom = view.dom;
  let wrapper = editorDom.parentElement;
  if (!wrapper.classList.contains('atp-editor-flex')) {
    wrapper = el('div', 'atp-editor-flex');
    editorDom.parentNode.insertBefore(wrapper, editorDom);
    wrapper.appendChild(editorDom);
  }

  const drawer = el('aside', 'atp-asset-drawer collapsed');
  wrapper.appendChild(drawer);

  const toggle = el('button', 'atp-drawer-toggle', 'Assets');
  toggle.type = 'button';
  toggle.title = 'Show/hide the asset drawer';
  toggle.addEventListener('click', () => {
    drawer.classList.toggle('collapsed');
    if (!drawer.classList.contains('collapsed') && !loaded) refresh();
  });
  drawer.appendChild(toggle);

  const body = el('div', 'atp-drawer-body');
  drawer.appendChild(body);

  // --- Header: tabs, search, filter, upload ---
  const header = el('div', 'atp-drawer-header');
  body.appendChild(header);

  const tabs = el('div', 'atp-drawer-tabs');
  header.appendChild(tabs);
  const tabButtons = {};
  for (const [id, label] of [
    ['attached', 'This post'],
    ['library', 'Library'],
  ]) {
    const b = el('button', 'atp-drawer-tab', label);
    b.type = 'button';
    b.addEventListener('click', () => {
      currentTab = id;
      render();
    });
    tabButtons[id] = b;
    tabs.appendChild(b);
  }

  const controls = el('div', 'atp-drawer-controls');
  header.appendChild(controls);

  const search = el('input', 'atp-drawer-search');
  search.type = 'search';
  search.placeholder = 'Search key or title…';
  search.addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      query = search.value.trim();
      offset = 0;
      refresh();
    }, 250);
  });
  controls.appendChild(search);

  const typeSelect = el('select', 'atp-drawer-type');
  for (const [value, label] of [
    ['', 'All types'],
    ['image', 'Images'],
    ['video', 'Video'],
    ['audio', 'Audio'],
    ['document', 'Documents'],
  ]) {
    const opt = el('option', null, label);
    opt.value = value;
    typeSelect.appendChild(opt);
  }
  typeSelect.addEventListener('change', () => {
    typeFilter = typeSelect.value;
    offset = 0;
    refresh();
  });
  controls.appendChild(typeSelect);

  const uploadLabel = el('label', 'atp-drawer-upload', 'Upload');
  const uploadInput = el('input', null);
  uploadInput.type = 'file';
  uploadInput.multiple = true;
  uploadInput.style.display = 'none';
  uploadLabel.appendChild(uploadInput);
  uploadInput.addEventListener('change', () => {
    uploadFiles(Array.from(uploadInput.files || []));
    uploadInput.value = '';
  });
  controls.appendChild(uploadLabel);

  const status = el('div', 'atp-drawer-status');
  body.appendChild(status);

  const list = el('div', 'atp-drawer-list');
  body.appendChild(list);

  const footer = el('div', 'atp-drawer-footer');
  body.appendChild(footer);

  // Drop files anywhere on the drawer to upload them.
  drawer.addEventListener('dragover', (event) => {
    const types = (event.dataTransfer && event.dataTransfer.types) || [];
    if (Array.from(types).includes('Files')) {
      event.preventDefault();
      drawer.classList.add('drop-target');
    }
  });
  drawer.addEventListener('dragleave', () => drawer.classList.remove('drop-target'));
  drawer.addEventListener('drop', (event) => {
    const files = event.dataTransfer && event.dataTransfer.files;
    if (!files || files.length === 0) return;
    event.preventDefault();
    drawer.classList.remove('drop-target');
    uploadFiles(Array.from(files));
  });

  function setStatus(text, isError) {
    status.textContent = text || '';
    status.classList.toggle('error', !!isError);
  }

  async function refresh() {
    loaded = true;
    setStatus('Loading…');
    const params = new URLSearchParams();
    const ownerId = getOwnerId();
    if (ownerId) params.set('object_id', ownerId);
    params.set('owner_type', getOwnerType());
    if (query) params.set('q', query);
    if (typeFilter) params.set('type', typeFilter);
    if (offset) params.set('offset', String(offset));
    try {
      const res = await fetch(`${panelUrl}?${params}`, {
        credentials: 'same-origin',
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const payload = await res.json();
      if (offset > 0) {
        payload.library = data.library.concat(payload.library);
      }
      data = payload;
      setStatus('');
    } catch (err) {
      setStatus(`Could not load assets: ${err.message}`, true);
      return;
    }
    render();
  }

  async function uploadFiles(files) {
    if (!files.length) return;
    setStatus(`Uploading ${files.length} file(s)…`);
    for (const file of files) {
      const form = new FormData();
      form.append('file', file, file.name);
      const ownerId = getOwnerId();
      if (ownerId) form.append('object_id', ownerId);
      form.append('owner_type', getOwnerType());
      try {
        const res = await fetch(uploadUrl, {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'X-CSRFToken': csrfToken() },
          body: form,
        });
        const result = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(result.error || `HTTP ${res.status}`);
        invalidateAssetInfo();
      } catch (err) {
        setStatus(`${file.name}: ${err.message}`, true);
        return;
      }
    }
    setStatus('');
    offset = 0;
    await refresh();
    startRenditionPolling();
  }

  // After an upload, renditions generate in the background; poll the panel
  // for a bit so badges flip from "no renditions" to "renditions n/n"
  // without the author doing anything.
  let pollTimer = null;
  function startRenditionPolling(remaining = 6) {
    clearTimeout(pollTimer);
    if (remaining <= 0) return;
    pollTimer = setTimeout(async () => {
      invalidateAssetInfo();
      await refresh();
      const stillPending = data.attached
        .concat(data.library)
        .some(
          (i) =>
            i.asset_type === 'image' &&
            (!i.renditions ||
              i.renditions.total === 0 ||
              i.renditions.completed < i.renditions.total),
        );
      if (stillPending) startRenditionPolling(remaining - 1);
    }, 5000);
  }

  function insertAtCursor(text) {
    const sel = view.state.selection.main;
    view.dispatch({
      changes: { from: sel.from, to: sel.to, insert: text },
      selection: { anchor: sel.from + text.length },
    });
    view.focus();
  }

  async function saveEdit(item, fields, card) {
    const form = new FormData();
    form.append('key', item.key);
    for (const [k, v] of Object.entries(fields)) form.append(k, v);
    try {
      const res = await fetch(updateUrl, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-CSRFToken': csrfToken() },
        body: form,
      });
      const result = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(result.error || `HTTP ${res.status}`);
      invalidateAssetInfo();
      Object.assign(item, result, { alias: item.alias, attached: item.attached });
      card.replaceWith(buildCard(item));
    } catch (err) {
      setStatus(`Save failed: ${err.message}`, true);
    }
  }

  async function attachAsset(item) {
    const form = new FormData();
    form.append('key', item.key);
    form.append('owner_type', getOwnerType());
    form.append('object_id', getOwnerId());
    try {
      const res = await fetch(attachUrl, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-CSRFToken': csrfToken() },
        body: form,
      });
      if (!res.ok) {
        const result = await res.json().catch(() => ({}));
        throw new Error(result.error || `HTTP ${res.status}`);
      }
      invalidateAssetInfo();
      refresh();
    } catch (err) {
      setStatus(`Attach failed: ${err.message}`, true);
    }
  }

  function buildBadges(parent, item) {
    const badges = el('div', 'atp-card-badges');
    if (item.asset_type === 'image') {
      badges.appendChild(
        el(
          'span',
          `atp-badge ${item.alt_text ? 'ok' : 'warn'}`,
          item.alt_text ? 'alt ✓' : 'no alt',
        ),
      );
      const r = item.renditions || { completed: 0, total: 0 };
      const cls = r.total > 0 && r.completed === r.total ? 'ok' : 'warn';
      const label =
        r.total === 0 ? 'no renditions' : `renditions ${r.completed}/${r.total}`;
      badges.appendChild(el('span', `atp-badge ${cls}`, label));
    }
    if (item.attached) badges.appendChild(el('span', 'atp-badge ok', 'attached'));
    parent.appendChild(badges);
  }

  function buildEditForm(item, card) {
    const form = el('div', 'atp-card-edit');
    const fields = [
      ['title', 'Title', item.title || ''],
      ['alt_text', 'Alt text', item.alt_text || ''],
      ['caption', 'Caption', item.caption || ''],
    ];
    const inputs = {};
    for (const [name, label, value] of fields) {
      form.appendChild(el('label', null, label));
      const input = el(name === 'caption' ? 'textarea' : 'input', null);
      input.value = value;
      inputs[name] = input;
      form.appendChild(input);
    }
    const save = el('button', 'atp-card-btn primary', 'Save');
    save.type = 'button';
    save.addEventListener('click', () =>
      saveEdit(
        item,
        {
          title: inputs.title.value,
          alt_text: inputs.alt_text.value,
          caption: inputs.caption.value,
        },
        card,
      ),
    );
    form.appendChild(save);

    // Focal point picker: click the image to mark where crops should center.
    if (item.asset_type === 'image' && item.thumb) {
      form.appendChild(el('label', null, 'Focal point (click to set)'));
      const fpWrap = el('div', 'atp-fp-wrap');
      const img = el('img', 'atp-fp-img');
      img.src = item.thumb;
      img.alt = '';
      fpWrap.appendChild(img);
      const dot = el('div', 'atp-fp-dot');
      const setDot = (x, y) => {
        if (x == null || y == null) {
          dot.style.display = 'none';
          return;
        }
        dot.style.display = '';
        dot.style.left = `${x * 100}%`;
        dot.style.top = `${y * 100}%`;
      };
      setDot(item.focal_point_x, item.focal_point_y);
      fpWrap.appendChild(dot);
      fpWrap.addEventListener('click', (event) => {
        const rect = fpWrap.getBoundingClientRect();
        const x = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
        const y = Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height));
        setDot(x, y);
        saveEdit(
          item,
          { focal_point_x: x.toFixed(3), focal_point_y: y.toFixed(3) },
          card,
        );
      });
      form.appendChild(fpWrap);
      const clear = el('button', 'atp-card-btn', 'Clear focal point');
      clear.type = 'button';
      clear.addEventListener('click', () =>
        saveEdit(item, { focal_point_x: '', focal_point_y: '' }, card),
      );
      form.appendChild(clear);
    }
    return form;
  }

  function buildCard(item) {
    const card = el('div', 'atp-asset-card-row');

    if (item.thumb && item.asset_type === 'image') {
      const img = el('img', 'atp-card-thumb');
      img.src = item.thumb;
      img.alt = '';
      img.loading = 'lazy';
      card.appendChild(img);
    } else {
      card.appendChild(el('div', 'atp-card-thumb placeholder', item.asset_type));
    }

    const main = el('div', 'atp-card-main');
    card.appendChild(main);
    main.appendChild(el('div', 'atp-card-title', item.title || item.key));
    main.appendChild(el('div', 'atp-card-key', referenceFor(item)));
    buildBadges(main, item);

    const actions = el('div', 'atp-card-actions');
    main.appendChild(actions);

    const insert = el('button', 'atp-card-btn primary', 'Insert');
    insert.type = 'button';
    insert.addEventListener('click', () => insertAtCursor(markdownFor(item)));
    actions.appendChild(insert);

    const copy = el('button', 'atp-card-btn', 'Copy ref');
    copy.type = 'button';
    copy.addEventListener('click', () => {
      navigator.clipboard?.writeText(referenceFor(item));
      copy.textContent = 'Copied';
      setTimeout(() => {
        copy.textContent = 'Copy ref';
      }, 1200);
    });
    actions.appendChild(copy);

    const edit = el('button', 'atp-card-btn', 'Edit');
    edit.type = 'button';
    edit.addEventListener('click', () => {
      const existing = card.querySelector('.atp-card-edit');
      if (existing) existing.remove();
      else card.appendChild(buildEditForm(item, card));
    });
    actions.appendChild(edit);

    if (!item.attached && getOwnerId()) {
      const attach = el('button', 'atp-card-btn', 'Attach');
      attach.type = 'button';
      attach.addEventListener('click', () => attachAsset(item));
      actions.appendChild(attach);
    }

    return card;
  }

  function render() {
    for (const [id, b] of Object.entries(tabButtons)) {
      b.classList.toggle('active', id === currentTab);
    }
    tabButtons.attached.style.display = getOwnerId() ? '' : 'none';

    list.replaceChildren();
    footer.replaceChildren();

    const items = currentTab === 'attached' ? data.attached : data.library;
    if (!items.length) {
      list.appendChild(
        el(
          'div',
          'atp-drawer-empty',
          currentTab === 'attached'
            ? 'Nothing attached to this post yet.'
            : 'No assets match.',
        ),
      );
    }
    for (const item of items) list.appendChild(buildCard(item));

    if (currentTab === 'library' && data.library.length < data.library_total) {
      const more = el(
        'button',
        'atp-card-btn',
        `Load more (${data.library.length}/${data.library_total})`,
      );
      more.type = 'button';
      more.addEventListener('click', () => {
        offset = data.library.length;
        refresh();
      });
      footer.appendChild(more);
    }
  }

  return { refresh };
}
