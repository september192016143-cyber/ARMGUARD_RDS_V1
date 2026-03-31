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

from django.utils import timezone

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
        timestamp = timezone.localtime().strftime('%Y-%m-%d %H:%M PHT')

        doc = fitz.open(stream=pdf_bytes, filetype='pdf')
        logger.info('Watermarking PDF — pages=%d user=%s', doc.page_count, username)
        for page in doc:
            w = page.rect.width
            h = page.rect.height
            half = h / 2
            # Stamp watermark in both halves — TR legal page is cut into two
            # identical copies (upper + lower), each copy needs its own stamp.
            # All three rows per half share one TextWriter so colour/opacity
            # are guaranteed identical across every line.
            for y_off in (0.0, half):
                _stamp_block(
                    page,
                    lines=[
                        ('ARMGUARD RDS', 30),
                        (username,       20),
                        (timestamp,      14),
                    ],
                    page_width=w,
                    band_height=half,
                    y_offset=y_off,
                )

        out = doc.tobytes(deflate=True)
        doc.close()
        logger.info('Watermark applied successfully')
        return out

    except Exception:
        logger.exception(
            'Watermark stamping failed for user=%s — returning original bytes', username
        )
        return pdf_bytes


def _stamp_block(
    page,
    lines: list,
    page_width: float,
    band_height: float,
    y_offset: float = 0.0,
) -> None:
    """
    Stamp a diagonal watermark block (all rows) into a horizontal band.

    *lines* is a list of (text, fontsize) tuples, one per row (top → bottom).
    All rows share a single TextWriter so colour and opacity are identical.

    Uses TextWriter + morph=(pivot, Matrix(-45)) because insert_text() only
    accepts rotate=0/90/180/270 and raises ValueError for arbitrary angles.
    """
    import math
    import fitz

    angle  = math.radians(45)
    cos_a  = math.cos(angle)   # ≈ 0.707
    sin_a  = math.sin(angle)   # ≈ 0.707

    # Band vertical centre, nudged up 15 % so the block sits visually centred.
    band_cx = page_width  / 2
    band_cy = y_offset + band_height / 2 - band_height * 0.15

    # Row spacing uses the largest fontsize for a consistent gap.
    max_fs      = max(fs for _, fs in lines)
    row_spacing = max_fs * 1.8
    n_rows      = len(lines)

    try:
        # All rows go into one TextWriter — same opacity and colour guaranteed.
        tw   = fitz.TextWriter(page.rect, opacity=0.35, color=(0.72, 0.12, 0.12))
        font = fitz.Font('helv')

        # Use the widest line's start-point as the shared rotation pivot so
        # the whole block rotates as one unit around the block centre.
        pivot_pt = None

        for row_idx, (text, fontsize) in enumerate(lines):
            text_len    = fitz.get_text_length(text, fontname='helv', fontsize=fontsize)
            # Centre row vertically around band_cy; rows are evenly spaced.
            perp_offset = (row_idx - (n_rows - 1) / 2) * row_spacing

            cx = band_cx - (text_len / 2) * cos_a + perp_offset * sin_a
            cy = band_cy + (text_len / 2) * sin_a + perp_offset * cos_a

            pt = fitz.Point(cx, cy)
            tw.append(pt, text, font=font, fontsize=fontsize)

            if pivot_pt is None:
                pivot_pt = pt   # use first (largest) line as rotation pivot

        tw.write_text(page, morph=(pivot_pt, fitz.Matrix(-45)))

    except Exception:
        logger.debug('Watermark block skipped at y_offset=%r', y_offset, exc_info=True)
