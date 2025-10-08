# # core/markdown/extensions/custom_ext.py
# """
# Extensions can register their own processors within markdown's pipeline:
#
# 1. External Pre-Processors (apply_preprocessors)
#    ↓ (Raw markdown text)
#
# 2. Markdown Extension Preprocessors
#    ↓ (Lines of text)
#
# 3. Markdown Block Processors
#    ↓ (Parse structure)
#
# 4. Markdown Inline Processors
#    ↓ (Parse inline elements)
#
# 5. Markdown Tree Processors
#    ↓ (ElementTree)
#
# 6. Markdown Postprocessors
#    ↓ (HTML string)
#
# 7. External Post-Processors (apply_postprocessors)
#    ↓ (Final HTML)
#
#
#
#
#
#    Markdown renderer pipeline converted to pypandoc. The following extensions/features require conversion:
#
#   Native Pandoc Support (working out-of-box):
#
#   - Tables, fenced code, syntax highlighting, TOC, lists, abbreviations, footnotes, definition lists, task lists, strikethrough, superscript/subscript, smart typography
#
#   Require Conversion:
#
#   1. Custom Extensions (implement as Pandoc filters or HTML postprocessors):
#
#   - engine.markdown.extensions.header_attributes - Complex: wraps headings in sections, adds IDs, creates anchor links, adds data attributes
#   - engine.markdown.extensions.paragraph_classes - Simple: adds "block" class to paragraphs
#
#   2. PyMdown Features:
#
#   - pymdownx.mark (highlight/mark text) - implement as HTML postprocessor
#   - pymdownx.superfences mermaid support - implement as Pandoc filter or postprocessor
#
#   3. Existing Postprocessors:
#
#   All existing postprocessors (sanitize_html, modify_external_links, add_heading_copy_buttons) will continue to work with Pandoc's HTML output.
# """
#
# import re
#
# from markdown.extensions import Extension
# from markdown.postprocessors import Postprocessor
# from markdown.preprocessors import Preprocessor
# from markdown.treeprocessors import Treeprocessor
#
#
# class CustomPreprocessor(Preprocessor):
#     """Runs during markdown's preprocessing phase"""
#
#     def run(self, lines):
#         # Modify lines of text before block parsing
#         new_lines = []
#         for line in lines:
#             # Example: Convert [[WikiLink]] syntax
#             line = re.sub(r"\[\[(.+?)\]\]", r"[\1](/wiki/\1/)", line)
#             new_lines.append(line)
#         return new_lines
#
#
# class CustomTreeprocessor(Treeprocessor):
#     """Runs on the ElementTree after parsing"""
#
#     def run(self, root):
#         # Modify the element tree
#         for elem in root.iter("code"):
#             # Add classes to code blocks
#             if "class" in elem.attrib:
#                 elem.attrib["class"] += " custom-code"
#             else:
#                 elem.attrib["class"] = "custom-code"
#
#
# class CustomPostprocessor(Postprocessor):
#     """Runs on the HTML string after serialization"""
#
#     def run(self, text):
#         # Final modifications to HTML string
#         # (But prefer external post-processors for complex HTML manipulation)
#         return text
#
#
# class CustomExtension(Extension):
#     def extendMarkdown(self, md):
#         # Register processors with priority
#         md.preprocessors.register(
#             CustomPreprocessor(md), "custom_pre", priority=175  # Higher = runs earlier
#         )
#
#         md.treeprocessors.register(CustomTreeprocessor(md), "custom_tree", priority=15)
#
#         md.postprocessors.register(CustomPostprocessor(md), "custom_post", priority=25)
#
#
# def makeExtension(**kwargs):
#     return CustomExtension(**kwargs)
