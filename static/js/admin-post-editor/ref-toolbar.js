/**
 * Mini toolbar for asset references: put the cursor inside an
 * ![alt](@asset:key) reference and a small toolbar appears with display
 * controls — width presets (the ?width= display parameter) and layout
 * classes ({.float-left} etc., the positioning classes the image
 * enhancer understands). Each action rewrites just that reference.
 */

import { showTooltip } from '@codemirror/view';
import { StateField } from '@codemirror/state';

// Full reference incl. optional ?params and optional {.attrs} block.
// Groups: 1=alt, 2=token, 3=?params, 4={attrs}
const REF_RE = /!\[([^\]]*)\]\(@((?:asset:)?[a-zA-Z0-9_-]+)(\?[^)]*)?\)(\{[^}]*\})?/g;

const FLOAT_CLASSES = ['float-left', 'float-center', 'float-right', 'width-full'];
const WIDTHS = [400, 800, 1200];

function findRefAt(state, pos) {
  const line = state.doc.lineAt(pos);
  REF_RE.lastIndex = 0;
  let m;
  while ((m = REF_RE.exec(line.text)) !== null) {
    const start = line.from + m.index;
    const end = start + m[0].length;
    if (pos >= start && pos <= end) {
      return {
        start,
        end,
        alt: m[1],
        token: m[2],
        params: m[3] || '',
        attrs: m[4] || '',
      };
    }
  }
  return null;
}

function rebuild(ref, { width, floatCls }) {
  // Preserve non-width params.
  const params = new URLSearchParams(ref.params.replace(/^\?/, ''));
  if (width === null) params.delete('width');
  else if (width !== undefined) params.set('width', String(width));
  const paramStr = params.toString() ? `?${params.toString()}` : '';

  // Preserve non-layout classes in the attr block.
  let classes = (ref.attrs.match(/\.[\w-]+/g) || []).map((c) => c.slice(1));
  if (floatCls !== undefined) {
    classes = classes.filter((c) => !FLOAT_CLASSES.includes(c) && c !== 'inline');
    if (floatCls) classes.push(floatCls);
  }
  const attrStr = classes.length ? `{${classes.map((c) => `.${c}`).join(' ')}}` : '';

  return `![${ref.alt}](@${ref.token}${paramStr})${attrStr}`;
}

function currentWidth(ref) {
  const params = new URLSearchParams(ref.params.replace(/^\?/, ''));
  return params.get('width');
}

function currentFloat(ref) {
  const classes = (ref.attrs.match(/\.[\w-]+/g) || []).map((c) => c.slice(1));
  return classes.find((c) => FLOAT_CLASSES.includes(c)) || null;
}

function buildToolbar(view, ref) {
  const bar = document.createElement('div');
  bar.className = 'cm-atp-ref-toolbar';

  const apply = (changes) => {
    const replacement = rebuild(ref, changes);
    view.dispatch({
      changes: { from: ref.start, to: ref.end, insert: replacement },
    });
    view.focus();
  };

  const addButton = (label, active, onClick, title) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = `cm-atp-ref-btn${active ? ' active' : ''}`;
    b.textContent = label;
    if (title) b.title = title;
    b.addEventListener('mousedown', (e) => {
      // mousedown, not click: keep the editor from losing selection first.
      e.preventDefault();
      onClick();
    });
    bar.appendChild(b);
    return b;
  };

  const group = (label) => {
    const s = document.createElement('span');
    s.className = 'cm-atp-ref-group';
    s.textContent = label;
    bar.appendChild(s);
  };

  const width = currentWidth(ref);
  group('width');
  for (const w of WIDTHS) {
    addButton(
      String(w),
      width === String(w),
      () => apply({ width: width === String(w) ? null : w }),
      `Display at ${w}px`,
    );
  }

  const float = currentFloat(ref);
  group('layout');
  for (const [cls, label, title] of [
    ['float-left', '◧', 'Float left'],
    ['float-center', '□', 'Center'],
    ['float-right', '◨', 'Float right'],
    ['width-full', '⬌', 'Full width'],
  ]) {
    addButton(
      label,
      float === cls,
      () => apply({ floatCls: float === cls ? null : cls }),
      title,
    );
  }

  return bar;
}

function refTooltip(state) {
  const sel = state.selection.main;
  if (!sel.empty) return null;
  const ref = findRefAt(state, sel.head);
  if (!ref) return null;
  return {
    pos: ref.start,
    above: false,
    strictSide: false,
    arrow: false,
    create: (view) => ({ dom: buildToolbar(view, ref) }),
  };
}

export function makeRefToolbarExtension() {
  const field = StateField.define({
    create: (state) => refTooltip(state),
    update(value, tr) {
      if (!tr.docChanged && !tr.selection) return value;
      return refTooltip(tr.state);
    },
    provide: (f) => showTooltip.from(f),
  });
  return field;
}
