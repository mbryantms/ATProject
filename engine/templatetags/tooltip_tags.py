import json
import uuid

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

"""
Django template tags for Floating UI tooltips.

Usage in templates:
1. Load the tags: {% load tooltip_tags %}

2. Include your bundled JavaScript file with Floating UI
3. Use tooltip tags in your template

"""


class TooltipNode(template.Node):
    def __init__(self, nodelist, tooltip_content_nodelist, **kwargs):
        self.nodelist = nodelist
        self.tooltip_content_nodelist = tooltip_content_nodelist
        self.position = kwargs.get("position", "top")
        self.offset = kwargs.get("offset", 10)
        self.delay = kwargs.get("delay", 0)
        self.theme = kwargs.get("theme", "dark")
        self.trigger = kwargs.get("trigger", "hover")
        self.arrow = kwargs.get("arrow", True)
        self.max_width = kwargs.get("max_width", "200px")

    def render(self, context):
        # Render the main content (trigger element)
        trigger_content = self.nodelist.render(context)

        # Render the tooltip content
        tooltip_content = self.tooltip_content_nodelist.render(context)

        # Generate unique IDs
        trigger_id = f"tooltip-trigger-{uuid.uuid4().hex[:8]}"
        tooltip_id = f"tooltip-{uuid.uuid4().hex[:8]}"

        # Resolve template variables for options
        position = self._resolve_variable(self.position, context)
        offset = self._resolve_variable(self.offset, context)
        delay = self._resolve_variable(self.delay, context)
        theme = self._resolve_variable(self.theme, context)
        trigger = self._resolve_variable(self.trigger, context)
        arrow = self._resolve_variable(self.arrow, context)
        max_width = self._resolve_variable(self.max_width, context)

        # Create configuration object
        config = {
            "position": position,
            "offset": int(offset) if str(offset).isdigit() else 10,
            "delay": int(delay) if str(delay).isdigit() else 0,
            "theme": theme,
            "trigger": trigger,
            "arrow": (
                bool(arrow) if isinstance(arrow, bool) else str(arrow).lower() == "true"
            ),
            "maxWidth": max_width,
        }

        # Generate the HTML
        html = f"""
        <span id="{trigger_id}" class="tooltip-trigger" data-tooltip-target="{tooltip_id}" data-tooltip-config='{json.dumps(config)}'>
            {trigger_content}
        </span>
        <div id="{tooltip_id}" class="tooltip tooltip-{theme}" role="tooltip" style="display: none; max-width: {max_width};">
            <div class="tooltip-content">
                {tooltip_content}
            </div>
            {f'<div class="tooltip-arrow" data-popper-arrow></div>' if arrow else ''}
        </div>
        """

        return mark_safe(html)

    def _resolve_variable(self, value, context):
        """Resolve template variables or return the literal value"""
        if hasattr(value, "resolve"):
            try:
                return value.resolve(context)
            except template.VariableDoesNotExist:
                return str(value)
        return value


@register.tag("tooltip")
@register.tag("tooltip_content")
def do_tooltip(parser, token):
    """
    Usage:
    {% tooltip position="top" theme="dark" trigger="hover" delay="100" %}
        <button>Hover me</button>
    {% tooltip_content %}
        This is the tooltip content with {{ variable }}
    {% endtooltip %}
    """
    bits = token.split_contents()
    # tag_name = bits[0]

    # Parse arguments more carefully
    kwargs = {}
    i = 1
    while i < len(bits):
        bit = bits[i]
        if "=" in bit:
            key, value = bit.split("=", 1)

            # Handle quoted strings
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                # Remove quotes
                kwargs[key] = value[1:-1]
            else:
                # Handle unquoted template variables
                try:
                    kwargs[key] = parser.compile_filter(value)
                except template.TemplateSyntaxError:
                    # If it fails to parse as a filter, treat as literal string
                    kwargs[key] = value
        i += 1

    # Parse the trigger content
    try:
        nodelist = parser.parse(("tooltip_content",))
        parser.next_token()

        # Parse the tooltip content
        tooltip_content_nodelist = parser.parse(("endtooltip",))
        parser.delete_first_token()
    except template.TemplateSyntaxError as e:
        raise template.TemplateSyntaxError(f"Error parsing tooltip tag: {e}")

    return TooltipNode(nodelist, tooltip_content_nodelist, **kwargs)


# Additional utility tags
@register.simple_tag(takes_context=True)
def simple_tooltip(context, content, tooltip_text, **kwargs):
    """
    Simple tooltip for inline use:
    {% simple_tooltip "Click me" "This is a tooltip" position="top" theme="dark" %}
    """
    trigger_id = f"tooltip-trigger-{uuid.uuid4().hex[:8]}"
    tooltip_id = f"tooltip-{uuid.uuid4().hex[:8]}"

    # Default options
    options = {
        "position": "top",
        "theme": "dark",
        "trigger": "hover",
        "delay": 0,
        "arrow": True,
        "offset": 10,
        "maxWidth": "200px",
    }
    options.update(kwargs)

    config = json.dumps(
        {
            "position": options["position"],
            "offset": int(options["offset"]),
            "delay": int(options["delay"]),
            "theme": options["theme"],
            "trigger": options["trigger"],
            "arrow": bool(options["arrow"]),
            "maxWidth": options["maxWidth"],
        }
    )

    html = f"""
    <span id="{trigger_id}" class="tooltip-trigger" data-tooltip-target="{tooltip_id}" data-tooltip-config='{config}'>
        {escape(content)}
    </span>
    <div id="{tooltip_id}" class="tooltip tooltip-{options['theme']}" role="tooltip" style="display: none; max-width: {options['maxWidth']};">
        <div class="tooltip-content">
            {escape(tooltip_text)}
        </div>
        {f'<div class="tooltip-arrow" data-popper-arrow></div>' if options['arrow'] else ''}
    </div>
    """

    return mark_safe(html)
