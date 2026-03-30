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
        for page in doc:
            w = page.rect.width
            h = page.rect.height
            _stamp_line(page, 'ARMGUARD RDS', w, h, row=0, fontsize=30)
            _stamp_line(page, username,        w, h, row=1, fontsize=20)
            _stamp_line(page, timestamp,       w, h, row=2, fontsize=14)

        out = doc.tobytes(deflate=True)
        doc.close()
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
) -> None:
    """
    Insert one watermark line centred on *page*, rotated 45 °, at a vertical
    position determined by *row*.

    The three rows are spread around the vertical centre of the page so they
    read as a stacked block:
        row 0 → slightly above centre
        row 1 → centre
        row 2 → slightly below centre

    Note: render_mode=0 (fill-only) requires ``fill`` for colour — ``color``
    is the stroke colour and has no effect in fill-only mode.  Using
    fill_opacity on a None fill would produce invisible text.
    """
    try:
        import math
        import fitz

        text_len = fitz.get_text_length(text, fontname='helv', fontsize=fontsize)

        # Centre the midpoint of the rotated text on the page.
        # With rotate=45° CCW the baseline runs up-right; offset the start
        # so the text midpoint lands at the page centre.
        angle  = math.radians(45)
        cos_a  = math.cos(angle)
        sin_a  = math.sin(angle)

        # Perpendicular offset direction (rotated 90° from text baseline)
        row_spacing = fontsize * 1.8
        perp_offset = (row - 1) * row_spacing

        cx = page_width  / 2 - (text_len / 2) * cos_a + perp_offset * sin_a
        cy = page_height / 2 + (text_len / 2) * sin_a + perp_offset * cos_a

        page.insert_text(
            fitz.Point(cx, cy),
            text,
            fontname='helv',
            fontsize=fontsize,
            # fill= sets the glyph interior colour (render_mode=0 fill-only)
            fill=(0.72, 0.12, 0.12),
            fill_opacity=0.30,
            rotate=45,
        )
    except Exception:
        logger.debug(
            'Watermark line skipped: row=%d text=%r', row, text, exc_info=True
        )
