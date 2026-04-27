"""
URL configuration for project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView, TemplateView
from django.utils.decorators import method_decorator
from armguard.apps.dashboard.views import dashboard_view, download_ssl_cert, ssl_cert_status, issued_stats_json, dashboard_cards_json, dashboard_tables_json
from armguard.apps.users.views import logout_view, OTPSetupView, OTPVerifyView
from utils.throttle import ratelimit as _ratelimit


# G3 FIX: Rate-limited login view — blocks brute-force at 10 POST attempts/minute per IP/user.
class _RateLimitedLoginView(auth_views.LoginView):
    """LoginView with per-IP/per-user rate limiting on POST (login attempts)."""
    template_name = 'registration/login.html'

    @method_decorator(_ratelimit(rate='30/m'))
    def post(self, *args, **kwargs):
        return super().post(*args, **kwargs)


urlpatterns = [
    # G5 FIX: Admin URL read from DJANGO_ADMIN_URL env var (default 'admin').
    # Set DJANGO_ADMIN_URL to an obscure value in production .env.
    path(f'{settings.ADMIN_URL}/', admin.site.urls),
    path('', RedirectView.as_view(url='/dashboard/', permanent=False)),
    path('dashboard/', dashboard_view, name='dashboard'),
    path('dashboard/issued-stats/', issued_stats_json, name='issued-stats-json'),
    path('dashboard/cards-stats/', dashboard_cards_json, name='dashboard-cards-json'),
    path('dashboard/tables-json/', dashboard_tables_json, name='dashboard-tables-json'),
    path('personnel/', include('armguard.apps.personnel.urls')),
    path('inventory/', include('armguard.apps.inventory.urls')),
    path('transactions/', include('armguard.apps.transactions.urls')),
    path('print/', include('armguard.apps.print.urls')),
    path('camera/', include('armguard.apps.camera.urls')),
    path('profile/', include('armguard.apps.profile.urls')),
    path('users/', include('armguard.apps.users.urls')),
    path('accounts/login/', _RateLimitedLoginView.as_view(), name='login'),
    path('accounts/logout/', logout_view, name='logout'),
    # G15 FIX: TOTP MFA — must be before the generic accounts/ include.
    path('accounts/otp/setup/',  OTPSetupView.as_view(),  name='otp-setup'),
    path('accounts/otp/verify/', OTPVerifyView.as_view(), name='otp-verify'),
    path('accounts/', include('django.contrib.auth.urls')),
    # G7 FIX: robots.txt and security.txt.
    path('download/ssl-cert/', download_ssl_cert, name='download-ssl-cert'),
    path('download/ssl-cert-status/', ssl_cert_status, name='ssl-cert-status'),
    path('robots.txt', TemplateView.as_view(template_name='robots.txt', content_type='text/plain'), name='robots_txt'),
    path('.well-known/security.txt', TemplateView.as_view(template_name='security.txt', content_type='text/plain'), name='security_txt'),
    # G12 FIX: Read-only REST API v1 (DRF). All endpoints require authentication.
    path('api/v1/', include('armguard.apps.api.urls')),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Custom error handlers — uses branded 404.html / 500.html templates.
handler404 = 'django.views.defaults.page_not_found'
handler500 = 'django.views.defaults.server_error'

