"""
G12 FIX: URL configuration for the ARMGUARD read-only REST API v1.
G13 FIX: last-modified polling endpoint for frontend staleness detection.

Registered routes:
  GET  /api/v1/pistols/              → list
  GET  /api/v1/pistols/{item_id}/    → retrieve
  GET  /api/v1/rifles/               → list
  GET  /api/v1/rifles/{item_id}/     → retrieve
  GET  /api/v1/personnel/            → list
  GET  /api/v1/personnel/{id}/       → retrieve
  GET  /api/v1/transactions/         → list  (newest-first)
  GET  /api/v1/transactions/{id}/    → retrieve
  POST /api/v1/auth/token/           → obtain DRF auth token
  GET  /api/v1/last-modified/        → ISO-8601 timestamp of latest change (G13)
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token

from .views import (
    PistolViewSet, RifleViewSet, PersonnelViewSet, TransactionViewSet,
    LastModifiedView,
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
    # Token auth endpoint for headless clients.
    path('auth/token/', obtain_auth_token, name='api-token-auth'),
    # G13 FIX: Polling endpoint — returns latest updated_at timestamp across all transactions.
    path('last-modified/', LastModifiedView.as_view(), name='api-last-modified'),
]
