"""
Postprocessor that enhances document/data asset links with metadata.
"""

from bs4 import BeautifulSoup
import urllib.parse


def enhance_document_assets(html: str, context: dict) -> str:
    """
    Enhance document and data asset links with file info.
    """
    # Lazy import to avoid circular import
    from engine.models import Asset

    soup = BeautifulSoup(html, "html.parser")

    for link in soup.find_all('a'):
        href = link.get('href', '')

        if '#asset-data:' not in href:
            continue

        url_parts = href.split('#asset-data:')
        base_url = url_parts[0]
        metadata_str = url_parts[1]
        metadata_parts = metadata_str.split(':')

        if len(metadata_parts) < 2:
            continue

        asset_key = metadata_parts[0]
        asset_type = metadata_parts[1]

        if asset_type not in ['document', 'data']:
            continue

        try:
            asset = Asset.objects.get(key=asset_key)
        except Asset.DoesNotExist:
            continue

        # Clean href
        link['href'] = base_url

        # Add download attribute
        link['download'] = ''

        # Add data attributes for CSS styling
        link['data-asset-type'] = asset_type
        link['data-file-type'] = asset.file_extension[1:]  # Remove leading dot
        link['data-file-size'] = asset.human_file_size

        # Add file info to link text if desired
        if not link.get_text().strip():
            link.string = f"{asset.title} ({asset.file_extension.upper()}, {asset.human_file_size})"

    return str(soup)


def asset_document_enhancer_default(html: str, context: dict) -> str:
    """Register this in POSTPROCESSORS."""
    return enhance_document_assets(html, context)
