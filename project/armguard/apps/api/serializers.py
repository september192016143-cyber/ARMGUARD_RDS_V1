"""
G12 FIX: Read-only DRF serializers for the ARMGUARD public API.

All serializers expose only non-sensitive, non-media fields so that
consuming clients (dashboards, audit tools) can query inventory and
transaction history without accessing PII-heavy file upload paths.
"""
import datetime as _dt

from rest_framework import serializers


class UTCDateTimeField(serializers.DateTimeField):
    """Serialize a datetime to a UTC ISO-8601 string ending in 'Z'.

    Django stores datetimes in UTC internally (USE_TZ=True) and the
    default DRF renderer localises them to TIME_ZONE (Asia/Manila = +08:00).
    This field converts to UTC before formatting so all API consumers see
    a consistent timezone-neutral representation.
    """

    def to_representation(self, value):
        if value is None:
            return None
        if hasattr(value, 'astimezone'):
            value = value.astimezone(_dt.timezone.utc)
        return value.strftime('%Y-%m-%dT%H:%M:%SZ')

from armguard.apps.inventory.models import Pistol, Rifle
from armguard.apps.personnel.models import Personnel
from armguard.apps.transactions.models import Transaction


class PistolSerializer(serializers.ModelSerializer):
    created = UTCDateTimeField(read_only=True)

    class Meta:
        model = Pistol
        fields = [
            'item_id',
            'item_number',
            'model',
            'serial_number',
            'item_status',
            'item_condition',
            'created',
        ]
        read_only_fields = fields


class RifleSerializer(serializers.ModelSerializer):
    created = UTCDateTimeField(read_only=True)

    class Meta:
        model = Rifle
        fields = [
            'item_id',
            'item_number',
            'model',
            'serial_number',
            'item_status',
            'item_condition',
            'created',
        ]
        read_only_fields = fields


class PersonnelSerializer(serializers.ModelSerializer):
    # F13 FIX: Expose snake_case 'personnel_id' instead of legacy 'Personnel_ID' field name.
    personnel_id = serializers.CharField(source='Personnel_ID', read_only=True)

    class Meta:
        model = Personnel
        fields = [
            'personnel_id',
            'rank',
            'first_name',
            'last_name',
            'middle_initial',
            'status',
            'group',
        ]
        read_only_fields = fields


class TransactionSerializer(serializers.ModelSerializer):
    personnel_id = serializers.CharField(source='personnel.Personnel_ID', read_only=True)
    pistol_id    = serializers.CharField(source='pistol.item_id',         read_only=True, default=None)
    rifle_id     = serializers.CharField(source='rifle.item_id',          read_only=True, default=None)
    # Render timestamp as UTC 'Z' to match LastModifiedView and avoid +08:00 ambiguity.
    timestamp    = UTCDateTimeField(read_only=True)

    class Meta:
        model = Transaction
        fields = [
            'transaction_id',
            'transaction_type',
            'issuance_type',
            'purpose',
            'personnel_id',
            'pistol_id',
            'rifle_id',
            'pistol_magazine_quantity',
            'rifle_magazine_quantity',
            'pistol_ammunition_quantity',
            'rifle_ammunition_quantity',
            'timestamp',
            # M3 FIX: 'notes' removed — internal operational field; not for public API.
            # updated_at removed — internal metadata; not for API consumers.
        ]
        read_only_fields = fields
