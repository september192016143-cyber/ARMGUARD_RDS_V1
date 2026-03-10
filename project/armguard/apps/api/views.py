"""
G12 FIX: Read-only DRF viewsets for the ARMGUARD API.
G13 FIX: LastModifiedView — lightweight polling endpoint used by the
         frontend to detect inventory/transaction changes without Redis
         or Django Channels.

All viewsets are read-only (list + retrieve).  Write operations are
intentionally excluded — all mutations must go through the UI to
preserve business-rule enforcement (select_for_update, audit log, etc.).

Access requires a valid session (IsAuthenticated) so the API cannot be
used by anonymous callers.  Token auth is included as an alternative
to session auth for headless clients (CI dashboards, audit scripts).
"""
from django.db.models import Max
from django.utils import timezone
from rest_framework import viewsets, permissions, mixins
from rest_framework.response import Response
from rest_framework.views import APIView

from armguard.apps.inventory.models import Pistol, Rifle
from armguard.apps.personnel.models import Personnel
from armguard.apps.transactions.models import Transaction

from .serializers import (
    PistolSerializer,
    RifleSerializer,
    PersonnelSerializer,
    TransactionSerializer,
)


class _ReadOnlyModelViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Base class: list + retrieve only, no create/update/delete."""
    permission_classes = [permissions.IsAuthenticated]


class PistolViewSet(_ReadOnlyModelViewSet):
    serializer_class = PistolSerializer
    queryset = Pistol.objects.all().order_by('item_id')


class RifleViewSet(_ReadOnlyModelViewSet):
    serializer_class = RifleSerializer
    queryset = Rifle.objects.all().order_by('item_id')


class PersonnelViewSet(_ReadOnlyModelViewSet):
    # F5 FIX: Restrict to is_staff users only — Personnel records contain military PII
    # (full names, ranks, service IDs). Token-authenticated audit clients must have
    # is_staff=True to access this viewset.
    permission_classes = [permissions.IsAdminUser]
    serializer_class = PersonnelSerializer
    queryset = Personnel.objects.all().order_by('Personnel_ID')


class TransactionViewSet(_ReadOnlyModelViewSet):
    # F5 FIX (extended): Transaction logs contain operational security records
    # (who holds which weapon, when, under which issuance type). Restrict to
    # is_staff users only, consistent with PersonnelViewSet.
    permission_classes = [permissions.IsAdminUser]
    serializer_class = TransactionSerializer
    queryset = (
        Transaction.objects
        .select_related('personnel', 'pistol', 'rifle')
        .order_by('-timestamp')
    )


class LastModifiedView(APIView):
    """
    G13 FIX: Returns the ISO-8601 timestamp of the most recent change
    across all transaction records.  The frontend polls this every 30 s
    and shows a toast notification when the value advances.

    Single lightweight DB query (MAX aggregate on one indexed column) —
    no Redis or Channels required.

    GET /api/v1/last-modified/
    Response: { "last_modified": "2026-03-09T14:32:01.123456Z", "now": "..." }
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        result = Transaction.objects.aggregate(ts=Max('updated_at'))
        ts = result['ts']
        # F10 FIX: Use fixed-width UTC format (no microseconds, no TZ-offset variation)
        # so the JS string-equality comparison is stable across deployments.
        last_modified = ts.strftime('%Y-%m-%dT%H:%M:%SZ') if ts else None
        return Response({
            'last_modified': last_modified,
            'now': timezone.now().strftime('%Y-%m-%dT%H:%M:%SZ'),
        })
