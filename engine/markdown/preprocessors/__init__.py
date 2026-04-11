# engine/markdown/preprocessors/__init__.py

# from .mention_handler import process_mentions

# Import other preprocessors
from .asset_resolver import asset_resolver_default
from .citation_escaper import citation_escaper_default

PREPROCESSORS = [
    # sanitize_input,
    # process_mentions,
    asset_resolver_default,  # Must be early in pipeline
    citation_escaper_default,  # Escape [@key] before Pandoc interprets them
    # Order matters - they run sequentially
]


def apply_preprocessors(text, context):
    """Apply all preprocessors in order"""
    for processor in PREPROCESSORS:
        text = processor(text, context)
    return text
