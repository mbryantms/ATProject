/**
 * CodeMirror 6 editor for the Post admin `content_markdown` field.
 *
 * Mounts on #id_content_markdown, keeps the original <textarea> hidden
 * so Django's form handling stays untouched, and mirrors the editor's
 * value back on every update plus immediately before form submit.
 */

import { EditorState } from '@codemirror/state';
import {
  EditorView,
  keymap,
  lineNumbers,
  highlightActiveLine,
  highlightActiveLineGutter,
  drawSelection,
  rectangularSelection,
  crosshairCursor,
} from '@codemirror/view';
import {
  defaultKeymap,
  history,
  historyKeymap,
  indentWithTab,
} from '@codemirror/commands';
import {
  bracketMatching,
  foldGutter,
  foldKeymap,
  indentOnInput,
  syntaxHighlighting,
  defaultHighlightStyle,
} from '@codemirror/language';
import { markdown } from '@codemirror/lang-markdown';
import { searchKeymap, highlightSelectionMatches } from '@codemirror/search';
import {
  autocompletion,
  completionKeymap,
  closeBrackets,
  closeBracketsKeymap,
} from '@codemirror/autocomplete';
import { linter, lintGutter } from '@codemirror/lint';

import { atpMarkdownDecorations } from './admin-post-editor/decorations.js';
import {
  makeCitationCompletionSource,
  makeAssetCompletionSource,
} from './admin-post-editor/completions.js';
import { makeLintSource } from './admin-post-editor/lint-source.js';
import { makeSnippetCompletionSource } from './admin-post-editor/snippets.js';
import { mountCheatsheetPalette } from './admin-post-editor/cheatsheet-palette.js';

const TEXTAREA_ID = 'id_content_markdown';

