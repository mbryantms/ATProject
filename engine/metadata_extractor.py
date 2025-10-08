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
from typing import Dict, Optional, Any

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
        from PIL.ExifTags import TAGS, GPSTAGS
        import os

        # Try to open the file - handle both file path and file object
        if not asset.file:
            logger.warning(f"Asset {asset.key} has no file attached")
            return metadata

        # Try opening via file path first, then fallback to file object
        try:
            if hasattr(asset.file, 'path') and os.path.exists(asset.file.path):
                logger.info(f"Opening image from path: {asset.file.path}")
                img = Image.open(asset.file.path)
            else:
                logger.info(f"Opening image from file object")
                # Open from file object if path doesn't exist
                asset.file.seek(0)
                img = Image.open(asset.file)

            logger.info(f"Image opened: format={img.format}, mode={img.mode}, size={img.size}")
        except (FileNotFoundError, OSError) as e:
            logger.error(f"Cannot open image file for {asset.key}: {e}")
            return metadata

        # Basic image properties
        metadata['has_alpha'] = img.mode in ('RGBA', 'LA', 'PA')
        metadata['color_space'] = img.mode
        logger.info(f"Basic properties: has_alpha={metadata.get('has_alpha')}, color_space={metadata.get('color_space')}")

        # DPI information
        if 'dpi' in img.info:
            metadata['dpi'] = int(img.info['dpi'][0])

        # ICC Color profile
        if 'icc_profile' in img.info:
            metadata['color_profile'] = 'Embedded ICC Profile'

        # Extract EXIF data
        exif = img.getexif()
        logger.info(f"EXIF data check: exif={'present' if exif else 'missing'}, count={len(exif) if exif else 0}")

        if exif:
            exif_data = {}

            # Also get extended EXIF data (ExifOffset IFD) - contains detailed camera settings
            exif_ifd = None
            try:
                exif_ifd = exif.get_ifd(0x8769)  # ExifOffset IFD
                if exif_ifd:
                    logger.info(f"Found ExifOffset IFD with {len(exif_ifd)} tags")
                else:
                    logger.warning(f"No ExifOffset IFD found for {asset.key}")
            except Exception as e:
                logger.warning(f"Could not read ExifOffset IFD for {asset.key}: {e}")

            # Combine both main EXIF and extended EXIF
            all_exif_items = list(exif.items())
            if exif_ifd:
                all_exif_items.extend(list(exif_ifd.items()))

            logger.info(f"Processing {len(all_exif_items)} total EXIF tags")

            for tag_id, value in all_exif_items:
                tag = TAGS.get(tag_id, tag_id)

                # Store original value for JSON serialization
                json_value = value

                # Convert various types to JSON-serializable formats
                if isinstance(value, bytes):
                    try:
                        # Decode and remove null bytes that PostgreSQL JSON can't handle
                        decoded = value.decode('utf-8', errors='ignore')
                        json_value = decoded.replace('\u0000', '').replace('\x00', '')
                        # If after removing nulls the string is empty or whitespace, use hex representation
                        if not json_value.strip():
                            json_value = value.hex()
                    except:
                        json_value = value.hex()
                elif hasattr(value, '__iter__') and not isinstance(value, (str, dict)):
                    # Handle IFDRational and tuple types
                    try:
                        # Convert tuples/IFDRational to list of numbers
                        json_value = [float(v) if hasattr(v, '__float__') else v for v in value]
                    except:
                        json_value = str(value)
                elif hasattr(value, 'numerator') and hasattr(value, 'denominator'):
                    # Handle single IFDRational
                    json_value = float(value.numerator) / float(value.denominator) if value.denominator != 0 else 0
                elif isinstance(value, str):
                    # Remove null bytes from strings
                    json_value = value.replace('\u0000', '').replace('\x00', '')
                else:
                    json_value = value

                exif_data[tag] = json_value

                # Extract specific fields (use original value for processing)
                if tag == 'Make':
                    metadata['camera_make'] = str(value).strip()
                elif tag == 'Model':
                    metadata['camera_model'] = str(value).strip()
                elif tag == 'LensModel':
                    metadata['lens'] = str(value).strip()
                elif tag == 'FocalLength':
                    # Handle IFDRational or tuple format
                    if hasattr(value, 'numerator') and hasattr(value, 'denominator'):
                        metadata['focal_length'] = float(value) if value.denominator != 0 else 0
                    elif isinstance(value, (tuple, list)) and len(value) == 2:
                        metadata['focal_length'] = float(value[0]) / float(value[1]) if value[1] != 0 else 0
                    else:
                        try:
                            metadata['focal_length'] = float(value)
                        except:
                            pass
                elif tag == 'FNumber' or tag == 'ApertureValue':
                    # Handle IFDRational or tuple format
                    if hasattr(value, 'numerator') and hasattr(value, 'denominator'):
                        metadata['aperture'] = float(value) if value.denominator != 0 else 0
                    elif isinstance(value, (tuple, list)) and len(value) == 2:
                        metadata['aperture'] = float(value[0]) / float(value[1]) if value[1] != 0 else 0
                    else:
                        try:
                            metadata['aperture'] = float(value)
                        except:
                            pass
                elif tag == 'ExposureTime':
                    # Format as string like "1/500"
                    if hasattr(value, 'numerator') and hasattr(value, 'denominator'):
                        if value.numerator == 1:
                            metadata['shutter_speed'] = f"1/{int(value.denominator)}"
                        else:
                            metadata['shutter_speed'] = f"{value.numerator}/{value.denominator}"
                    elif isinstance(value, (tuple, list)) and len(value) == 2:
                        if value[0] == 1:
                            metadata['shutter_speed'] = f"1/{int(value[1])}"
                        else:
                            metadata['shutter_speed'] = f"{value[0]}/{value[1]}"
                    elif isinstance(value, float):
                        # Handle decimal format (e.g., 0.01666 = 1/60)
                        if value < 1:
                            # Convert to fraction format
                            denominator = round(1 / value)
                            metadata['shutter_speed'] = f"1/{denominator}"
                        else:
                            metadata['shutter_speed'] = f"{value}s"
                    else:
                        metadata['shutter_speed'] = str(value)
                elif tag == 'ISOSpeedRatings' or tag == 'ISO' or tag == 'PhotographicSensitivity':
                    try:
                        # Handle tuple/list format
                        if isinstance(value, (tuple, list)):
                            metadata['iso'] = int(value[0])
                        else:
                            metadata['iso'] = int(value)
                    except:
                        pass
                elif tag == 'DateTimeOriginal' or tag == 'DateTime':
                    # Parse datetime and make timezone-aware
                    try:
                        from django.utils import timezone
                        naive_dt = datetime.strptime(
                            str(value), '%Y:%m:%d %H:%M:%S'
                        )
                        # Make timezone-aware using Django's configured timezone
                        metadata['captured_at'] = timezone.make_aware(
                            naive_dt,
                            timezone.get_current_timezone()
                        )
                    except:
                        pass

            # Extract GPS data
            gps_info = exif.get_ifd(0x8825)  # GPS IFD
            if gps_info:
                gps_data = {}
                for tag_id, value in gps_info.items():
                    tag = GPSTAGS.get(tag_id, tag_id)
                    gps_data[tag] = value

                # Convert GPS coordinates
                lat = _convert_gps_coordinate(
                    gps_data.get('GPSLatitude'),
                    gps_data.get('GPSLatitudeRef')
                )
                lon = _convert_gps_coordinate(
                    gps_data.get('GPSLongitude'),
                    gps_data.get('GPSLongitudeRef')
                )

                if lat is not None:
                    metadata['latitude'] = lat
                if lon is not None:
                    metadata['longitude'] = lon

            # Store raw EXIF data (limit size for JSON field)
            metadata['exif_data'] = exif_data

        # Extract color information
        try:
            color_info = _extract_color_info(img)
            metadata.update(color_info)
        except Exception as e:
            logger.warning(f"Failed to extract color info for {asset.key}: {e}")

        # Log what was extracted
        logger.info(f"Image metadata extracted for {asset.key}:")
        logger.info(f"  - Camera: {metadata.get('camera_make')} {metadata.get('camera_model')}")
        logger.info(f"  - Lens: {metadata.get('lens')}")
        logger.info(f"  - Focal length: {metadata.get('focal_length')}")
        logger.info(f"  - Aperture: {metadata.get('aperture')}")
        logger.info(f"  - Shutter speed: {metadata.get('shutter_speed')}")
        logger.info(f"  - ISO: {metadata.get('iso')}")
        logger.info(f"  - GPS: {metadata.get('latitude')}, {metadata.get('longitude')}")
        logger.info(f"  - Captured at: {metadata.get('captured_at')}")
        logger.info(f"  - Color: {metadata.get('average_color')}")
        logger.info(f"  - Total fields: {len(metadata)}")

    except Exception as e:
        logger.error(f"Error extracting image metadata for {asset.key}: {e}")
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
        import os

        if not asset.file:
            logger.warning(f"Asset {asset.key} has no file attached")
            return metadata

        # Try to get the file path
        try:
            if hasattr(asset.file, 'path') and os.path.exists(asset.file.path):
                file_path = asset.file.path
            else:
                logger.warning(f"Audio file path not accessible for {asset.key}")
                return metadata
        except Exception as e:
            logger.error(f"Cannot access audio file for {asset.key}: {e}")
            return metadata

        audio = MutagenFile(file_path)

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
            import os

            if not asset.file:
                logger.warning(f"Asset {asset.key} has no file attached")
                return metadata

            # Try to get the file path or file object
            try:
                if hasattr(asset.file, 'path') and os.path.exists(asset.file.path):
                    reader = PdfReader(asset.file.path)
                else:
                    # Try using file object
                    asset.file.seek(0)
                    reader = PdfReader(asset.file)
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
        import subprocess
        import json
        import os

        if not asset.file:
            logger.warning(f"Asset {asset.key} has no file attached")
            return metadata

        # Get file path
        if not (hasattr(asset.file, 'path') and os.path.exists(asset.file.path)):
            logger.warning(f"Video file path not accessible for {asset.key}")
            return metadata

        # Use ffprobe to get format metadata
        result = subprocess.run([
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            asset.file.path
        ], capture_output=True, text=True, timeout=30)

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
    import os

    logger.info(f"Starting metadata extraction for asset: {asset.key} (type: {asset.asset_type})")

    # Validate file exists
    if not asset.file:
        logger.warning(f"Asset {asset.key} has no file attached - cannot extract metadata")
        return None

    # Check file accessibility
    try:
        if hasattr(asset.file, 'path'):
            file_path = asset.file.path
            file_exists = os.path.exists(file_path)
            logger.info(f"Asset file path: {file_path}, exists: {file_exists}")
            if not file_exists:
                logger.error(f"File does not exist at path: {file_path}")
                return None
        else:
            logger.warning(f"Asset file has no path attribute - will attempt to use file object")
    except Exception as e:
        logger.error(f"Error checking file path for {asset.key}: {e}")
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