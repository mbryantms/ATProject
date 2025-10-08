# engine/templatetags/markdown_tags.py

from django import template
from django.utils.safestring import mark_safe

from engine.markdown.renderer import render_markdown

register = template.Library()


@register.filter(name="markdown")
def markdown_filter(value):
    return mark_safe(render_markdown(value))


@register.filter(name="markdown_abstract")
def markdown_abstract_filter(value):
    """Render markdown for abstract sections (no block class on paragraphs)"""
    return mark_safe(render_markdown(value, context={"is_abstract": True}))


@register.simple_tag(takes_context=True)
def markdown_with_context(context, value):
    """Template tag that passes template context to processors"""
    processor_context = {
        "user": context.get("user"),
        "request": context.get("request"),
        "post": context.get("post"),
    }
    return mark_safe(render_markdown(value, context=processor_context))
