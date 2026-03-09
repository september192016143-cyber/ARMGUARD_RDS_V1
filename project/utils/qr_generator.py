# qr_generator.py
# Unified QR Code Generator for ArmGuard System
# Standard settings matching JavaScript QRCode library

import qrcode
from pathlib import Path
from PIL import Image
from io import BytesIO

def generate_qr_code(data, output_path=None, size=600):
    """
    Generate a HIGH-RESOLUTION QR code image for crisp printing.
    Optimized for print quality:
    - 600x600px default (HD resolution for 1cm print size)
    - High error correction for reliability
    - Larger box size for crisp rendering
    - Minimal border
    
    Args:
        data (str): The data to encode in the QR code.
        output_path (str or Path, optional): The file path to save the QR code image.
        size (int): The output size in pixels (default: 600 for HD print).
    
    Returns:
        Path or Image: If output_path provided, returns Path. Otherwise returns PIL Image.
    """
    # Create QR code with HD print settings
    qr = qrcode.QRCode(
        version=1,  # Auto-adjust version
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # High error correction
        box_size=20,  # Larger box size for crisp rendering
        border=2,  # Small but sufficient border
    )
    
    qr.add_data(data)
    qr.make(fit=True)
    
    # Create image with gray QR on black background
    img = qr.make_image(fill_color="#888888", back_color="black")
    
    # Resize to specified size with high-quality resampling
    img = img.resize((size, size), Image.Resampling.LANCZOS)
    
    # Convert to RGB mode for better compatibility
    img = img.convert('RGB')
    
    # Save or return with optimal settings for print
    if output_path:
        # Save with high quality settings for print
        img.save(output_path, format='PNG', optimize=True, dpi=(300, 300))
        return Path(output_path)
    else:
        return img

def generate_qr_code_to_buffer(data, size=600):
    """
    Generate HD QR code and return as BytesIO buffer (for Django ImageField).
    
    Args:
        data (str): The data to encode in the QR code.
        size (int): The output size in pixels (default: 600 for HD print).
    
    Returns:
        BytesIO: Buffer containing high-quality PNG image data.
    """
    img = generate_qr_code(data, output_path=None, size=size)
    
    buffer = BytesIO()
    # Save with optimal settings for web and print
    img.save(buffer, format='PNG', optimize=True, dpi=(300, 300))
    buffer.seek(0)
    
    return buffer
