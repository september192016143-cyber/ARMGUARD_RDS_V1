"""
PDF watermarking for ARMGUARD RDS.

Uses PyMuPDF (fitz) to stamp a diagonal, semi-transparent watermark
containing "ARMGUARD RDS", the accessing user's display name, and a UTC
access timestamp onto every page of a PDF document.

Gracefully degrades — returns the original bytes unchanged when:
  - PyMuPDF is not installed
  - Stamping raises any unexpected exception

Install PyMuPDF with:  pip install pymupdf
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger('armguard.pdf')


def watermark_pdf_bytes(pdf_bytes: bytes, username: str) -> bytes:
    """
    Return *pdf_bytes* with a per-user diagonal watermark applied to every page.

    Parameters
    ----------
    pdf_bytes : raw bytes of the original PDF.
    username  : display name to embed in the watermark (e.g. "SGT Juan Dela Cruz").

    Returns
    -------
    bytes : watermarked PDF bytes, or the original bytes if stamping is unavailable.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning('PyMuPDF not installed — watermark skipped for user=%s', username)
        return pdf_bytes

    try:
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

        doc = fitz.open(stream=pdf_bytes, filetype='pdf')
        logger.info('Watermarking PDF — pages=%d user=%s', doc.page_count, username)
        for page in doc:
            w = page.rect.width
            h = page.rect.height
            half = h / 2
            # Stamp watermark in both halves — TR legal page is cut into two
            # identical copies (upper + lower), each copy needs its own stamp.
            for y_off in (0.0, half):
                _stamp_line(page, 'ARMGUARD RDS', w, half, row=0, fontsize=30, y_offset=y_off)
                _stamp_line(page, username,        w, half, row=1, fontsize=20, y_offset=y_off)
                _stamp_line(page, timestamp,       w, half, row=2, fontsize=14, y_offset=y_off)

        out = doc.tobytes(deflate=True)
        doc.close()
        logger.info('Watermark applied successfully')
        return out

    except Exception:
        logger.exception(
            'Watermark stamping failed for user=%s — returning original bytes', username
        )
        return pdf_bytes


def _stamp_line(
    page,
    text: str,
    page_width: float,
    page_height: float,
    row: int,
    fontsize: int,
    y_offset: float = 0.0,
) -> None:
    """
    Insert one watermark line rotated 45°, centred within a horizontal band
    of *page_height* tall, starting at *y_offset* from the page top.

    The three rows form a stacked block around the band centre:
        row 0 → slightly above centre
        row 1 → centre
        row 2 → slightly below centre

    Uses fitz.TextWriter + morph=(pivot, Matrix(-45)) because insert_text()
    only accepts rotate=0/90/180/270 and raises ValueError for 45°.
    """
    import math
    import fitz

    text_len = fitz.get_text_length(text, fontname='helv', fontsize=fontsize)

    # Centre the midpoint of the rotated text within the band.
    # Text goes UP-RIGHT at 45° (screen coords, Y-down).  Matrix(-45) rotates
    # the horizontal baseline CCW by 45° visually.
    angle       = math.radians(45)
    cos_a       = math.cos(angle)   # ≈ 0.707
    sin_a       = math.sin(angle)   # ≈ 0.707

    row_spacing = fontsize * 1.8
    perp_offset = (row - 1) * row_spacing

    # Band centre is at (page_width/2, y_offset + page_height/2).
    # Nudge upward ~8 % of the band height so the block looks visually centred.
    band_cx = page_width  / 2
    band_cy = y_offset + page_height / 2 - page_height * 0.08

    cx = band_cx - (text_len / 2) * cos_a + perp_offset * sin_a
    cy = band_cy + (text_len / 2) * sin_a + perp_offset * cos_a

    pt = fitz.Point(cx, cy)

    try:
        # TextWriter is the correct way to draw text at arbitrary angles in PyMuPDF.
        # morph=(pivot, matrix) rotates text around `pivot`; Matrix(-45) visually
        # tilts the text up-right at 45° in screen co-ordinates (Y points down).
        tw = fitz.TextWriter(page.rect, opacity=0.35, color=(0.72, 0.12, 0.12))
        font = fitz.Font('helv')
        tw.append(pt, text, font=font, fontsize=fontsize)
        tw.write_text(page, morph=(pt, fitz.Matrix(-45)))
    except Exception:
        logger.debug(
            'Watermark line skipped: row=%d text=%r', row, text, exc_info=True
        )
