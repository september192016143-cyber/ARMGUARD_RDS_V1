"""
G12 FIX: URL configuration for the ARMGUARD read-only REST API v1.
G13 FIX: last-modified polling endpoint for frontend staleness detection.
S01 FIX: obtain_auth_token replaced with ThrottledObtainAuthToken (5/min per IP).

Registered routes:
  GET  /api/v1/pistols/              → list
  GET  /api/v1/pistols/{item_id}/    → retrieve
  GET  /api/v1/rifles/               → list
  GET  /api/v1/rifles/{item_id}/     → retrieve
  GET  /api/v1/personnel/            → list
  GET  /api/v1/personnel/{id}/       → retrieve
  GET  /api/v1/transactions/         → list  (newest-first)
  GET  /api/v1/transactions/{id}/    → retrieve
  POST /api/v1/auth/token/           → obtain DRF auth token (5/min throttled)
  GET  /api/v1/last-modified/        → ISO-8601 timestamp of latest change (G13)
  GET  /api/v1/schema/               → OpenAPI 3.0 schema (drf-spectacular)
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

# T1 FIX: drf-spectacular OpenAPI schema view (staff-only).
try:
    from drf_spectacular.views import SpectacularAPIView
    _spectacular_available = True
except ImportError:
    _spectacular_available = False

from .views import (
    PistolViewSet, RifleViewSet, PersonnelViewSet, TransactionViewSet,
    LastModifiedView, ThrottledObtainAuthToken,
)

router = DefaultRouter()
router.register(r'pistols',      PistolViewSet,      basename='pistol')
router.register(r'rifles',       RifleViewSet,       basename='rifle')
router.register(r'personnel',    PersonnelViewSet,   basename='personnel')
router.register(r'transactions', TransactionViewSet, basename='transaction')

# N1 FIX: Namespace isolates DRF-generated URL names (pistol-list, rifle-list,
# personnel-list, transaction-list) from the identically-named web GUI URL names.
# Without this, {% url 'personnel-list' %} resolves to /api/v1/personnel/ instead
# of /personnel/ because the API urlconf is included after the web app urlconfs.
app_name = 'api'

urlpatterns = [
    path('', include(router.urls)),
    # S01 FIX: Token auth — throttled to 5 requests/minute per IP.
    path('auth/token/', ThrottledObtainAuthToken.as_view(), name='api-token-auth'),
    # G13 FIX: Polling endpoint — returns latest updated_at timestamp across all transactions.
    path('last-modified/', LastModifiedView.as_view(), name='api-last-modified'),
]

# T1 FIX: OpenAPI 3.0 schema — only registered when drf-spectacular is installed.
if _spectacular_available:
    urlpatterns += [
        path('schema/', SpectacularAPIView.as_view(), name='api-schema'),
    ]
