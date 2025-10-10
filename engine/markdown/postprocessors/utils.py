"""Utilities to support efficient BeautifulSoup usage in postprocessors."""

from __future__ import annotations

from bs4 import BeautifulSoup

_SHARED_SOUP_KEY = "__shared_soup"
_SHARED_SOURCE_KEY = "__shared_soup_source"


def get_shared_soup(html: str, context: dict) -> BeautifulSoup:
    """Return a shared BeautifulSoup instance for the given HTML.
    Postprocessors often need to mutate the rendered HTML using BeautifulSoup.
    Parsing the document for every postprocessor is expensive, so we cache the
    parsed tree in the rendering context.  The cache is invalidated if the
    source HTML string changes between postprocessors.
    """
    soup = context.get(_SHARED_SOUP_KEY)
    source = context.get(_SHARED_SOURCE_KEY)
    if soup is None or source != html:
        soup = BeautifulSoup(html, "html.parser")
        context[_SHARED_SOUP_KEY] = soup
        context[_SHARED_SOURCE_KEY] = html
    return soup


def soup_to_html(context: dict, soup: BeautifulSoup | None = None) -> str:
    """Serialise the shared soup back to HTML and update the cache."""
    if soup is None:
        soup = context.get(_SHARED_SOUP_KEY)
    html = str(soup) if soup is not None else ""
    context[_SHARED_SOURCE_KEY] = html
    context[_SHARED_SOUP_KEY] = soup
    return html


def clear_shared_soup(context: dict) -> None:
    """Remove any cached soup information from the context."""
    context.pop(_SHARED_SOUP_KEY, None)
    context.pop(_SHARED_SOURCE_KEY, None)