function initEditor() {
  const textarea = document.getElementById(TEXTAREA_ID);
  if (!textarea || textarea.dataset.cmBound === '1') return;
  textarea.dataset.cmBound = '1';

  const syncToTextarea = (view) => {
    textarea.value = view.state.doc.toString();
  };

  const updateListener = EditorView.updateListener.of((update) => {
    if (update.docChanged) {
      syncToTextarea(update.view);
    }
  });

  // Endpoint URLs + post id are stamped onto the textarea by
  // PostAdmin.formfield_for_dbfield.
  const citationsUrl = textarea.dataset.cmCitationsUrl || '';
  const assetsUrl = textarea.dataset.cmAssetsUrl || '';
  const lintUrl = textarea.dataset.cmLintUrl || '';
  const postIdValue = textarea.dataset.cmPostId || '';
  const getPostId = () => postIdValue;

  const completionSources = [];
  if (citationsUrl) {
    completionSources.push(makeCitationCompletionSource(citationsUrl));
  }
  if (assetsUrl) {
    completionSources.push(makeAssetCompletionSource(assetsUrl, getPostId));
  }

  // Cheatsheet-driven snippets + class-name hints. The data is stamped
  // onto the textarea as JSON so we don't need a round-trip.
  let fenceSnippets = [];
  let inlineClasses = [];
  try {
    if (textarea.dataset.cmFenceSnippets) {
      fenceSnippets = JSON.parse(textarea.dataset.cmFenceSnippets);
    }
    if (textarea.dataset.cmInlineClasses) {
      inlineClasses = JSON.parse(textarea.dataset.cmInlineClasses);
    }
  } catch (err) {
    // Malformed JSON — leave snippet completion off but don't break the editor.
    console.warn('CM6: failed to parse snippet data', err);
  }
  if (fenceSnippets.length || inlineClasses.length) {
    completionSources.push(makeSnippetCompletionSource(fenceSnippets, inlineClasses));
  }

  const linterExtensions = [];
  if (lintUrl) {
    linterExtensions.push(
      linter(makeLintSource(lintUrl, getPostId), {
        delay: 500,
      }),
    );
    linterExtensions.push(lintGutter());
  }

  const state = EditorState.create({
    doc: textarea.value || '',
    extensions: [
      lineNumbers(),
      highlightActiveLine(),
      highlightActiveLineGutter(),
      history(),
      foldGutter(),
      drawSelection(),
      indentOnInput(),
      bracketMatching(),
      closeBrackets(),
      autocompletion({
        override: completionSources.length ? completionSources : undefined,
        activateOnTyping: true,
      }),
      rectangularSelection(),
      crosshairCursor(),
      highlightSelectionMatches(),
      EditorView.lineWrapping,
      EditorState.tabSize.of(4),
      syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
      markdown(),
      atpMarkdownDecorations,
      ...linterExtensions,
      keymap.of([
        indentWithTab,
        ...closeBracketsKeymap,
        ...defaultKeymap,
        ...searchKeymap,
        ...historyKeymap,
        ...foldKeymap,
        ...completionKeymap,
      ]),
      updateListener,
      EditorView.theme({
        '&': {
          fontSize: '14px',
          border: '1px solid var(--border-color)',
          borderRadius: '4px',
          background: 'var(--body-bg)',
          color: 'var(--body-fg)',
          maxHeight: '70vh',
          width: '100%',
          maxWidth: 'none',
        },
        '.cm-scroller': {
          fontFamily:
            "ui-monospace, SFMono-Regular, Menlo, Monaco, 'Cascadia Mono', Consolas, monospace",
          lineHeight: '1.55',
          overflow: 'auto',
        },
        '.cm-content': {
          padding: '10px 8px',
          caretColor: 'var(--body-fg)',
        },
        '.cm-gutters': {
          background: 'var(--darkened-bg)',
          color: 'var(--body-quiet-color)',
          border: 'none',
          borderRight: '1px solid var(--hairline-color)',
        },
        '.cm-activeLine': {
          background: 'var(--selected-row, rgba(127,127,127,0.08))',
        },
        '.cm-activeLineGutter': {
          background: 'var(--selected-row, rgba(127,127,127,0.08))',
        },
        '.cm-selectionBackground, ::selection': {
          background: 'var(--selected-bg, #b5d6fb) !important',
        },
        '.cm-cursor': { borderLeftColor: 'var(--body-fg)' },
        '.cm-tooltip': {
          background: 'var(--body-bg)',
          color: 'var(--body-fg)',
          border: '1px solid var(--border-color)',
        },
        '.cm-tooltip.cm-tooltip-autocomplete > ul > li[aria-selected]': {
          background: 'var(--selected-bg, #b5d6fb)',
          color: 'var(--body-fg)',
        },

        // Search / replace panel — native form controls don't inherit
        // dark theme by default, so style them explicitly.
        '.cm-panels': {
          background: 'var(--darkened-bg)',
          color: 'var(--body-fg)',
          borderTop: '1px solid var(--border-color)',
        },
        '.cm-panels.cm-panels-bottom': {
          borderTop: '1px solid var(--border-color)',
        },
        '.cm-panel': {
          background: 'var(--darkened-bg)',
          color: 'var(--body-fg)',
          padding: '6px 8px',
        },
        '.cm-panel.cm-search label': {
          color: 'var(--body-fg)',
          fontSize: '12px',
          marginRight: '8px',
          display: 'inline-flex',
          alignItems: 'center',
          gap: '4px',
        },
        '.cm-panel input, .cm-panel input[type=text], .cm-panel input[type=search]': {
          background: 'var(--body-bg)',
          color: 'var(--body-fg)',
          border: '1px solid var(--border-color)',
          borderRadius: '3px',
          padding: '3px 6px',
          fontSize: '12px',
        },
        '.cm-panel input[type=checkbox]': {
          accentColor: 'var(--link-fg, #447e9b)',
        },
        '.cm-panel button': {
          background: 'var(--button-bg)',
          color: 'var(--button-fg)',
          border: '1px solid var(--border-color)',
          borderRadius: '3px',
          padding: '3px 8px',
          margin: '0 2px',
          fontSize: '12px',
          cursor: 'pointer',
        },
        '.cm-panel button:hover': { background: 'var(--button-hover-bg)' },
        '.cm-panel button[name=close]': {
          background: 'transparent',
          color: 'var(--body-fg)',
          border: '0',
        },
        '.cm-searchMatch': {
          background: 'var(--message-warning-bg, #ffc)',
          color: '#222',
          outline: '1px solid rgba(0,0,0,0.2)',
        },
        '.cm-searchMatch.cm-searchMatch-selected': {
          background: '#f5dd5d',
          color: '#222',
        },

        // Lint gutter + diagnostics — keep readable in both themes.
        '.cm-lint-marker': { width: '0.8em', height: '0.8em' },
        '.cm-tooltip-lint': {
          background: 'var(--body-bg)',
          color: 'var(--body-fg)',
          border: '1px solid var(--border-color)',
          padding: '4px 8px',
          borderRadius: '3px',
          maxWidth: '360px',
        },
        '.cm-diagnostic-warning': {
          borderLeft: '3px solid #f0ad4e',
        },
        '.cm-diagnostic-error': { borderLeft: '3px solid #d9534f' },
        '.cm-diagnostic-info': { borderLeft: '3px solid #5bc0de' },

        // ATProject custom-token decorations.
        '.cm-atp-asset': {
          color: '#4da6ff',
          textDecoration: 'underline dotted',
          textUnderlineOffset: '2px',
        },
        '.cm-atp-citation': {
          color: '#b48ead',
          fontWeight: '500',
        },
        '.cm-atp-admonition': {
          color: '#a3be8c',
          fontWeight: '600',
        },
        '.cm-atp-footnote': {
          color: '#d08770',
        },
      }),
    ],
  });

  const wrapper = document.createElement('div');
  wrapper.className = 'cm-post-editor-wrapper';
  wrapper.style.width = '100%';
  wrapper.style.display = 'block';
  textarea.style.display = 'none';
  textarea.parentNode.insertBefore(wrapper, textarea);

  const view = new EditorView({ state, parent: wrapper });

  // Expose the view on window so sibling admin widgets (citation picker,
  // preview button, future tooling) can insert at cursor or read state
  // without touching the textarea directly.
  window.__atpPostEditorView = view;

  // Searchable markdown-reference palette (Ctrl/Cmd-/ or the "Markdown helper"
  // button) that inserts snippets at the cursor. Data is the same cheatsheet
  // stamped onto the textarea as JSON.
  try {
    if (textarea.dataset.cmCheatsheet) {
      mountCheatsheetPalette(view, JSON.parse(textarea.dataset.cmCheatsheet));
    }
  } catch (err) {
    console.warn('CM6: failed to mount markdown helper', err);
  }

  // Ensure the textarea is in sync on submit regardless of
  // whether a docChanged event fired between the last keystroke
  // and the submit (e.g. programmatic paste).
  const form = textarea.closest('form');
  if (form) {
    form.addEventListener('submit', () => syncToTextarea(view));
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initEditor);
} else {
  initEditor();
}
