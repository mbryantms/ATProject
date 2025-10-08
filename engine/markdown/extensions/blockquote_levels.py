# # engine/services/blockquote_levels.py
# from markdown.extensions import Extension
# from markdown.treeprocessors import Treeprocessor
#
# """
# THIS NEEDS TO BE PLUGGED IN
#
# This should be put in the renderer:
#
# # mysite/utils/renderer.py
# from markdown import Markdown
# from django.utils.safestring import mark_safe
#
# from mysite.markdown_ext.blockquote_levels import BlockquoteLevelsExtension
#
# COMMON_EXTS = [
#     'extra',            # or your current set: footnotes, tables, etc.
#     'toc',
#     # ... other extensions you already use ...
# ]
#
# def render_markdown(text: str) -> str:
#     md = Markdown(extensions=COMMON_EXTS + [BlockquoteLevelsExtension()])
#     html = md.convert(text or "")
#     return mark_safe(html)
#
#
# How to call from template filter:
# # mysite/templatetags/markdown_extras.py
# from django import template
# from mysite.utils.markdown_renderer import render_markdown
#
# register = template.Library()
#
# @register.filter(is_safe=True)
# def md(value):
#     return render_markdown(value)
#
# And then in the template:
# {{ post.body|md }}
#
# Once wired it will support this syntax:
# > Level 1
# >
# > > Level 2
# > >
# > > > Level 3
#
# """
#
#
# class _BlockquoteLevels(Treeprocessor):
#     def run(self, root):
#         # depth-first assignment of classes
#         def visit(node, depth):
#             # Only count consecutive blockquote ancestors to get “nesting”
#             # (i.e., <blockquote> directly inside another <blockquote>).
#             if node.tag.lower() == "blockquote":
#                 # Compute depth by walking ancestors
#                 d = 1
#                 parent = node.getparent() if hasattr(node, "getparent") else None
#                 # If ElementTree lacks getparent, compute by recursion param instead:
#                 d = depth
#                 # Append/merge the class
#                 cls = node.get("class", "")
#                 cls_list = [c for c in cls.split() if c]
#                 level_class = f"blockquote-level-{d}"
#                 if level_class not in cls_list:
#                     cls_list.append(level_class)
#                 node.set("class", " ".join(cls_list))
#                 # Children of a blockquote increase depth for nested blockquotes
#                 for child in list(node):
#                     visit(child, d + 1)
#             else:
#                 for child in list(node):
#                     visit(child, depth)
#
#         visit(root, 1)
#
#
# class BlockquoteLevelsExtension(Extension):
#     def extendMarkdown(self, md):
#         # Ensure we run after the parser has built the tree, before serialization
#         md.treeprocessors.register(_BlockquoteLevels(md), "blockquote_levels", 15)
#
#
# def makeExtension(**kwargs):
#     return BlockquoteLevelsExtension(**kwargs)
