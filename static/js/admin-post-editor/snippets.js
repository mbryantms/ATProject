/**
 * CM6 completion source for project-specific markdown snippets and class
 * names surfaced in the Markdown reference panel.
 *
 * Two triggers:
 *
 *   1. Line-start `:::` → full fenced-div snippets (admonitions, epigraph,
 *      columns, text-center/right, sans-serif, float, width-full,
 *      table-small, sortable). Insertion uses CM6 snippet placeholders so
 *      the author can Tab through the fields.
 *
 *   2. Inside `{.…` → class-name hints (smallcaps, marginnote,
 *      tabular-nums, date-*, float-*, width-full, icon-not, admonition-*,
 *      epigraph, columns, table-small, sortable). Works for bracketed
 *      spans, image/link attr blocks, and fenced divs.
 */

import { snippet } from '@codemirror/autocomplete';

export function makeSnippetCompletionSource(fenceSnippets, inlineClasses) {
  const fenceOptions = (fenceSnippets || []).map((s) => ({
    label: `::: {.${s.className}}`,
    displayLabel: `::: {.${s.className}}`,
    type: 'function',
    detail: s.detail || '',
    apply: snippet(s.template),
    boost: s.className.startsWith('admonition-') ? 2 : 1,
  }));

  const classOptions = (inlineClasses || []).map((c) => ({
    label: c.name,
    type: 'class',
    detail: c.detail || '',
  }));

  return (context) => {
    const { state, pos } = context;
    const line = state.doc.lineAt(pos);
    const before = line.text.slice(0, pos - line.from);

    // Trigger 1 — fence opener. Accept optional leading whitespace, `:::`,
    // optional space, optional `{.`, optional class-name prefix.
    const fenceMatch = before.match(/^(\s*):::\s*\{?\.?([a-zA-Z0-9-]*)$/);
    if (fenceMatch) {
      const indentLen = fenceMatch[1].length;
      const fromCol = line.from + indentLen;
      if (!context.explicit && !fenceMatch[0].slice(indentLen).startsWith(':::')) {
        return null;
      }
      return {
        from: fromCol,
        options: fenceOptions,
        validFor: /^:::.*$/,
      };
    }

    // Trigger 2 — inside `{.…`. Replace the partial class prefix only.
    const classMatch = before.match(/\{\.([a-zA-Z0-9-]*)$/);
    if (classMatch) {
      const prefix = classMatch[1] || '';
      const fromPos = pos - prefix.length;
      if (!context.explicit && prefix.length < 1) return null;
      return {
        from: fromPos,
        options: classOptions,
        validFor: /^[a-zA-Z0-9-]*$/,
      };
    }

    return null;
  };
}
