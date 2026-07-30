/**
 * Hover cards for @asset:key / @alias references in the CM6 editor.
 *
 * Hovering a reference fetches the asset's metadata from the admin
 * asset-info endpoint and shows a card: thumbnail, title, dimensions,
 * alt-text status, rendition progress, and whether it's attached to the
 * current post/page. Unknown references get an explicit "unresolved"
 * card, matching the lint underline the author already sees.
 */

import { hoverTooltip } from '@codemirror/view';

// Mirrors the decoration/lint pattern: group 1 is the token after `@`.
const REF_RE = /!?\[[^\]]*\]\(@((?:asset:)?[a-zA-Z0-9_-]+)(?:\?[^)]*)?\)/g;

const CACHE_TTL_MS = 15000;
const cache = new Map(); // token -> { ts, data|null }

async function fetchInfo(url, token, ownerId, ownerType) {
  const cached = cache.get(token);
  if (cached && Date.now() - cached.ts < CACHE_TTL_MS) return cached.data;

  let data = null;
  try {
    const qs =
      `?ref=${encodeURIComponent(token)}` +
      (ownerId ? `&object_id=${encodeURIComponent(ownerId)}` : '') +
      (ownerType ? `&owner_type=${encodeURIComponent(ownerType)}` : '');
    const res = await fetch(`${url}${qs}`, { credentials: 'same-origin' });
    if (res.ok) data = await res.json();
  } catch {
    data = null;
  }
  cache.set(token, { ts: Date.now(), data });
  return data;
}

/** Drop a token's cache entry (used after uploads/edits change its state). */
export function invalidateAssetInfo(token) {
  if (token) cache.delete(token);
  else cache.clear();
}

function row(parent, className, text) {
  const el = document.createElement('div');
  el.className = className;
  if (text != null) el.textContent = text;
  parent.appendChild(el);
  return el;
}

function badge(parent, className, text) {
  const el = document.createElement('span');
  el.className = `cm-atp-card-badge ${className}`;
  el.textContent = text;
  parent.appendChild(el);
  return el;
}

function buildCard(token, data) {
  const card = document.createElement('div');
  card.className = 'cm-atp-asset-card';

  if (!data) {
    row(card, 'cm-atp-card-missing', `@${token} — unresolved reference`);
    return card;
  }

  if (data.thumb && data.asset_type === 'image') {
    const img = document.createElement('img');
    img.className = 'cm-atp-card-thumb';
    img.src = data.thumb;
    img.alt = '';
    card.appendChild(img);
  }

  row(card, 'cm-atp-card-title', data.title || data.key);

  const dims = data.width && data.height ? ` · ${data.width}×${data.height}` : '';
  row(card, 'cm-atp-card-meta', `${data.key} · ${data.asset_type}${dims}`);

  const badges = row(card, 'cm-atp-card-badges', null);
  if (data.asset_type === 'image') {
    if (data.alt_text) badge(badges, 'ok', 'alt ✓');
    else badge(badges, 'warn', 'no alt');
    const r = data.renditions || { completed: 0, total: 0 };
    if (r.total === 0) badge(badges, 'warn', 'no renditions');
    else if (r.completed < r.total)
      badge(badges, 'warn', `renditions ${r.completed}/${r.total}`);
    else badge(badges, 'ok', `renditions ${r.completed}/${r.total}`);
  }
  if (data.attached) badge(badges, 'ok', 'attached');

  return card;
}

export function makeAssetHoverExtension(url, getOwnerId, getOwnerType) {
  return hoverTooltip(async (view, pos) => {
    const line = view.state.doc.lineAt(pos);
    REF_RE.lastIndex = 0;
    let m;
    while ((m = REF_RE.exec(line.text)) !== null) {
      const start = line.from + m.index;
      const end = start + m[0].length;
      if (pos >= start && pos <= end) {
        const token = m[1];
        const data = await fetchInfo(
          url,
          token,
          getOwnerId && getOwnerId(),
          getOwnerType && getOwnerType(),
        );
        return {
          pos: start,
          end,
          above: true,
          create: () => ({ dom: buildCard(token, data) }),
        };
      }
    }
    return null;
  });
}
