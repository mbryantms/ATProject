# # engine/markdown/extensions/header_attributes.py
# """
# A Markdown extension that:
# - Sets id attributes on heading elements (h1–h6) based on their text for deep linking.
# - Converts the heading content into an anchor link to its own section.
# - Wraps each heading and all following content up to the next heading of the same or higher level
#   into a <section> element with:
#     - id equal to the heading slug
#     - classes including the nesting level (level1..level6) and "block"
#     - optional extra classes from configuration
#
# Notes:
# - Duplicate headings get uniquified slugs by appending -2, -3, ...
# - The anchor inside the heading gets a title like: "Link to section: § '<Heading Text>'".
# - Both the heading and the wrapping section receive the same id to satisfy the requirement.
#   (Although duplicate IDs in HTML are not ideal, we follow the specification provided.)
# """
#
# import re
# from typing import Dict, List, Optional
# from xml.etree import ElementTree as ET
#
# from markdown.extensions import Extension
# from markdown.treeprocessors import Treeprocessor
#
# _HEADING_TAGS = {f"h{i}" for i in range(1, 7)}
#
#
# def _text_content(elem: ET.Element) -> str:
#     parts: List[str] = []
#     for t in elem.itertext():
#         parts.append(t)
#     return "".join(parts).strip()
#
#
# def _slugify(text: str) -> str:
#     text = text.strip().lower()
#     # Replace apostrophes and similar quotes
#     text = re.sub(r"[’'\"]", "", text)
#     # Replace non-alphanumeric with dashes
#     text = re.sub(r"[^a-z0-9]+", "-", text)
#     # Collapse multiple dashes
#     text = re.sub(r"-+", "-", text)
#     return text.strip("-") or "section"
#
#
# class HeaderSectionizer(Treeprocessor):
#     def __init__(
#         self,
#         md,
#         *,
#         set_heading_id: bool = True,
#         section_classes: Optional[List[str]] = None,
#         add_data_attributes: bool = True,
#     ):
#         super().__init__(md)
#         self.set_heading_id = set_heading_id
#         self.section_classes = section_classes or ["block"]
#         self.add_data_attributes = add_data_attributes
#         self._used_slugs: Dict[str, int] = {}
#
#     def unique_slug(self, base: str) -> str:
#         count = self._used_slugs.get(base, 0)
#         if count == 0:
#             self._used_slugs[base] = 1
#             return base
#         # Already used; increment and append
#         count += 1
#         self._used_slugs[base] = count
#         return f"{base}-{count}"
#
#     def _process_container(self, parent: ET.Element, start_index: int = 0):
#         # Iterate over children of the given parent and wrap headings into sections.
#         i = start_index
#         while True:
#             children = list(parent)
#             if i >= len(children):
#                 break
#             node = children[i]
#             tag = node.tag.lower() if isinstance(node.tag, str) else ""
#             if tag in _HEADING_TAGS:
#                 level = int(tag[1])
#                 heading_text = _text_content(node)
#                 base_slug = _slugify(heading_text)
#                 slug = self.unique_slug(base_slug)
#
#                 # Prepare anchor inside heading. Avoid creating duplicate or nested <a> tags.
#                 existing_children = list(node)
#                 only_child_is_a = (
#                     len(existing_children) == 1
#                     and isinstance(existing_children[0].tag, str)
#                     and existing_children[0].tag.lower() == "a"
#                     and (node.text is None or node.text == "")
#                     and (
#                         existing_children[0].tail is None
#                         or existing_children[0].tail == ""
#                     )
#                 )
#
#                 if only_child_is_a:
#                     # Reuse existing anchor
#                     a = existing_children[0]
#                     a.set("href", f"#{slug}")
#                     a.set("title", f"Link to section: § '{heading_text}'")
#                 else:
#                     # Create a single anchor and move all heading content into it, flattening any nested anchors.
#                     a = ET.Element("a")
#                     a.set("href", f"#{slug}")
#                     a.set("title", f"Link to section: § '{heading_text}'")
#
#                     # Add leading text if present
#                     if node.text:
#                         a.text = node.text or ""
#                     node.text = None
#
#                     # Move/flatten children
#                     for child in existing_children:
#                         node.remove(child)
#                         if isinstance(child.tag, str) and child.tag.lower() == "a":
#                             # Flatten this anchor: move its text and children into our anchor
#                             if child.text:
#                                 if a.text:
#                                     a.text += child.text
#                                 else:
#                                     a.text = child.text
#                             for grand in list(child):
#                                 child.remove(grand)
#                                 a.append(grand)
#                             # Preserve tail by appending as text after current contents
#                             if child.tail:
#                                 # Add tail either to the last element's tail or append to a.text
#                                 if len(a):
#                                     last = a[-1]
#                                     last.tail = (last.tail or "") + child.tail
#                                 else:
#                                     a.text = (a.text or "") + child.tail
#                         else:
#                             a.append(child)
#
#                     node.append(a)
#
#                 # Set heading id if configured
#                 if self.set_heading_id:
#                     node.set("id", slug)
#                 # Ensure heading element has 'heading' class
#                 existing_class = node.get("class") or ""
#                 classes = existing_class.split() if existing_class else []
#                 if "heading" not in classes:
#                     classes.append("heading")
#                 if classes:
#                     node.set("class", " ".join(classes))
#                 if self.add_data_attributes:
#                     node.set("data-level", str(level))
#                     node.set("data-slug", slug)
#
#                 # Wrap into section and move following siblings until next heading of same or higher level
#                 section = ET.Element("section")
#                 # classes: provided + levelN + block (ensure uniqueness)
#                 classes = list(
#                     dict.fromkeys(
#                         (self.section_classes or []) + [f"level{level}", "block"]
#                     )
#                 )
#                 section.set("class", " ".join(classes).strip())
#                 section.set("id", slug)
#                 if self.add_data_attributes:
#                     section.set("data-level", str(level))
#                     section.set("data-slug", slug)
#
#                 # Replace heading node at parent position with section, and append heading inside section
#                 parent.remove(node)
#                 section.append(node)
#                 parent.insert(i, section)
#
#                 # Now gather following siblings into this section until break condition
#                 # Refresh children list from parent after modification
#                 j = i + 1
#                 while True:
#                     siblings = list(parent)
#                     if j >= len(siblings):
#                         break
#                     nxt = siblings[j]
#                     nxt_tag = nxt.tag.lower() if isinstance(nxt.tag, str) else ""
#                     if nxt_tag in _HEADING_TAGS:
#                         nxt_level = int(nxt_tag[1])
#                         if nxt_level <= level:
#                             break  # stop collecting into this section
#                     # Move nxt into section
#                     parent.remove(nxt)
#                     section.append(nxt)
#                     # Do not advance j; we just removed the element at j
#
#                 # Recursively process the contents of this section, skipping the first child (the heading itself)
#                 self._process_container(section, start_index=1)
#
#                 # Advance i past this section (which occupies one position in parent)
#                 i += 1
#             else:
#                 i += 1
#
#     def run(
#         self, root: ET.Element
#     ):
#         # Reset slug counter for each render to prevent ID increment on page refresh
#         self._used_slugs.clear()
#
#         # Process the entire tree, including headings nested inside sections
#         self._process_container(root, start_index=0)
#         return root
#
#
# class HeaderAttributesExtension(Extension):
#     def __init__(self, **kwargs):
#         # Defaults can be overridden via extension_configs
#         self.config = {
#             "set_heading_id": [True, "Set id on heading elements"],
#             "section_classes": [["block"], "Base classes to apply to section wrappers"],
#             "add_data_attributes": [True, "Add data-level and data-slug attributes"],
#         }
#         super().__init__(**kwargs)
#
#     def extendMarkdown(self, md):
#         set_heading_id = self.getConfig("set_heading_id")
#         section_classes = self.getConfig("section_classes")
#         add_data_attributes = self.getConfig("add_data_attributes")
#         md.treeprocessors.register(
#             HeaderSectionizer(
#                 md,
#                 set_heading_id=set_heading_id,
#                 section_classes=section_classes,
#                 add_data_attributes=add_data_attributes,
#             ),
#             "header_attributes_sectionizer",
#             priority=15,
#         )
#
#
# def makeExtension(**kwargs):
#     return HeaderAttributesExtension(**kwargs)
