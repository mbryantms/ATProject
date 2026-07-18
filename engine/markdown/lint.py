"""Single source of truth for authoring-time content lint.

Scans post markdown for problems an author should fix before publishing and
returns structured findings that carry character offsets. Everything that
surfaces these problems derives from :func:`lint_markdown`, so the detection
rules live in exactly one place instead of being re-implemented per consumer:

- the admin's CodeMirror lint gutter (needs ``from``/``to`` offsets),
- the "Preview" modal's warning list, and
- the save-time warning messages.

Checks:

* **asset** — ``@asset:key`` / ``@alias`` references (inside a markdown link or
  image target) that don't resolve to an attached PostAsset or a ready Asset.
* **citation** — ``[@key]`` / ``[-@key]`` / ``[@a; @b]`` and narrative ``@key``
  citations whose key isn't in the Source library. Code spans and asset-ref
  targets are excluded so they don't produce false positives.
* **link** — ``/posts/<slug>/`` internal links to a slug no Post has.
* **fence** — an odd number of ``:::`` fences (an unclosed admonition/div).

This is advisory guidance only; it never blocks a save.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# @asset:key / @alias inside a markdown link/image target. Mirrors the
# production asset_resolver preprocessor pattern so lint stays in sync with what
# actually resolves at render time.
ASSET_REF_RE = re.compile(r"!?\[[^\]]*\]\(@(asset:)?([a-zA-Z0-9_-]+)(?:\?[^\)]*)?\)")

_INTERNAL_LINK_RE = re.compile(r"\]\(/posts/([a-z0-9][a-z0-9\-_]*)/?\)")
_FENCE_RE = re.compile(r"^:::+.*$", re.MULTILINE)
# Citation key body (shared by bracketed + narrative matchers).
_CITE_KEY = r"[a-zA-Z0-9][\w:#$%&\-+?<>~/]*[a-zA-Z0-9]|[a-zA-Z0-9]"
_BRACKET_RE = re.compile(r"\[(-?@[^\]]+)\]")
_BRACKET_KEY_RE = re.compile(r"-?@([a-zA-Z0-9][\w:#$%&\-+?<>~/]*)")
_NARRATIVE_RE = re.compile(rf"(?<![@\[\\\w])@({_CITE_KEY})")
_CODE_SPAN_PATTERNS = (r"```[\s\S]*?```", r"~~~[\s\S]*?~~~", r"`[^`\n]+`")

@dataclass(frozen=True)
class LintFinding:
    """One authoring-lint problem, with its span in the source text."""

    kind: str  # "asset" | "citation" | "link" | "fence"
    label: str  # offending token, e.g. "@asset:foo" or "/posts/bar/"
    message: str
    start: int
    end: int
    severity: str = "warning"


def lint_markdown(content, *, post_assets=None, current_post_pk=None):
    """Return all :class:`LintFinding`s for ``content`` (empty list if clean).

    ``post_assets`` is the list of ``PostAsset`` rows attached to the post (used
    to resolve ``@alias`` references without a query); ``current_post_pk`` is
    accepted for symmetry and future self-reference checks.
    """
    if not content:
        return []
    findings = []
    findings.extend(_lint_assets(content, post_assets or []))
    findings.extend(_lint_citations(content))
    findings.extend(_lint_internal_links(content))
    findings.extend(_lint_fences(content))
    return findings


def group_labels(findings):
    """Collapse findings into ``{kind: [unique labels in first-seen order]}``.

    Used by the summary consumers (preview list, save-time messages). The
    ``fence`` kind has no meaningful label, so it maps to an empty list but is
    still present as a key when a fence problem exists.
    """
    grouped: dict[str, list[str]] = {}
    for f in findings:
        bucket = grouped.setdefault(f.kind, [])
        if f.label and f.label not in bucket:
            bucket.append(f.label)
    return grouped


def summarize(findings):
    """Human-readable summary lines — one per problem kind present.

    Used by the preview modal's warning list and the save-time messages, which
    both need a per-kind roll-up (with a deduped label list) rather than one
    entry per occurrence.
    """
    grouped = group_labels(findings)
    lines = []
    if grouped.get("asset"):
        lines.append(
            "Unresolved asset reference(s): "
            + ", ".join(grouped["asset"])
            + ". Attach the asset or fix the key/alias."
        )
    if grouped.get("citation"):
        lines.append(
            "Unknown citation key(s) — will render as [??key]: "
            + ", ".join(grouped["citation"])
            + ". Add to the Source library or correct the key."
        )
    if grouped.get("link"):
        lines.append(
            "Internal link(s) to unknown slug(s): " + ", ".join(grouped["link"]) + "."
        )
    if "fence" in grouped:
        lines.append(
            "Odd number of ::: fences detected — an admonition or fenced div "
            "is likely unclosed."
        )
    return lines


def to_diagnostics(findings):
    """Map findings to the ``@codemirror/lint`` Diagnostic shape."""
    return [
        {
            "from": f.start,
            "to": f.end,
            "severity": f.severity,
            "message": f.message,
        }
        for f in findings
    ]


# ---------------------------------------------------------------------------
# Individual checks (each returns a list of LintFinding with source offsets)
# ---------------------------------------------------------------------------


def _lint_assets(content, post_assets):
    if "@" not in content:
        return []
    from engine.models import Asset

    aliases = {pa.alias for pa in post_assets if pa.alias}
    post_keys = {pa.asset.key for pa in post_assets if pa.asset}

    candidates = {m.group(2) for m in ASSET_REF_RE.finditer(content)}
    known_globals = (
        set(
            Asset.objects.filter(
                key__in=candidates, is_deleted=False, status="ready"
            ).values_list("key", flat=True)
        )
        if candidates
        else set()
    )

    findings = []
    for m in ASSET_REF_RE.finditer(content):
        is_global = m.group(1) == "asset:"
        key = m.group(2)
        if is_global:
            if key in post_keys or key in known_globals:
                continue
            label = f"@asset:{key}"
        else:
            if key in aliases or key in post_keys or key in known_globals:
                continue
            label = f"@{key}"
        # Underline just the @…key span, not the whole image/link syntax.
        start = (m.start(1) - 1) if is_global else (m.start(2) - 1)
        findings.append(
            LintFinding(
                kind="asset",
                label=label,
                message=f"Unresolved asset reference: {label}",
                start=start,
                end=m.end(2),
            )
        )
    return findings


def _lint_citations(content):
    if "@" not in content:
        return []
    from engine.models import Source

    # Positions to skip: fenced/inline code and asset-ref link targets.
    stripped = []
    for pat in _CODE_SPAN_PATTERNS:
        stripped.extend((m.start(), m.end()) for m in re.finditer(pat, content))
    stripped.extend((m.start(), m.end()) for m in ASSET_REF_RE.finditer(content))

    def _skip(pos):
        return any(a <= pos < b for a, b in stripped)

    found = []  # (key, start, end)
    # Bracketed: [@key] / [-@key] / [@a; @b, pp. 3]
    for m in _BRACKET_RE.finditer(content):
        if _skip(m.start()):
            continue
        base = m.start(1)
        for km in _BRACKET_KEY_RE.finditer(m.group(1)):
            key = km.group(1).rstrip(".")
            key_start = base + km.start(1)
            found.append((key, key_start - 1, key_start + len(key)))
    # Narrative: @key not preceded by a word char / [ / @.
    for m in _NARRATIVE_RE.finditer(content):
        if _skip(m.start()):
            continue
        key = m.group(1).rstrip(".")
        found.append((key, m.start(), m.start(1) + len(key)))

    if not found:
        return []
    keys = {k for k, _, _ in found}
    known = set(
        Source.objects.filter(citation_key__in=keys).values_list(
            "citation_key", flat=True
        )
    )
    return [
        LintFinding(
            kind="citation",
            label=f"@{key}",
            message=f"Unknown citation key: @{key}",
            start=start,
            end=end,
        )
        for key, start, end in found
        if key not in known
    ]


def _lint_internal_links(content):
    matches = list(_INTERNAL_LINK_RE.finditer(content))
    if not matches:
        return []
    from engine.models import Post

    slugs = {m.group(1) for m in matches}
    known = set(Post.all_objects.filter(slug__in=slugs).values_list("slug", flat=True))
    return [
        LintFinding(
            kind="link",
            label=f"/posts/{m.group(1)}/",
            message=f"Internal link to unknown slug: /posts/{m.group(1)}/",
            start=m.start(1) - len("/posts/"),
            end=m.end(1) + 1,
        )
        for m in matches
        if m.group(1) not in known
    ]


def _lint_fences(content):
    fences = list(_FENCE_RE.finditer(content))
    if not fences or len(fences) % 2 == 0:
        return []
    last = fences[-1]
    return [
        LintFinding(
            kind="fence",
            label="",
            message="Unclosed ::: fence — missing matching ::: below.",
            start=last.start(),
            end=last.end(),
        )
    ]
