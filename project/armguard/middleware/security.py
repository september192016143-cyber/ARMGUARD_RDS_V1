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
    # PDF rendering strategy — ALL PDFs use <embed type="application/pdf">:
    #   • <embed> is governed by object-src, NOT frame-src.
    #   • Chrome's built-in PDF viewer creates internal sub-frames with src=''
    #     when rendering PDFs inside <iframe>. Those sub-frames are checked
    #     against frame-src, and '' matches nothing — causing
    #     "Framing '' violates frame-src" CSP errors.
    #   • Inside <embed>, Chrome's PDF sub-frames are checked against object-src
    #     instead, which is correctly set to 'self' blob:.
    #   • All PDF rendering paths (transaction_detail.js, transaction_form.js,
    #     pdf_print.js) use fetch→blob→<embed>. No <iframe> is used for PDFs.
    CSP = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline' "     # unsafe-inline for Django admin only
            "https://fonts.googleapis.com "     # Google Fonts CSS
            "https://cdnjs.cloudflare.com; "    # Font Awesome CSS
        "font-src 'self' "
            "https://fonts.gstatic.com "        # Google Fonts files
            "https://cdnjs.cloudflare.com; "    # Font Awesome font files
        "img-src 'self' data: blob:; "          # QR codes: data: URIs; card preview: blob: URLs
        "frame-src 'self'; "                    # No PDF iframes — all PDFs rendered via <embed>
        "object-src 'self' blob:; "             # <embed type="application/pdf"> — transaction_detail, transaction_form, pdf_print
        "connect-src 'self'; "
        "frame-ancestors 'self';"               # Allow self-framing; block external framing
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
        response['Referrer-Policy'] = 'same-origin'
        response['Permissions-Policy'] = self.PERMISSIONS_POLICY
        return response
