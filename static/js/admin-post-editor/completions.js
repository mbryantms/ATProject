/**
 * CM6 completion sources for ATProject's bespoke markdown syntax.
 *
 * Two sources:
 *   - citationCompletionSource — triggers inside `[@...` or after a bare
 *     narrative `@`, calls the autocomplete-citations endpoint, and
 *     inserts just the key (no @, no brackets).
 *   - assetCompletionSource — triggers inside a markdown link/image
 *     target when the author has typed `](@` or `](@asset:` and suggests
 *     both post-local aliases and global asset keys.
 */

function debounceFetch(url, delay = 150) {
  let pending = null;
  return async (q, signal) => {
    if (pending) clearTimeout(pending.timer);
    return new Promise((resolve) => {
      const timer = setTimeout(async () => {
        try {
          const res = await fetch(`${url}?q=${encodeURIComponent(q)}`, {
            credentials: 'same-origin',
            signal,
          });
          if (!res.ok) {
            resolve([]);
            return;
          }
          const data = await res.json();
          resolve(data.results || []);
        } catch (err) {
          if (err.name !== 'AbortError') resolve([]);
        }
      }, delay);
      pending = { timer };
    });
  };
}

export function makeCitationCompletionSource(url) {
  const fetcher = debounceFetch(url);

  return async (context) => {
    // Two trigger modes:
    //  1. Inside brackets: `[@...` or `[@a; @...`
    //  2. Narrative: bare `@...` not preceded by a word char / `[` / `@`.
    const before = context.matchBefore(/@[a-zA-Z0-9][\w:#$%&\-+?<>~/]*/);
    if (!before) return null;

    // If the cursor is preceded by `[` or `; ` or the line start, or
    // any non-word character immediately before the @, treat as a cite.
    const charBefore = context.state.sliceDoc(
      Math.max(0, before.from - 1),
      before.from,
    );
    const triggeredByBracket =
      context.state
        .sliceDoc(Math.max(0, before.from - 30), before.from)
        .match(/\[(?:-?@[^\]]*?; *)*$/) !== null;
    const isWordBefore = /\w/.test(charBefore);
    if (isWordBefore && !triggeredByBracket) return null;

    // Don't trigger inside a markdown link target like `](@asset:...` — that's
    // the asset completion source's job.
    const priorSlice = context.state.sliceDoc(
      Math.max(0, before.from - 3),
      before.from,
    );
    if (priorSlice.endsWith('](')) return null;

    const prefix = before.text.slice(1); // drop leading @
    if (!context.explicit && prefix.length < 1) return null;

    const results = await fetcher(prefix);

    const options = results.map((r) => ({
      label: r.key,
      type: 'variable',
      detail: [r.author, r.year].filter(Boolean).join(' '),
      info: r.title,
      apply: r.key, // inserts key only; leading @ is already present.
    }));

    return {
      from: before.from + 1, // keep the @ in place
      options,
      validFor: /^[a-zA-Z0-9][\w:#$%&\-+?<>~/]*$/,
    };
  };
}

export function makeAssetCompletionSource(url, getPostId) {
  return async (context) => {
    // Trigger inside an image or link target: `](...` where the user
    // has typed `@`, optionally with `asset:` prefix.
    const before = context.matchBefore(/\]\(@(?:asset:)?[a-zA-Z0-9_-]*/);
    if (!before) return null;

    // Figure out where the replacement range starts — we keep `](` and
    // `@` (+ optional `asset:` prefix) intact, only suggesting the key.
    const mAfterAt = before.text.match(/@(asset:)?([a-zA-Z0-9_-]*)$/);
    if (!mAfterAt) return null;
    const hasAssetPrefix = !!mAfterAt[1];
    const typedKey = mAfterAt[2] || '';
    const keyStartOffset = before.from + before.text.length - typedKey.length;

    if (!context.explicit && typedKey.length < 1) return null;

    const qs =
      `?q=${encodeURIComponent(typedKey)}` +
      (getPostId && getPostId() ? `&post_id=${encodeURIComponent(getPostId())}` : '');
    let results = [];
    try {
      const res = await fetch(`${url}${qs}`, { credentials: 'same-origin' });
      if (res.ok) results = (await res.json()).results || [];
    } catch {
      // fall through with empty
    }

    const options = results
      .filter((r) => !(hasAssetPrefix && !r.global))
      .map((r) => {
        // For the alias form we expect `](@alias` so insertion is just the
        // alias. For the global form we insert `asset:key` unless the user
        // already typed the `asset:` prefix, in which case we insert just
        // the key.
        let apply;
        if (r.global && !hasAssetPrefix) {
          apply = `asset:${r.key}`;
        } else {
          apply = r.key;
        }
        return {
          label: r.key,
          type: r.global ? 'namespace' : 'variable',
          detail: r.global ? 'global' : 'alias',
          info: `${r.type || ''} — ${r.title || ''}`.trim(),
          apply,
        };
      });

    return {
      from: keyStartOffset,
      options,
      validFor: /^[a-zA-Z0-9_-]*$/,
    };
  };
}
