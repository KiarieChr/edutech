"""
Branding utilities for Fahari Academia Document Design Studio (Phase 1).
Provides secure image verification, size and dimension checking,
and safe cleanup of obsolete media assets.
"""
import os
import re
from PIL import Image
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.utils.translation import gettext_lazy as _

ALLOWED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp'}
ALLOWED_IMAGE_FORMATS = {'PNG', 'JPEG', 'WEBP'}
MAX_LOGO_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_DIMENSION = 4096  # Max width or height in px to prevent decompression bombs
MIN_DIMENSION = 16    # Minimum sensible logo dimension

HEX_COLOR_REGEX = re.compile(r'^#[0-9A-Fa-f]{6}$')


def validate_hex_color(value, field_name="Color"):
    """
    Validate that a given string is a valid 6-character hexadecimal color code.
    e.g. #17365D
    """
    if not value:
        return value
    val = value.strip()
    if not HEX_COLOR_REGEX.match(val):
        raise ValidationError(
            _(f"{field_name} must be a valid 6-character hexadecimal code starting with '#' (e.g. #17365D).")
        )
    return val.upper()


def validate_branding_image(uploaded_file):
    """
    Validate uploaded logo image:
    1. Check presence
    2. Check file size (<= 5MB)
    3. Check file extension
    4. Check actual file payload using PIL Image.open
    5. Verify format matches allowed formats
    6. Verify image dimensions are within safe bounds
    7. Verify image integrity with img.verify()
    """
    if not uploaded_file:
        raise ValidationError(_("No image file was provided."))

    # Size check
    if uploaded_file.size > MAX_LOGO_SIZE_BYTES:
        size_mb = uploaded_file.size / (1024 * 1024)
        raise ValidationError(
            _(f"Image file size ({size_mb:.2f} MB) exceeds the maximum allowed limit of 5.00 MB.")
        )

    # Extension check
    name = getattr(uploaded_file, 'name', '') or ''
    _, ext = os.path.splitext(name.lower())
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError(
            _(f"Unsupported file extension '{ext}'. Only PNG, JPEG, and WebP images are permitted.")
        )

    # Content check using PIL
    try:
        uploaded_file.seek(0)
        with Image.open(uploaded_file) as img:
            format_detected = (img.format or '').upper()
            if format_detected not in ALLOWED_IMAGE_FORMATS:
                raise ValidationError(
                    _(f"File payload is detected as '{format_detected}'. Only authentic PNG, JPEG, and WebP images are permitted.")
                )

            width, height = img.size
            if width > MAX_DIMENSION or height > MAX_DIMENSION:
                raise ValidationError(
                    _(f"Image dimensions ({width}x{height}px) exceed the maximum supported bounds of {MAX_DIMENSION}x{MAX_DIMENSION}px.")
                )
            if width < MIN_DIMENSION or height < MIN_DIMENSION:
                raise ValidationError(
                    _(f"Image dimensions ({width}x{height}px) are too small to be a usable institutional emblem.")
                )

            # verify checks headers and file structure
            img.verify()
    except Exception as e:
        if isinstance(e, ValidationError):
            raise
        raise ValidationError(_("The uploaded file could not be parsed as a valid image or is corrupted."))
    finally:
        uploaded_file.seek(0)


def delete_old_logo_file(field_file):
    """
    Safely delete a previously stored logo file from storage.
    Fails silently if the file does not exist or storage cannot access it.
    """
    if not field_file:
        return
    file_name = getattr(field_file, 'name', None)
    if not file_name:
        return
    try:
        if default_storage.exists(file_name):
            default_storage.delete(file_name)
    except Exception:
        pass
