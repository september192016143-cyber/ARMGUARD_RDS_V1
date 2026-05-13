"""
Content Security Policy and Referrer Policy middleware.

Adds security response headers to every HTTP response:
  - Content-Security-Policy  — restricts resource origins to mitigate XSS
  - Referrer-Policy          — limits referrer information sent to third parties

Register in settings MIDDLEWARE after all authentication middleware so the
headers are added to every authenticated and unauthenticated response alike.
"""


class SecurityHeadersMiddleware:
    """Append security response headers on every outgoing response.

    Headers set:
      - Content-Security-Policy   — XSS / injection mitigation
      - Referrer-Policy           — limits referrer leakage
      - Permissions-Policy        — disables unused browser features
    """

    # C2 FIX: Tight policy — inline scripts eliminated (moved to static/js/base.js).
    # External CDNs (Google Fonts, Font Awesome) explicitly allowlisted.
    # style-src retains 'unsafe-inline' only for Django admin inline styles
    # (eliminating it there would require django-csp nonce support — next sprint).
    #
    # script-src allowances:
    #   'self'          — our own static/js/* files
    #   (no unsafe-inline — all JS is external files)
    #
    # PDF rendering strategy — ALL PDFs use PDF.js rendered onto <canvas>:
    #   • PDF.js (self-hosted at static/js/pdfjs/) fetches PDF bytes via
    #     fetch(url, {credentials:'same-origin'}) and renders each page onto
    #     an HTML <canvas> element. No <iframe>, no <embed>, no <object>.
    #   • This eliminates ALL frame-src and object-src CSP involvement.
    #   • PDF.js spawns a Web Worker (pdf.worker.min.mjs, same-origin)
    #     → worker-src 'self'. Internally it may wrap it as a blob: worker
    #     → worker-src blob:.
    #   • object-src is now 'none' — the tightest possible setting.
    #   • All PDF rendering paths (transaction_detail.js, transaction_form.js,
    #     pdf_print.js) use fetch→ArrayBuffer→pdfjsLib.getDocument→<canvas>.
    CSP = (
        "default-src 'self'; "
        "script-src 'self'; "  # blob: moved to worker-src only — PDF.js worker loaded as blob URL
        "style-src 'self' 'unsafe-inline' "     # unsafe-inline for Django admin only
            "https://fonts.googleapis.com "     # Google Fonts CSS
            "https://cdnjs.cloudflare.com; "    # Font Awesome CSS
        "font-src 'self' "
            "https://fonts.gstatic.com "        # Google Fonts files
            "https://cdnjs.cloudflare.com; "    # Font Awesome font files
        "img-src 'self' data: blob:; "          # QR codes: data: URIs; card preview: blob: URLs
        "frame-src 'none'; "                    # No iframes — all PDFs rendered via PDF.js <canvas>
        "object-src 'none'; "                   # No <embed> or <object> — PDF.js uses <canvas> only
        "worker-src 'self' blob:; "             # PDF.js Web Worker (static/js/pdfjs/pdf.worker.min.mjs)
        "connect-src 'self'; "
        "frame-ancestors 'none';"               # P2-Medium: block all framing (clickjacking prevention)
    )

    # Disable browser features not required by the application.
    # geolocation, camera, microphone — not used by an armory RDS.
    PERMISSIONS_POLICY = (
        "geolocation=(), "
        "camera=(), "
        "microphone=(), "
        "payment=(), "
        "usb=(), "
        "accelerometer=(), "
        "gyroscope=()"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # CSP is only meaningful for HTML documents. Applying it to binary
        # responses (application/pdf, images, etc.) is unnecessary — the browser
        # does not interpret CSP directives on non-HTML MIME types.
        content_type = response.get('Content-Type', '')
        if 'text/html' in content_type:
            response['Content-Security-Policy'] = self.CSP
            # Prevent browsers from caching authenticated HTML pages.
            # Without this, browsers use heuristic freshness (RFC 7234 §4.2.2)
            # and may serve stale HTML — causing PJAX to display old page content
            # even after the server has been updated (e.g. template changes, JS
            # file moves).  Only added if the view hasn't already set its own
            # Cache-Control directive (e.g. a print view that wants a longer TTL).
            # Static assets (JS/CSS/images) are served by Nginx with content-hashed
            # filenames + immutable cache headers, so they are unaffected.
            if not response.has_header('Cache-Control'):
                response['Cache-Control'] = 'no-store'
        response['Referrer-Policy'] = 'same-origin'
        response['Permissions-Policy'] = self.PERMISSIONS_POLICY
        return response
