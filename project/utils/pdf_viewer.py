"""
Centralized, audited PDF serving for ARMGUARD RDS.

All views that serve PDFs should use serve_pdf() or serve_pdf_bytes()
instead of constructing FileResponse/HttpResponse directly.

Guarantees
----------
1. Authentication enforced before any file is opened.
2. Resolved path is constrained inside MEDIA_ROOT (path traversal blocked).
3. Every access is recorded in the ``armguard.pdf`` audit log.
4. Response headers (Content-Disposition, Cache-Control, X-Content-Type-Options)
   are set consistently on every PDF response.
5. Optional per-user watermarking via utils.pdf_watermark.

Supported document types
------------------------
    PDF_TYPE_TR     – Temporary Receipt        → media/TR_PDF/
    PDF_TYPE_PAR    – Property Ack. Receipt    → media/PAR_PDF/
    PDF_TYPE_MO     – Mission Order            → media/MO_PDF/
    PDF_TYPE_REPORT – Daily / Periodic Report  → media/REPORT_PDF/

Usage (inside an @login_required view)
---------------------------------------
    from utils.pdf_viewer import serve_pdf, PDF_TYPE_TR

    return serve_pdf(
        request,
        pdf_type=PDF_TYPE_TR,
        filename="TR_SGT_DelaCruz_42.pdf",
        label="TR #42 – SGT Dela Cruz",
        extra_headers={'X-Print-Page-Size': 'legal'},
    )
"""

import logging
import os
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden

logger = logging.getLogger('armguard.pdf')

# ── Document-type constants ───────────────────────────────────────────────────
PDF_TYPE_TR     = 'TR'    # Temporary Receipt        media/TR_PDF/
PDF_TYPE_PAR    = 'PAR'   # Property Ack. Receipt    media/PAR_PDF/
PDF_TYPE_MO     = 'MO'    # Mission Order            media/MO_PDF/
PDF_TYPE_REPORT = 'RPT'   # Daily / Periodic Report  media/REPORT_PDF/

_SUBDIRS: dict[str, str] = {
    PDF_TYPE_TR:     'TR_PDF',
    PDF_TYPE_PAR:    'PAR_PDF',
    PDF_TYPE_MO:     'MO_PDF',
    PDF_TYPE_REPORT: 'REPORT_PDF',
}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _media_root() -> Path:
    return Path(settings.MEDIA_ROOT).resolve()


def _safe_path(pdf_type: str, filename: str) -> Path:
    """
    Resolve *filename* inside the sub-directory for *pdf_type* and verify the
    result is still inside MEDIA_ROOT.

    Raises Http404 on:
    - unknown pdf_type
    - filename containing path separators (traversal attempt)
    - resolved path escaping the expected sub-directory
    - file not found on disk
    """
    # Reject any path separator in the bare filename
    if not filename or os.sep in filename or (os.altsep and os.altsep in filename):
        logger.warning(
            'PDF serve blocked — invalid filename: pdf_type=%s filename=%r',
            pdf_type, filename,
        )
        raise Http404('Invalid filename.')

    subdir = _SUBDIRS.get(pdf_type)
    if subdir is None:
        raise Http404('Unknown PDF type.')

    base   = (_media_root() / subdir).resolve()
    target = (base / filename).resolve()

    # Ensure target is strictly inside base (covers symlink escapes too)
    try:
        target.relative_to(base)
    except ValueError:
        logger.warning(
            'Path traversal blocked: type=%s filename=%r resolved=%s',
            pdf_type, filename, target,
        )
        raise Http404('Invalid path.')

    if not target.is_file():
        raise Http404('PDF not found.')

    return target


