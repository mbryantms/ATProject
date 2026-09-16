# engine/markdown/postprocessors/dropcap_enhancer.py
"""
Postprocessor that prepares paragraphs for dropcaps.

Two kinds of paragraph get their opening letter hoisted into
``<span class="dropcap-letter">``:

1. The document's opening paragraph: the first ``<p>`` that is not inside a
   footnote, abstract, blockquote, figure, list, table, admonition or
   epigraph. It is tagged ``p.dropcap``. The span is inert on its own; the
   ``dropcap-<key>`` class the template puts on ``.markdownBody`` (from the
   post/page setting or the site default) is what styles it, so the cached
   HTML never needs re-rendering when those settings change.

2. Paragraphs the author marks explicitly::

       ::: {.dropcap-cinzel lines=2}
       Paragraph text…
       :::

   The classes move from the fenced div onto its first paragraph as
   ``p.dropcap.dropcap-cinzel`` (a bare ``.dropcap`` reuses the document
   style), ``lines=`` becomes ``--dropcap-lines`` on the paragraph, and the
   div is unwrapped when nothing else is on it. Paragraph-level classes win
   over the wrapper's because CSS custom properties inherit from the
   nearest ancestor.

``::: {.dropcap-not}`` around the opening paragraph switches the automatic
treatment off for the document (the next paragraph does not inherit it).

Leading punctuation (an opening quote or bracket) rides inside the span in
its own ``span.dropcap-punct`` so it stays attached to the letter; the
stylesheet renders it small in the body face. Paragraphs that open with
anything other than a letter (a digit, an image, math, code) are left
alone.
"""

from __future__ import annotations

import unicodedata

from bs4 import NavigableString, Tag

from engine.markdown.dropcaps import CLASS_PREFIX, clamp_lines, parse_class

from .utils import get_shared_soup, soup_to_html

LETTER_CLASS = "dropcap-letter"
PUNCT_CLASS = "dropcap-punct"
PARAGRAPH_CLASS = "dropcap"
NOT_CLASS = "dropcap-not"

# Containers whose paragraphs never receive the automatic opening dropcap.
_SKIP_TAGS = {"blockquote", "figure", "li", "table", "aside", "nav", "header", "footer"}
_SKIP_CLASSES = {
    "footnotes",
    "page-abstract",
    "admonition",
    "epigraph",
    "sidenote",
    "marginnote",
}
# Elements that, when met before any text, mean "this paragraph does not
# open with a letter".
_BLOCKING_TAGS = {
    "img",
    "svg",
    "math",
    "code",
    "pre",
    "picture",
    "video",
    "audio",
    "figure",
}
_BLOCKING_CLASSES = {"math", "citation"}


def _classes(tag: Tag) -> list[str]:
    value = tag.get("class", [])
    if isinstance(value, str):
        value = value.split()
    return list(value)


def _set_classes(tag: Tag, classes: list[str]) -> None:
    if classes:
        tag["class"] = list(dict.fromkeys(classes))
    elif tag.has_attr("class"):
        del tag["class"]


def _add_classes(tag: Tag, *new: str) -> None:
    _set_classes(tag, _classes(tag) + list(new))


def _in_skipped_container(p: Tag) -> bool:
    for parent in p.parents:
        if not isinstance(parent, Tag):
            continue
        if parent.name in _SKIP_TAGS:
            return True
        if _SKIP_CLASSES.intersection(_classes(parent)):
            return True
    return False


def _in_dropcap_not(p: Tag) -> bool:
    return any(
        isinstance(parent, Tag) and NOT_CLASS in _classes(parent)
        for parent in p.parents
    )


def _first_text_node(p: Tag) -> NavigableString | None:
    """The first non-blank text node of ``p``, or ``None`` if something
    that is not a letter (an image, math, code…) comes first."""
    for node in p.descendants:
        if isinstance(node, Tag):
            if node.name in _BLOCKING_TAGS or _BLOCKING_CLASSES.intersection(
                _classes(node)
            ):
                return None
            continue
        if isinstance(node, NavigableString):
            if type(node) is not NavigableString:  # comments, CDATA…
                continue
            if str(node).strip():
                return node
    return None


def _is_opening_punct(ch: str) -> bool:
    return unicodedata.category(ch) in {"Pi", "Ps", "Po"} and ch not in ".,;:!?…"


