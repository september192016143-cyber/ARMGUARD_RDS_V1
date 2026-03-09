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
    CSP = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline' "     # unsafe-inline for Django admin only
            "https://fonts.googleapis.com "     # Google Fonts CSS
            "https://cdnjs.cloudflare.com; "    # Font Awesome CSS
        "font-src 'self' "
            "https://fonts.gstatic.com "        # Google Fonts files
            "https://cdnjs.cloudflare.com; "    # Font Awesome font files
        "img-src 'self' data:; "                # QR codes include data: URIs
        "connect-src 'self'; "
        "frame-ancestors 'none';"               # Belt+suspenders with X-Frame-Options DENY
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
        response['Content-Security-Policy'] = self.CSP
        response['Referrer-Policy'] = 'same-origin'
        response['Permissions-Policy'] = self.PERMISSIONS_POLICY
        return response