def _build_response(
    content,
    filename: str,
    as_attachment: bool,
    extra_headers: dict | None,
) -> HttpResponse:
    """Construct a consistent PDF HTTP response from bytes or a file-like object."""
    disposition = 'attachment' if as_attachment else 'inline'

    if isinstance(content, bytes):
        response = HttpResponse(content, content_type='application/pdf')
        response['Content-Disposition'] = f'{disposition}; filename="{filename}"'
    else:
        # file-like: let FileResponse set Content-Length automatically
        response = FileResponse(
            content,
            content_type='application/pdf',
            filename=filename,
            as_attachment=as_attachment,
        )
        # FileResponse already sets Content-Disposition; override to ensure inline/attachment
        response['Content-Disposition'] = f'{disposition}; filename="{filename}"'

    response['Cache-Control']         = 'no-store, no-cache, must-revalidate, max-age=0'
    response['X-Content-Type-Options'] = 'nosniff'

    if extra_headers:
        for key, value in extra_headers.items():
            response[key] = value

    return response


def _log_access(request, pdf_type: str, filename: str, label: str) -> None:
    logger.info(
        'PDF access | user=%-30s  type=%-5s  file=%-50s  label=%r  ip=%s',
        request.user.get_full_name() or request.user.username,
        pdf_type,
        filename,
        label,
        request.META.get('REMOTE_ADDR', '-'),
    )


# ── Public API ────────────────────────────────────────────────────────────────

def serve_pdf(
    request,
    *,
    pdf_type: str,
    filename: str,
    label: str = '',
    as_attachment: bool = False,
    apply_watermark: bool = False,
    extra_headers: dict | None = None,
) -> HttpResponse:
    """
    Serve a PDF file from disk with authentication, path-traversal protection,
    audit logging, and optional watermarking.

    Parameters
    ----------
    request         : HttpRequest — must be an authenticated request.
    pdf_type        : PDF_TYPE_TR | PDF_TYPE_PAR | PDF_TYPE_MO | PDF_TYPE_REPORT
    filename        : bare filename (no directory components) inside the type sub-dir.
    label           : human-readable label written to the audit log.
    as_attachment   : force-download (True) or inline viewing (False, default).
    apply_watermark : stamp per-user watermark when True.
    extra_headers   : additional response headers, e.g. {'X-Print-Page-Size': 'legal'}.
    """
    if not request.user.is_authenticated:
        return HttpResponseForbidden('Authentication required.')

    target = _safe_path(pdf_type, filename)
    _log_access(request, pdf_type, filename, label)

    if apply_watermark:
        try:
            from utils.pdf_watermark import watermark_pdf_bytes
            raw       = target.read_bytes()
            watermarked = watermark_pdf_bytes(
                raw,
                request.user.get_full_name() or request.user.username,
            )
            return _build_response(watermarked, filename, as_attachment, extra_headers)
        except Exception:
            logger.exception('Watermark failed for %s — serving without watermark', filename)
            # Fall through to plain file serve

    return _build_response(open(target, 'rb'), filename, as_attachment, extra_headers)


def serve_pdf_bytes(
    request,
    *,
    pdf_bytes: bytes,
    filename: str,
    label: str = '',
    as_attachment: bool = False,
    apply_watermark: bool = False,
    extra_headers: dict | None = None,
) -> HttpResponse:
    """
    Serve an in-memory PDF (already generated as bytes) with audit logging and
    optional watermarking.

    Used for dynamically generated PDFs (TR fills, TR previews) where the bytes
    are produced on-the-fly and never written to a permanent path that could be
    served by serve_pdf().

    Parameters
    ----------
    request         : HttpRequest — must be an authenticated request.
    pdf_bytes       : raw bytes of the PDF to serve.
    filename        : suggested filename sent in Content-Disposition.
    label           : human-readable label written to the audit log.
    as_attachment   : force-download (True) or inline viewing (False, default).
    apply_watermark : stamp per-user watermark when True.
    extra_headers   : additional response headers.
    """
    if not request.user.is_authenticated:
        return HttpResponseForbidden('Authentication required.')

    _log_access(request, 'BYTES', filename, label)

    if apply_watermark:
        try:
            from utils.pdf_watermark import watermark_pdf_bytes
            pdf_bytes = watermark_pdf_bytes(
                pdf_bytes,
                request.user.get_full_name() or request.user.username,
            )
        except Exception:
            logger.exception('Watermark failed for in-memory PDF %s', filename)

    return _build_response(pdf_bytes, filename, as_attachment, extra_headers)