def wrap_opening_letter(p: Tag) -> bool:
    """Hoist the first letter of ``p`` into ``span.dropcap-letter``.

    Returns ``False`` (and leaves the paragraph untouched) when it already
    has one or does not open with a letter.
    """
    if p.find("span", class_=LETTER_CLASS) is not None:
        return True
    text_node = _first_text_node(p)
    if text_node is None:
        return False
    text = str(text_node)
    stripped = text.lstrip()
    leading_ws = text[: len(text) - len(stripped)]

    i = 0
    while i < len(stripped) and _is_opening_punct(stripped[i]):
        i += 1
    if i >= len(stripped) or not stripped[i].isalpha():
        return False
    punct = stripped[:i]
    letter = stripped[i]
    rest = stripped[i + 1 :]
    # Keep combining marks (e.g. a decomposed accent) with their base letter.
    while rest and unicodedata.combining(rest[0]):
        letter += rest[0]
        rest = rest[1:]

    # new_tag lives on the BeautifulSoup object at the root of the tree.
    root = text_node
    while root.parent is not None:
        root = root.parent

    span = root.new_tag("span")
    span["class"] = [LETTER_CLASS]
    if punct:
        punct_span = root.new_tag("span")
        punct_span["class"] = [PUNCT_CLASS]
        punct_span.string = punct
        span.append(punct_span)
    span.append(NavigableString(letter))

    text_node.replace_with(span)
    if leading_ws:
        span.insert_before(NavigableString(leading_ws))
    if rest:
        span.insert_after(NavigableString(rest))
    return True


def _first_paragraph_child(div: Tag) -> Tag | None:
    for child in div.children:
        if isinstance(child, NavigableString):
            if child.strip():
                return None
            continue
        if isinstance(child, Tag):
            return child if child.name == "p" else None
    return None


def _process_explicit_blocks(soup) -> None:
    for div in soup.find_all("div"):
        classes = _classes(div)
        if NOT_CLASS in classes:
            continue
        style_keys = [k for k in (parse_class(c) for c in classes) if k]
        wants_dropcap = PARAGRAPH_CLASS in classes or bool(style_keys)
        # Every dropcap-* class leaves the div: known ones move to the
        # paragraph, unknown ones (typos) are dropped rather than left to
        # match nothing.
        remaining = [
            c
            for c in classes
            if c != PARAGRAPH_CLASS and not c.startswith(CLASS_PREFIX)
        ]
        if not wants_dropcap:
            if remaining != classes:
                _set_classes(div, remaining)
            continue

        p = _first_paragraph_child(div)
        if p is None:
            # Nothing to decorate; drop the request but keep the block.
            _set_classes(div, remaining)
            continue

        new_classes = [PARAGRAPH_CLASS]
        if style_keys:
            new_classes.append(f"{CLASS_PREFIX}{style_keys[0]}")
        _add_classes(p, *new_classes)

        lines = clamp_lines(div.get("data-lines"))
        if div.has_attr("data-lines"):
            del div["data-lines"]
        if lines is not None:
            p["style"] = f"--dropcap-lines: {lines}"

        wrap_opening_letter(p)

        _set_classes(div, remaining)
        only_child = all(
            (isinstance(c, NavigableString) and not c.strip()) or c is p
            for c in div.children
        )
        if only_child and not remaining and not div.attrs:
            div.unwrap()


def _process_opening_paragraph(soup) -> None:
    for p in soup.find_all("p"):
        if _in_skipped_container(p):
            continue
        if _in_dropcap_not(p) or PARAGRAPH_CLASS in _classes(p):
            return  # the author already chose; nothing more to do
        if wrap_opening_letter(p):
            _add_classes(p, PARAGRAPH_CLASS)
        return  # only ever the first eligible paragraph


def enhance_dropcaps(html: str, context: dict) -> str:
    soup = get_shared_soup(html, context)
    if context.get("is_abstract") or context.get("fragment"):
        # Abstracts and nested caption renders are never a document opening.
        return soup_to_html(context, soup)
    _process_explicit_blocks(soup)
    _process_opening_paragraph(soup)
    return soup_to_html(context, soup)


def dropcap_enhancer_default(html: str, context: dict) -> str:
    return enhance_dropcaps(html, context)
