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
        context: Must contain 'post' key with Post instance

    Returns:
        Markdown with resolved asset URLs
    """
    # Lazy import to avoid circular import
    from engine.models import Asset, PostAsset

    post = context.get('post')
    # Note: post can be None for global @asset: references, which still work

    # Build alias map for this post (if post is available)
    alias_map = {}
    if post:
        for post_asset in post.post_assets.select_related('asset').all():
            if post_asset.alias:
                alias_map[post_asset.alias] = post_asset.asset

    # Pattern for @asset:key or @alias
    # Matches: ![alt](@asset:key) or ![alt](@alias) or [text](@asset:key)
    # Allow uppercase, lowercase, digits, hyphens, and underscores in keys
    pattern = r'(!?\[([^\]]*)\]\(@)(asset:)?([a-zA-Z0-9_-]+)(\?[^\)]*)?\)'

    def replace_asset_ref(match):
        # Group 0: entire match
        # Group 1: optional ! + [ + text + ](@
        # Group 2: text inside brackets (alt/link text)
        # Group 3: optional "asset:"
        # Group 4: asset key
        # Group 5: optional query params
        is_image = match.group(0).startswith('!')  # Check if it's an image
        link_text = match.group(2)  # Alt text or link text
        is_global = match.group(3) == 'asset:'  # Has @asset: prefix
        key = match.group(4)  # Asset key or alias
        query_params = match.group(5) or ''  # Optional ?width=800

        asset = None
        asset_metadata = {}

        if is_global:
            # Global asset reference: @asset:key
            # Use cache to avoid repeated DB queries
            cache_key = f'asset:{key}'
            asset = cache.get(cache_key)

            if not asset:
                try:
                    # Only use ready assets (not draft or archived)
                    asset = Asset.objects.get(
                        key=key,
                        is_deleted=False,
                        status='ready'
                    )
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
                    asset = Asset.objects.get(
                        key=key,
                        is_deleted=False,
                        status='ready'
                    )
                except Asset.DoesNotExist:
                    return match.group(0)

        if not asset:
            return match.group(0)

        # Get PostAsset for custom metadata (if post is available)
        if post:
            try:
                # If we matched by alias (not global), use the alias to find the specific PostAsset
                if not is_global and key in alias_map:
                    post_asset = post.post_assets.get(alias=key)
                else:
                    # For global asset references, there might be multiple PostAssets
                    # for the same asset (with different aliases or positions)
                    # Use the first one found
                    post_asset = post.post_assets.filter(asset=asset).first()

                if post_asset:
                    alt_text = post_asset.get_alt_text() or link_text
                    asset_metadata['caption'] = post_asset.get_caption()
                else:
                    # No PostAsset found, use asset defaults
                    alt_text = asset.alt_text or link_text
                    asset_metadata['caption'] = asset.caption
            except PostAsset.DoesNotExist:
                alt_text = asset.alt_text or link_text
                asset_metadata['caption'] = asset.caption
        else:
            alt_text = asset.alt_text or link_text
            asset_metadata['caption'] = asset.caption

        # Build asset URL with data attributes for postprocessor
        # Store metadata in data attributes for later processing
        asset_url = asset.file.url

        # Parse query parameters
        params = {}
        if query_params:
            for param in query_params[1:].split('&'):  # Skip leading ?
                if '=' in param:
                    k, v = param.split('=', 1)
                    params[k] = v

        # Add special marker for postprocessor with metadata
        # Format: ![alt](URL#asset-data:key:type:width:height:caption:display_width=800)
        metadata_str = f"#asset-data:{asset.key}:{asset.asset_type}"

        if asset.width:
            metadata_str += f":{asset.width}"
        if asset.height:
            metadata_str += f":{asset.height}"
        if asset_metadata.get('caption'):
            # URL-encode caption
            import urllib.parse
            caption_encoded = urllib.parse.quote(asset_metadata['caption'])
            metadata_str += f":caption={caption_encoded}"

        # Add query params to metadata
        # Map 'width' and 'height' params to 'display_width' and 'display_height'
        for k, v in params.items():
            if k == 'width':
                metadata_str += f":display_width={v}"
            elif k == 'height':
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
