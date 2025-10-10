"""
Metadata extraction utilities for assets.

This module provides functions to extract rich metadata from various asset types:
- EXIF data from images (camera settings, GPS, etc.)
- Audio metadata (artist, album, genre, etc.)
- Document metadata (author, subject, page count, etc.)
- Color information from images
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from .storage_utils import ensure_local_file, open_field_file

logger = logging.getLogger(__name__)


def extract_image_metadata(asset) -> Dict[str, Any]:
    """
    Extract comprehensive metadata from image files.

    Returns dict with:
    - exif_data: Raw EXIF data (JSON)
    - camera_make, camera_model, lens
    - focal_length, aperture, shutter_speed, iso
    - captured_at: datetime
    - latitude, longitude
    - dpi, has_alpha, color_space, color_profile
    - dominant_colors, color_palette, average_color
    """
    metadata = {}

    try:
        from PIL import Image
        from PIL.ExifTags import GPSTAGS, TAGS

        if not asset.file:
            logger.warning(f"Asset {asset.key} has no file attached")
            return metadata

        file_obj = open_field_file(asset.file)

        with Image.open(file_obj) as img:
            img.load()
            logger.info(
                "Image opened: format=%s, mode=%s, size=%s",
                img.format,
                img.mode,
                img.size,
            )

            # Basic image properties
            metadata["has_alpha"] = img.mode in ("RGBA", "LA", "PA")
            metadata["color_space"] = img.mode

            # DPI information
            if "dpi" in img.info and img.info["dpi"]:
                metadata["dpi"] = int(img.info["dpi"][0])

            # ICC Color profile
            if "icc_profile" in img.info:
                metadata["color_profile"] = "Embedded ICC Profile"

            # Extract EXIF data
            exif = img.getexif()
            logger.info(
                "EXIF data check: exif=%s, count=%s",
                "present" if exif else "missing",
                len(exif) if exif else 0,
            )

            if exif:
                exif_data = {}

                # Also get extended EXIF data (ExifOffset IFD) - contains detailed camera settings
                exif_ifd = None
                try:
                    exif_ifd = exif.get_ifd(0x8769)  # ExifOffset IFD
                    if exif_ifd:
                        logger.info(
                            "Found ExifOffset IFD with %s tags", len(exif_ifd)
                        )
                    else:
                        logger.warning(
                            "No ExifOffset IFD found for %s", asset.key
                        )
                except Exception as exc:
                    logger.warning(
                        "Could not read ExifOffset IFD for %s: %s",
                        asset.key,
                        exc,
                    )

                # Combine both main EXIF and extended EXIF
                all_exif_items = list(exif.items())
                if exif_ifd:
                    all_exif_items.extend(list(exif_ifd.items()))

                logger.info(
                    "Processing %s total EXIF tags", len(all_exif_items)
                )

                for tag_id, value in all_exif_items:
                    tag = TAGS.get(tag_id, tag_id)

                    # Store original value for JSON serialization
                    json_value = value

                    # Convert various types to JSON-serializable formats
                    if isinstance(value, bytes):
                        try:
                            decoded = value.decode("utf-8", errors="ignore")
                            json_value = (
                                decoded.replace("\u0000", "").replace("\x00", "")
                            )
                            if not json_value.strip():
                                json_value = value.hex()
                        except Exception:
                            json_value = value.hex()
                    elif hasattr(value, "__iter__") and not isinstance(
                        value, (str, dict)
                    ):
                        try:
                            json_value = [
                                float(v) if hasattr(v, "__float__") else v
                                for v in value
                            ]
                        except Exception:
                            json_value = str(value)
                    elif hasattr(value, "numerator") and hasattr(
                        value, "denominator"
                    ):
                        json_value = (
                            float(value.numerator) / float(value.denominator)
                            if value.denominator != 0
                            else 0
                        )
                    elif isinstance(value, str):
                        json_value = value.replace("\u0000", "").replace(
                            "\x00", ""
                        )
                    else:
                        json_value = value

                    exif_data[tag] = json_value

                    if tag == "Make":
                        metadata["camera_make"] = str(value).strip()
                    elif tag == "Model":
                        metadata["camera_model"] = str(value).strip()
                    elif tag == "LensModel":
                        metadata["lens"] = str(value).strip()
                    elif tag == "FocalLength":
                        if hasattr(value, "numerator") and hasattr(
                            value, "denominator"
                        ):
                            metadata["focal_length"] = (
                                float(value) if value.denominator != 0 else 0
                            )
                        elif isinstance(value, (tuple, list)) and len(value) == 2:
                            metadata["focal_length"] = (
                                float(value[0]) / float(value[1])
                                if value[1] != 0
                                else 0
                            )
                        else:
                            try:
                                metadata["focal_length"] = float(value)
                            except Exception:
                                pass
                    elif tag in {"FNumber", "ApertureValue"}:
                        if hasattr(value, "numerator") and hasattr(
                            value, "denominator"
                        ):
                            metadata["aperture"] = (
                                float(value) if value.denominator != 0 else 0
                            )
                        elif isinstance(value, (tuple, list)) and len(value) == 2:
                            metadata["aperture"] = (
                                float(value[0]) / float(value[1])
                                if value[1] != 0
                                else 0
                            )
                        else:
                            try:
                                metadata["aperture"] = float(value)
                            except Exception:
                                pass
                    elif tag == "ExposureTime":
                        if hasattr(value, "numerator") and hasattr(
                            value, "denominator"
                        ):
                            if value.numerator == 1:
                                metadata["shutter_speed"] = (
                                    f"1/{int(value.denominator)}"
                                )
                            else:
                                metadata["shutter_speed"] = (
                                    f"{value.numerator}/{value.denominator}"
                                )
                        elif isinstance(value, (tuple, list)) and len(value) == 2:
                            if value[0] == 1:
                                metadata["shutter_speed"] = (
                                    f"1/{int(value[1])}"
                                )
                            else:
                                metadata["shutter_speed"] = (
                                    f"{value[0]}/{value[1]}"
                                )
                        elif isinstance(value, float):
                            if value < 1:
                                denominator = round(1 / value)
                                metadata["shutter_speed"] = f"1/{denominator}"
                            else:
                                metadata["shutter_speed"] = f"{value}s"
                        else:
                            metadata["shutter_speed"] = str(value)
                    elif tag in {
                        "ISOSpeedRatings",
                        "ISO",
                        "PhotographicSensitivity",
                    }:
                        try:
                            if isinstance(value, (tuple, list)):
                                metadata["iso"] = int(value[0])
                            else:
                                metadata["iso"] = int(value)
                        except Exception:
                            pass
                    elif tag in {"DateTimeOriginal", "DateTime"}:
                        try:
                            from django.utils import timezone

                            naive_dt = datetime.strptime(
                                str(value), "%Y:%m:%d %H:%M:%S"
                            )
                            metadata["captured_at"] = timezone.make_aware(
                                naive_dt, timezone.get_current_timezone()
                            )
                        except Exception:
                            pass

                gps_info = exif.get_ifd(0x8825)  # GPS IFD
                if gps_info:
                    gps_data = {}
                    for tag_id, value in gps_info.items():
                        tag = GPSTAGS.get(tag_id, tag_id)
                        gps_data[tag] = value

                    lat = _convert_gps_coordinate(
                        gps_data.get("GPSLatitude"),
                        gps_data.get("GPSLatitudeRef"),
                    )
                    lon = _convert_gps_coordinate(
                        gps_data.get("GPSLongitude"),
                        gps_data.get("GPSLongitudeRef"),
                    )

                    if lat is not None:
                        metadata["latitude"] = lat
                    if lon is not None:
                        metadata["longitude"] = lon

                metadata["exif_data"] = exif_data

            try:
                color_info = _extract_color_info(img)
                metadata.update(color_info)
            except Exception as exc:
                logger.warning(
                    "Failed to extract color info for %s: %s", asset.key, exc
                )

        try:
            file_obj.seek(0)
        except Exception:
            pass

        logger.info("Image metadata extracted for %s", asset.key)

    except Exception as exc:
        logger.error(f"Error extracting image metadata for {asset.key}: {exc}")
        import traceback

        logger.error(traceback.format_exc())

    return metadata


def extract_audio_metadata(asset) -> Dict[str, Any]:
    """
    Extract metadata from audio files using mutagen.

    Returns dict with:
    - artist, album, genre, year, track_number
    """
    metadata = {}

    try:
        from mutagen import File as MutagenFile

        if not asset.file:
            logger.warning(f"Asset {asset.key} has no file attached")
            return metadata

        file_obj = open_field_file(asset.file)
        audio = MutagenFile(file_obj, filename=asset.file.name)

        if audio is None:
            return metadata

        # Common tags across formats
        tag_mappings = {
            'artist': ['artist', 'TPE1', '©ART', 'ARTIST'],
            'album': ['album', 'TALB', '©alb', 'ALBUM'],
            'genre': ['genre', 'TCON', '©gen', 'GENRE'],
            'year': ['date', 'TDRC', '©day', 'DATE', 'year'],
            'track_number': ['tracknumber', 'TRCK', 'trkn', 'TRACKNUMBER'],
        }

        # Try to extract each field
        for field, possible_tags in tag_mappings.items():
            for tag in possible_tags:
                if tag in audio:
                    value = audio[tag]
                    # Handle list values (common in mutagen)
                    if isinstance(value, list) and len(value) > 0:
                        value = value[0]

                    # Convert to appropriate type
                    if field == 'year':
                        try:
                            # Extract year from various date formats
                            value_str = str(value)
                            if '-' in value_str:
                                value_str = value_str.split('-')[0]
                            metadata['year'] = int(value_str[:4])
                        except:
                            pass
                    elif field == 'track_number':
                        try:
                            # Handle "5/12" format
                            value_str = str(value)
                            if '/' in value_str:
                                value_str = value_str.split('/')[0]
                            metadata['track_number'] = int(value_str)
                        except:
                            pass
                    else:
                        metadata[field] = str(value).strip()
                    break  # Found the field, move to next

        try:
            file_obj.seek(0)
        except Exception:
            pass

    except ImportError:
        logger.warning(f"mutagen not installed - cannot extract audio metadata for {asset.key}")
    except Exception as e:
        logger.error(f"Error extracting audio metadata for {asset.key}: {e}")

    return metadata


def extract_document_metadata(asset) -> Dict[str, Any]:
    """
    Extract metadata from document files (primarily PDFs).

    Returns dict with:
    - author, subject, keywords, page_count
    """
    metadata = {}

    if asset.file_extension.lower() == 'pdf':
        try:
            from PyPDF2 import PdfReader

            if not asset.file:
                logger.warning(f"Asset {asset.key} has no file attached")
                return metadata

            try:
                file_obj = open_field_file(asset.file)
                reader = PdfReader(file_obj)
            except Exception as e:
                logger.error(f"Cannot open PDF file for {asset.key}: {e}")
                return metadata

            # Page count
            metadata['page_count'] = len(reader.pages)

            # PDF metadata
            if reader.metadata:
                if reader.metadata.author:
                    metadata['author'] = str(reader.metadata.author).strip()
                if reader.metadata.subject:
                    metadata['subject'] = str(reader.metadata.subject).strip()
                if hasattr(reader.metadata, 'keywords') and reader.metadata.keywords:
                    metadata['keywords'] = str(reader.metadata.keywords).strip()

            try:
                file_obj.seek(0)
            except Exception:
                pass

        except ImportError:
            logger.warning(f"PyPDF2 not installed - cannot extract PDF metadata for {asset.key}")
        except Exception as e:
            logger.error(f"Error extracting PDF metadata for {asset.key}: {e}")

    return metadata


def extract_video_metadata(asset) -> Dict[str, Any]:
    """
    Extract metadata from video files using ffprobe.

    This is already handled in utils.py populate_asset_metadata signal,
    but we include it here for completeness and future enhancements.

    Returns dict with video-specific metadata.
    """
    metadata = {}

    try:
        import json
        import subprocess

        if not asset.file:
            logger.warning(f"Asset {asset.key} has no file attached")
            return metadata

        with ensure_local_file(asset.file) as local_path:
            result = subprocess.run(
                [
                    'ffprobe',
                    '-v', 'quiet',
                    '-print_format', 'json',
                    '-show_format',
                    local_path
                ],
                capture_output=True,
                text=True,
                timeout=30
            )

        if result.returncode == 0:
            data = json.loads(result.stdout)
            format_data = data.get('format', {})
            tags = format_data.get('tags', {})

            # Extract metadata from tags (varies by container format)
            if 'artist' in tags:
                metadata['artist'] = tags['artist']
            if 'album' in tags:
                metadata['album'] = tags['album']
            if 'genre' in tags:
                metadata['genre'] = tags['genre']
            if 'creation_time' in tags:
                try:
                    from django.utils import timezone as tz
                    # Parse ISO format datetime (already timezone-aware)
                    dt = datetime.fromisoformat(
                        tags['creation_time'].replace('Z', '+00:00')
                    )
                    # Ensure it's in the configured timezone
                    metadata['captured_at'] = dt if tz.is_aware(dt) else tz.make_aware(dt)
                except:
                    pass

    except FileNotFoundError:
        logger.warning(f"ffprobe not found - cannot extract video metadata for {asset.key}")
    except Exception as e:
        logger.error(f"Error extracting video metadata for {asset.key}: {e}")

    return metadata


def extract_all_metadata(asset) -> Optional['AssetMetadata']:
    """
    Extract all available metadata for an asset and create/update AssetMetadata instance.

    This is the main entry point for metadata extraction.

    Args:
        asset: Asset instance

    Returns:
        AssetMetadata instance or None if extraction failed
    """
    from .models import AssetMetadata

    logger.info(f"Starting metadata extraction for asset: {asset.key} (type: {asset.asset_type})")

    # Validate file exists
    if not asset.file:
        logger.warning(f"Asset {asset.key} has no file attached - cannot extract metadata")
        return None

    # Basic accessibility check
    try:
        file_obj = open_field_file(asset.file)
        try:
            file_obj.seek(0)
        except Exception:
            pass
    except Exception as exc:
        logger.error(f"Unable to open asset file for {asset.key}: {exc}")
        return None

    metadata_dict = {}

    # Extract metadata based on asset type
    if asset.asset_type == 'image':
        logger.info(f"Extracting image metadata for {asset.key}")
        metadata_dict = extract_image_metadata(asset)
    elif asset.asset_type == 'audio':
        logger.info(f"Extracting audio metadata for {asset.key}")
        metadata_dict = extract_audio_metadata(asset)
    elif asset.asset_type == 'document':
        logger.info(f"Extracting document metadata for {asset.key}")
        metadata_dict = extract_document_metadata(asset)
    elif asset.asset_type == 'video':
        logger.info(f"Extracting video metadata for {asset.key}")
        metadata_dict = extract_video_metadata(asset)
    else:
        logger.warning(f"Unsupported asset type for metadata extraction: {asset.asset_type}")

    # Only create AssetMetadata if we actually extracted something useful
    if not metadata_dict:
        logger.warning(f"No metadata extracted for {asset.key} - metadata_dict is empty")
        return None

    logger.info(f"Successfully extracted {len(metadata_dict)} metadata fields for {asset.key}")

    try:
        # Get or create AssetMetadata instance
        metadata, created = AssetMetadata.objects.get_or_create(
            asset=asset,
            defaults=metadata_dict
        )

        if created:
            logger.info(f"Created new AssetMetadata for {asset.key} with {len(metadata_dict)} fields")
        else:
            logger.info(f"Updating existing AssetMetadata for {asset.key}")
            updated_fields = []

            # Update existing metadata - always update extracted data
            for field, value in metadata_dict.items():
                if value is not None:  # Only set non-None values
                    old_value = getattr(metadata, field, None)
                    setattr(metadata, field, value)
                    if old_value != value:
                        updated_fields.append(field)

            if updated_fields:
                logger.info(f"Updated fields: {', '.join(updated_fields)}")
                metadata.save()
            else:
                logger.info(f"No fields needed updating")

        # Log final saved values
        logger.info(f"Saved metadata for {asset.key}:")
        logger.info(f"  - Camera: {metadata.camera_make} {metadata.camera_model}")
        logger.info(f"  - ISO: {metadata.iso}, Aperture: {metadata.aperture}")
        logger.info(f"  - GPS: {metadata.latitude}, {metadata.longitude}")

        return metadata

    except Exception as e:
        logger.error(f"Error saving metadata for asset {asset.key}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


# Helper functions

def _convert_gps_coordinate(coord, ref):
    """
    Convert GPS coordinates from EXIF format to decimal degrees.

    Args:
        coord: Tuple of (degrees, minutes, seconds) - can be rationals or floats
        ref: Reference (N/S for latitude, E/W for longitude)

    Returns:
        Float coordinate in decimal degrees, or None if invalid
    """
    if not coord or not ref:
        return None

    try:
        # Handle different GPS coordinate formats
        # Format 1: Simple tuple of floats (39.0, 58.0, 57.3)
        # Format 2: Tuple of rationals ((39, 1), (58, 1), (57, 1))

        if len(coord) != 3:
            return None

        # Extract degrees, minutes, seconds
        def extract_value(val):
            """Extract float from either a rational tuple or direct float."""
            if isinstance(val, (int, float)):
                return float(val)
            elif isinstance(val, (tuple, list)) and len(val) == 2:
                # Rational format (numerator, denominator)
                return float(val[0]) / float(val[1]) if val[1] != 0 else 0
            elif hasattr(val, 'numerator') and hasattr(val, 'denominator'):
                # IFDRational
                return float(val) if val.denominator != 0 else 0
            else:
                return float(val)

        degrees = extract_value(coord[0])
        minutes = extract_value(coord[1])
        seconds = extract_value(coord[2])

        # Convert to decimal
        decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)

        # Apply direction
        if ref in ['S', 'W']:
            decimal = -decimal

        return decimal

    except (IndexError, TypeError, ValueError, ZeroDivisionError) as e:
        logger.warning(f"GPS coordinate conversion failed: {e}, coord={coord}, ref={ref}")
        return None


def _extract_color_info(img) -> Dict[str, Any]:
    """
    Extract color information from an image.

    Returns dict with:
    - dominant_colors: List of hex color codes
    - average_color: Single hex color code
    - color_palette: List of prominent colors
    """
    from PIL import Image
    import colorsys

    color_info = {}

    try:
        # Resize image for faster processing
        img_small = img.copy()
        img_small.thumbnail((150, 150))

        # Convert to RGB if needed
        if img_small.mode != 'RGB':
            img_small = img_small.convert('RGB')

        # Get color palette using quantize
        palette_img = img_small.quantize(colors=10)
        palette = palette_img.getpalette()

        # Extract dominant colors
        colors = []
        for i in range(10):
            r = palette[i * 3]
            g = palette[i * 3 + 1]
            b = palette[i * 3 + 2]
            hex_color = '#{:02x}{:02x}{:02x}'.format(r, g, b)
            colors.append(hex_color)

        color_info['dominant_colors'] = colors[:5]  # Top 5
        color_info['color_palette'] = colors

        # Calculate average color
        pixels = list(img_small.getdata())
        avg_r = sum(p[0] for p in pixels) // len(pixels)
        avg_g = sum(p[1] for p in pixels) // len(pixels)
        avg_b = sum(p[2] for p in pixels) // len(pixels)
        color_info['average_color'] = '#{:02x}{:02x}{:02x}'.format(avg_r, avg_g, avg_b)

    except Exception as e:
        logger.warning(f"Failed to extract color info: {e}")

    return color_info
