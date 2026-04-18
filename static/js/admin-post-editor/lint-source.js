/**
 * CM6 linter source backed by the admin's lint-content endpoint.
 *
 * The server returns `{diagnostics: [{from, to, severity, message}]}`
 * with absolute offsets into the submitted text, which maps directly to
 * `@codemirror/lint`'s Diagnostic shape.
 */

function getCookie(name) {
  const cookies = document.cookie ? document.cookie.split('; ') : [];
  for (const c of cookies) {
    const [k, ...rest] = c.split('=');
    if (k === name) return decodeURIComponent(rest.join('='));
  }
  return '';
}

export function makeLintSource(url, getPostId) {
  return async (view) => {
    const content = view.state.doc.toString();
    if (!content) return [];

    const form = new FormData();
    form.append('content', content);
    const pid = getPostId && getPostId();
    if (pid) form.append('post_id', pid);

    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCookie('csrftoken') },
        body: form,
        credentials: 'same-origin',
      });
      if (!res.ok) return [];
      const data = await res.json();
      return (data.diagnostics || []).map((d) => ({
        from: Math.max(0, Math.min(d.from, content.length)),
        to: Math.max(0, Math.min(d.to, content.length)),
        severity: d.severity || 'warning',
        message: d.message || '',
      }));
    } catch {
      return [];
    }
  };
}
