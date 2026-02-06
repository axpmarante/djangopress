"""Utility functions for the core app"""

import os
from io import BytesIO
from PIL import Image
from django.core.files.base import ContentFile


def resize_and_compress_image(image_field, max_width=1920, quality=80, max_size_kb=500):
    """
    Resize and compress an image to reduce file size while maintaining quality.

    Args:
        image_field: Django ImageField
        max_width: Maximum width in pixels (default: 1920px)
        quality: JPEG quality (1-100, default: 80)
        max_size_kb: Maximum target file size in KB (default: 500KB)

    Returns:
        ContentFile: Processed image as ContentFile
    """
    print(f"\n{'='*60}")
    print(f"IMAGE PROCESSING STARTED")
    print(f"{'='*60}")
    print(f"Original filename: {image_field.name}")

    # Open the image
    img = Image.open(image_field)
    original_size = image_field.size if hasattr(image_field, 'size') else 0
    print(f"Original file size: {original_size / 1024:.2f} KB")
    print(f"Original dimensions: {img.size[0]}x{img.size[1]}px")

    # Convert RGBA to RGB if necessary (for PNG with transparency)
    print(f"Image mode: {img.mode}")
    if img.mode in ('RGBA', 'LA', 'P'):
        print(f"Converting {img.mode} to RGB with white background...")
        # Create a white background
        background = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P':
            img = img.convert('RGBA')
        background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
        img = background
    elif img.mode != 'RGB':
        print(f"Converting {img.mode} to RGB...")
        img = img.convert('RGB')

    # Get original dimensions
    original_width, original_height = img.size

    # Resize if width exceeds max_width
    if original_width > max_width:
        print(f"Image width ({original_width}px) exceeds max width ({max_width}px)")
        # Calculate new height to maintain aspect ratio
        ratio = max_width / original_width
        new_height = int(original_height * ratio)
        print(f"Resizing to: {max_width}x{new_height}px (ratio: {ratio:.2f})")
        img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
    else:
        print(f"No resize needed - image width ({original_width}px) is within limit")

    # Prepare output buffer
    output = BytesIO()

    # Get the file extension
    filename = image_field.name
    ext = os.path.splitext(filename)[1].lower()

    # Determine format (default to JPEG for better compression)
    if ext in ['.jpg', '.jpeg']:
        format_type = 'JPEG'
    elif ext == '.png':
        format_type = 'PNG'
    elif ext == '.webp':
        format_type = 'WEBP'
    else:
        format_type = 'JPEG'
        # Change extension to .jpg for other formats
        filename = os.path.splitext(filename)[0] + '.jpg'

    # Save with initial quality
    current_quality = quality
    print(f"\nCompressing image...")
    print(f"Format: {format_type}")
    print(f"Initial quality: {current_quality}%")
    img.save(output, format=format_type, quality=current_quality, optimize=True)

    # If file is still too large, reduce quality further
    max_size_bytes = max_size_kb * 1024
    attempts = 0
    max_attempts = 5
    initial_compressed_size = output.tell()
    print(f"Compressed size at {current_quality}% quality: {initial_compressed_size / 1024:.2f} KB")

    while output.tell() > max_size_bytes and current_quality > 50 and attempts < max_attempts:
        output = BytesIO()
        current_quality -= 10
        img.save(output, format=format_type, quality=current_quality, optimize=True)
        attempts += 1
        print(f"Attempt {attempts}: Reducing quality to {current_quality}% = {output.tell() / 1024:.2f} KB")

    # Reset buffer position
    output.seek(0)

    final_size = output.tell()
    print(f"\nPROCESSING COMPLETE")
    print(f"Final file size: {final_size / 1024:.2f} KB")
    print(f"Size reduction: {((original_size - final_size) / original_size * 100):.1f}%")
    print(f"Final quality: {current_quality}%")
    print(f"{'='*60}\n")

    # Return as ContentFile
    return ContentFile(output.read(), name=os.path.basename(filename))
