"""
Preprocessor that resolves asset references to actual URLs.

Converts:
    ![Alt](@asset:my-diagram)      → ![Alt](/media/assets/2024/01/diagram.jpg)
    ![Alt](@my-alias)              → ![Alt](/media/assets/2024/01/diagram.jpg)
"""

import re

from django.core.cache import cache


def resolve_asset_keys(text: str, context: dict) -> str:
    """
    Resolve @asset: and @alias references to actual asset URLs.

    Args:
        text: Markdown text with asset references
        context: May contain a ``content_object`` (Page or Post) or legacy
            ``post`` key. Global asset references work without either.

    Returns:
        Markdown with resolved asset URLs
    """
    # Lazy import to avoid circular import
    from engine.models import Asset

    owner = context.get("content_object") or context.get("post")
    asset_relation = None
    if owner is not None and getattr(owner, "pk", None):
        asset_relation = getattr(owner, "post_assets", None) or getattr(
            owner, "page_assets", None
        )

    # Build the owner-local alias map when a saved content object is available.
    alias_map = {}
    if asset_relation is not None:
        for content_asset in asset_relation.select_related("asset").all():
            if content_asset.alias:
                alias_map[content_asset.alias] = content_asset.asset

    # Pattern for @asset:key or @alias
    # Matches: ![alt](@asset:key) or ![alt](@alias) or [text](@asset:key)
    # Allow uppercase, lowercase, digits, hyphens, and underscores in keys
    pattern = r"(!?\[([^\]]*)\]\(@)(asset:)?([a-zA-Z0-9_-]+)(\?[^\)]*)?\)"

    def replace_asset_ref(match):
        # Group 0: entire match
        # Group 1: optional ! + [ + text + ](@
        # Group 2: text inside brackets (alt/link text)
        # Group 3: optional "asset:"
        # Group 4: asset key
        # Group 5: optional query params
        is_image = match.group(0).startswith("!")  # Check if it's an image
        link_text = match.group(2)  # Alt text or link text
        is_global = match.group(3) == "asset:"  # Has @asset: prefix
        key = match.group(4)  # Asset key or alias
        query_params = match.group(5) or ""  # Optional ?width=800

        asset = None
        asset_metadata = {}

        if is_global:
            # Global asset reference: @asset:key
            # Use cache to avoid repeated DB queries
            cache_key = f"asset:{key}"
            asset = cache.get(cache_key)

            if not asset:
                try:
                    # Only use ready assets (not draft or archived)
                    asset = Asset.objects.get(key=key, is_deleted=False, status="ready")
                    cache.set(cache_key, asset, 3600)  # Cache 1 hour
                except Asset.DoesNotExist:
                    # Asset not found, return original
                    return match.group(0)
        else:
            # Post alias reference: @alias
            asset = alias_map.get(key)
            if not asset:
                # Try global key as fallback
                try:
                    asset = Asset.objects.get(key=key, is_deleted=False, status="ready")
                except Asset.DoesNotExist:
                    return match.group(0)

        if not asset:
            return match.group(0)

        # Apply content-local caption/alt overrides when the asset is attached.
        if asset_relation is not None:
            if not is_global and key in alias_map:
                content_asset = asset_relation.filter(alias=key).first()
            else:
                content_asset = asset_relation.filter(asset=asset).first()

            if content_asset:
                alt_text = content_asset.get_alt_text() or link_text
                asset_metadata["caption"] = content_asset.get_caption()
            else:
                alt_text = asset.alt_text or link_text
                asset_metadata["caption"] = asset.caption
        else:
            alt_text = asset.alt_text or link_text
            asset_metadata["caption"] = asset.caption

        # Build asset URL with data attributes for postprocessor
        # Store metadata in data attributes for later processing
        asset_url = asset.file.url

        # Parse query parameters
        params = {}
        if query_params:
            for param in query_params[1:].split("&"):  # Skip leading ?
                if "=" in param:
                    k, v = param.split("=", 1)
                    params[k] = v

        # Add special marker for postprocessor with metadata
        # Format: ![alt](URL#asset-data:key:type:width:height:caption:display_width=800)
        metadata_str = f"#asset-data:{asset.key}:{asset.asset_type}"

        if asset.width:
            metadata_str += f":{asset.width}"
        if asset.height:
            metadata_str += f":{asset.height}"
        if asset_metadata.get("caption"):
            # URL-encode caption
            import urllib.parse

            caption_encoded = urllib.parse.quote(asset_metadata["caption"])
            metadata_str += f":caption={caption_encoded}"

        # Add query params to metadata
        # Map 'width' and 'height' params to 'display_width' and 'display_height'
        for k, v in params.items():
            if k == "width":
                metadata_str += f":display_width={v}"
            elif k == "height":
                metadata_str += f":display_height={v}"
            else:
                metadata_str += f":{k}={v}"

        # Return with or without ! depending on whether it's an image reference
        prefix = "!" if is_image else ""
        return f"{prefix}[{alt_text}]({asset_url}{metadata_str})"

    return re.sub(pattern, replace_asset_ref, text)


def asset_resolver_default(text: str, context: dict) -> str:
    """
    Default configuration for asset_resolver.

    Register this in PREPROCESSORS.
    """
    return resolve_asset_keys(text, context)
