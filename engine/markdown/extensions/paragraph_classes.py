# # engine/markdown/extensions/paragraph_classes.py
# """
# Markdown extension to add classes to paragraph (<p>) elements via inline class markers
# at the end of paragraph text.
#
# Syntax:
# - Append a class list in braces at the end of a paragraph:
#     This is a paragraph {.lead .muted}
#
# - Class names must be prefixed by a dot within the braces and separated by spaces.
#   Valid characters for class names: letters, digits, underscore, and hyphen.
#
# Behavior:
# - The marker is removed from the rendered text and the classes are applied to the
#   enclosing <p> element's class attribute (merged with any existing classes).
# - Works whether the marker appears in the paragraph's text or in the tail of the last
#   inline child element.
# - Only affects <p> elements. Does not change code/pre blocks.
# """
#
# import re
# from typing import List, Optional
# from xml.etree import ElementTree as ET
#
# from markdown.extensions import Extension
# from markdown.treeprocessors import Treeprocessor
#
# # Pattern for a trailing class spec like:  {... .class-one .class_two}
# _CLASS_SPEC_RE = re.compile(r"\s*\{(?:\s*\.[A-Za-z0-9_-]+)+\}\s*$")
# # Pattern to extract class names from content inside braces
# _CLASS_NAME_RE = re.compile(r"\.[A-Za-z0-9_-]+")
#
#
# def _extract_trailing_class_spec_from_text(
#     text: Optional[str],
# ) -> tuple[Optional[str], Optional[List[str]]]:
#     """
#     If the given text ends with a class spec, return the text with the spec removed
#     and the list of classes. Otherwise return (text, None).
#     """
#     if not text:
#         return text, None
#     if not _CLASS_SPEC_RE.search(text):
#         return text, None
#
#     # Find the last opening brace that starts the class spec
#     # Simpler: search for the pattern and slice it off
#     m = _CLASS_SPEC_RE.search(text)
#     if not m:
#         return text, None
#     start = m.start()
#     spec = text[start:]
#     remaining = text[:start]
#
#     # Extract class names
#     classes = [s[1:] for s in _CLASS_NAME_RE.findall(spec)]
#     if not classes:
#         return text, None
#     return remaining.rstrip(), classes
#
#
# class ParagraphClassAssigner(Treeprocessor):
#     def __init__(self, md, classes: Optional[List[str]] = None):
#         super().__init__(md)
#         self.classes = [c for c in (classes or []) if isinstance(c, str) and c.strip()]
#
#     def run(self, root: ET.Element):
#         if not self.classes:
#             return root
#         # Iterate over all paragraph elements
#         for p in root.iter("p"):
#             existing = p.get("class") or ""
#             existing_list = existing.split() if existing else []
#             # Preserve order and uniqueness: existing first, then configured ones not already present
#             seen = set(existing_list)
#             merged = existing_list + [c for c in self.classes if c not in seen]
#             if merged:
#                 p.set("class", " ".join(merged))
#         return root
#
#
# class ParagraphClassesExtension(Extension):
#     def __init__(self, **kwargs):
#         self.config = {
#             "classes": [[], "Classes to add to every <p> element"],
#         }
#         super().__init__(**kwargs)
#
#     def extendMarkdown(self, md):
#         classes = self.getConfig("classes")
#         # Priority should run after inline parsing created <p> structure but before other tree processors
#         md.treeprocessors.register(
#             ParagraphClassAssigner(md, classes=classes), "paragraph_classes", priority=20
#         )
#
#
# def makeExtension(**kwargs):
#     return ParagraphClassesExtension(**kwargs)
