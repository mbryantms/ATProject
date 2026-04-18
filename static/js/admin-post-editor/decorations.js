/**
 * ViewPlugin that scans visible lines and paints decorations over the
 * project-specific markdown tokens the stock @codemirror/lang-markdown
 * parser doesn't know about:
 *
 *   - @asset:key / @alias inside ](...) image/link targets
 *   - [@cite] / [@a; @b] / [-@k] bracketed citations
 *   - @bare narrative citations
 *   - ::: {.admonition-*} / ::: {.epigraph} / ::: {.columns} / bare ::: closer
 *   - [^ref] footnote references and [^ref]: definitions
 */

import { Decoration, ViewPlugin } from '@codemirror/view';
import { RangeSetBuilder } from '@codemirror/state';

const assetRefDeco = Decoration.mark({ class: 'cm-atp-asset' });
const citationDeco = Decoration.mark({ class: 'cm-atp-citation' });
const admonitionDeco = Decoration.mark({ class: 'cm-atp-admonition' });
const footnoteDeco = Decoration.mark({ class: 'cm-atp-footnote' });

// Mirrors engine/admin/post.py's _ASSET_REF_RE but we want the whole
// @-prefix..key span to paint, not just the capture groups.
const ASSET_REF_RE = /!?\[[^\]]*\]\((@(?:asset:)?[a-zA-Z0-9_-]+(?:\?[^)]*)?)\)/g;

// Bracketed citation: [-?@key(, locator)?(; …)*]
const CITATION_BRACKETED_RE =
  /\[-?@[a-zA-Z0-9][\w:#$%&\-+?<>~/]*(?:,\s*[^;\]]+?)?(?:;\s*-?@[a-zA-Z0-9][\w:#$%&\-+?<>~/]*(?:,\s*[^;\]]+?)?)*\]/g;

// Narrative citation — @key outside brackets / link targets. We exclude
// @ preceded by a word character, '@', '[', or '\\'.
const CITATION_NARRATIVE_RE =
  /(^|[^\w@[\\(])(@[a-zA-Z0-9][\w:#$%&\-+?<>~/]*[a-zA-Z0-9]|@[a-zA-Z0-9])/g;

// Admonition / fenced div openers/closers on their own line.
const ADMONITION_RE = /^:::+.*$/gm;

// Footnote references and definitions.
const FOOTNOTE_REF_RE = /\[\^[^\]\s]+\]/g;
const FOOTNOTE_DEF_RE = /^\[\^[^\]\s]+\]:/gm;

function scanVisibleRanges(view) {
  const builder = new RangeSetBuilder();

  // Collect ranges keyed by start so we can sort before adding.
  const hits = [];
  const doc = view.state.doc;

  for (const { from, to } of view.visibleRanges) {
    const text = doc.sliceString(from, to);

    // Asset refs
    ASSET_REF_RE.lastIndex = 0;
    let m;
    while ((m = ASSET_REF_RE.exec(text)) !== null) {
      const start = from + m.index + m[0].indexOf(m[1]);
      hits.push([start, start + m[1].length, assetRefDeco]);
    }

    // Bracketed citations
    CITATION_BRACKETED_RE.lastIndex = 0;
    while ((m = CITATION_BRACKETED_RE.exec(text)) !== null) {
      hits.push([from + m.index, from + m.index + m[0].length, citationDeco]);
    }

    // Narrative citations
    CITATION_NARRATIVE_RE.lastIndex = 0;
    while ((m = CITATION_NARRATIVE_RE.exec(text)) !== null) {
      const cite = m[2];
      const citeStart = from + m.index + m[0].indexOf(cite);
      hits.push([citeStart, citeStart + cite.length, citationDeco]);
    }

    // Admonition fences
    ADMONITION_RE.lastIndex = 0;
    while ((m = ADMONITION_RE.exec(text)) !== null) {
      hits.push([from + m.index, from + m.index + m[0].length, admonitionDeco]);
    }

    // Footnote definitions
    FOOTNOTE_DEF_RE.lastIndex = 0;
    while ((m = FOOTNOTE_DEF_RE.exec(text)) !== null) {
      hits.push([from + m.index, from + m.index + m[0].length, footnoteDeco]);
    }

    // Footnote references (inline)
    FOOTNOTE_REF_RE.lastIndex = 0;
    while ((m = FOOTNOTE_REF_RE.exec(text)) !== null) {
      // Skip footnote definitions (colon-terminated) which we already painted.
      const afterEnd = text.charAt(m.index + m[0].length);
      if (afterEnd === ':') continue;
      hits.push([from + m.index, from + m.index + m[0].length, footnoteDeco]);
    }
  }

  hits.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  // Dedupe overlapping ranges — citation regex can catch @ inside a
  // bracketed cite, so keep the outer range.
  let lastTo = -1;
  for (const [s, e, deco] of hits) {
    if (s < lastTo) continue;
    builder.add(s, e, deco);
    lastTo = e;
  }

  return builder.finish();
}

export const atpMarkdownDecorations = ViewPlugin.fromClass(
  class {
    constructor(view) {
      this.decorations = scanVisibleRanges(view);
    }
    update(update) {
      if (update.docChanged || update.viewportChanged) {
        this.decorations = scanVisibleRanges(update.view);
      }
    }
  },
  { decorations: (v) => v.decorations },
);
