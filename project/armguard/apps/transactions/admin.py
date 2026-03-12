# Register your models here.
from django.contrib import admin

from .models import Transaction, TransactionLogs
from .forms import TransactionAdminForm
from django.contrib import admin
import os


class TransactionAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        obj.save(user=request.user)
        # Rename PAR document after save so transaction_id is available
        if (
            obj.par_document
            and obj.issuance_type
            and obj.issuance_type.startswith('PAR')
        ):
            personnel = obj.personnel
            rank = personnel.rank.replace(' ', '_') if personnel else 'UNK'
            last_name = personnel.last_name.replace(' ', '_') if personnel else 'UNK'
            new_filename = f"PAR_{rank}_{last_name}_{obj.transaction_id}.pdf"
            old_path = obj.par_document.path
            new_dir = os.path.dirname(old_path)
            new_path = os.path.join(new_dir, new_filename)
            if old_path != new_path and os.path.exists(old_path):
                os.rename(old_path, new_path)
                Transaction.objects.filter(pk=obj.pk).update(
                    par_document=f"PAR_PDF/{new_filename}"
                )
                obj.par_document.name = f"PAR_PDF/{new_filename}"

    def has_change_permission(self, request, obj=None):
        """
        REC-07: Transactions are operationally immutable — once created they form
        the permanent audit trail. Editing is blocked for all users except superusers.
        Superusers may correct data errors (e.g. wrong issuance_type) which will
        trigger the REC-06 signal to resync linked TransactionLogs automatically.
        """
        if obj is not None and not request.user.is_superuser:
            return False
        return super().has_change_permission(request, obj)

    form = TransactionAdminForm
    fieldsets = (
        (None, {
            'fields': (
                'transaction_type',
                'issuance_type',
                'purpose',
                'purpose_other',
                'qr_item_id',
                'pistol',
                'rifle',
                'pistol_ammunition',
                'pistol_ammunition_quantity',
                'rifle_ammunition',
                'rifle_ammunition_quantity',
                'pistol_magazine',
                'pistol_magazine_quantity',
                'rifle_magazine',
                'rifle_magazine_quantity',
                'pistol_holster_quantity',
                'magazine_pouch_quantity',
                'rifle_sling_quantity',
                'bandoleer_quantity',
                'qr_personnel_id',
                'personnel',
                'notes',
                'par_document',
            )
        }),
    )

admin.site.register(Transaction, TransactionAdmin)

# WithdrawalReturnTransactionsAdmin was removed — it only covered pistol/rifle columns,
# was never registered, and is fully superseded by TransactionLogsAdmin below.

class TransactionLogsAdmin(admin.ModelAdmin):
    def duty_type(self, obj):
        """
        FIX DIS. 5: Resolve duty_type from whichever withdrawal transaction FK is present.
        Now checks all five item types (pistol, rifle, magazine, ammunition, accessory)
        using the new withdrawal_magazine/ammunition/accessory_transaction_id FKs added in
        Fix Dis. 4 — so mag/ammo/accessory-only logs no longer show None.
        """
        for attr in (
            'withdrawal_pistol_transaction_id',
            'withdrawal_rifle_transaction_id',
            'withdrawal_pistol_magazine_transaction_id',
            'withdrawal_rifle_magazine_transaction_id',
            'withdrawal_pistol_ammunition_transaction_id',
            'withdrawal_rifle_ammunition_transaction_id',
            'withdrawal_pistol_holster_transaction_id',
            'withdrawal_magazine_pouch_transaction_id',
            'withdrawal_rifle_sling_transaction_id',
            'withdrawal_bandoleer_transaction_id',
        ):
            txn = getattr(obj, attr, None)
            if txn and txn.purpose:
                return txn.purpose
        return None

    duty_type.short_description = 'Duty Type'

    list_display = [
        'record_id',
        'personnel_id',
        'duty_type',  # Resolved via the duty_type() method above (reads from related withdrawal Transaction)
        'issuance_type',
        'log_status',
        # ── Pistol withdrawal ──────────────────────────────────────────────
        'withdrawal_pistol_transaction_id',
        'withdraw_pistol',
        'withdraw_pistol_timestamp',
        'withdraw_pistol_transaction_personnel',
        # ── Rifle withdrawal ───────────────────────────────────────────────
        'withdrawal_rifle_transaction_id',
        'withdraw_rifle',
        'withdraw_rifle_timestamp',
        'withdraw_rifle_transaction_personnel',
        # ── Pistol Magazine withdrawal ───────────────────────────────────────────
        'withdrawal_pistol_magazine_transaction_id',
        'withdraw_pistol_magazine',
        'withdraw_pistol_magazine_quantity',
        'withdraw_pistol_magazine_timestamp',
        # ── Rifle Magazine withdrawal ────────────────────────────────────────────
        'withdrawal_rifle_magazine_transaction_id',
        'withdraw_rifle_magazine',
        'withdraw_rifle_magazine_quantity',
        'withdraw_rifle_magazine_timestamp',
        # ── Pistol Ammunition withdrawal ────────────────────────────────────────
        'withdrawal_pistol_ammunition_transaction_id',
        'withdraw_pistol_ammunition',
        'withdraw_pistol_ammunition_quantity',
        'withdraw_pistol_ammunition_timestamp',
        # ── Rifle Ammunition withdrawal ──────────────────────────────────────────
        'withdrawal_rifle_ammunition_transaction_id',
        'withdraw_rifle_ammunition',
        'withdraw_rifle_ammunition_quantity',
        'withdraw_rifle_ammunition_timestamp',
        # ── Pistol Holster withdrawal ─────────────────────────────────────────
        'withdrawal_pistol_holster_transaction_id',
        'withdraw_pistol_holster_quantity',
        'withdraw_pistol_holster_timestamp',
        # ── Magazine Pouch withdrawal ─────────────────────────────────────────
        'withdrawal_magazine_pouch_transaction_id',
        'withdraw_magazine_pouch_quantity',
        'withdraw_magazine_pouch_timestamp',
        # ── Rifle Sling withdrawal ────────────────────────────────────────────
        'withdrawal_rifle_sling_transaction_id',
        'withdraw_rifle_sling_quantity',
        'withdraw_rifle_sling_timestamp',
        # ── Bandoleer withdrawal ──────────────────────────────────────────────
        'withdrawal_bandoleer_transaction_id',
        'withdraw_bandoleer_quantity',
        'withdraw_bandoleer_timestamp',
        # ── Pistol return ────────────────────────────────────────────────
        'return_pistol_transaction_id',
        'return_pistol',
        'return_pistol_timestamp',
        'return_pistol_transaction_personnel',
        # ── Rifle return ────────────────────────────────────────────────
        'return_rifle_transaction_id',
        'return_rifle',
        'return_rifle_timestamp',
        'return_rifle_transaction_personnel',
        # ── Pistol Magazine return ─────────────────────────────────────────
        'return_pistol_magazine',
        'return_pistol_magazine_quantity',
        'return_pistol_magazine_timestamp',
        # ── Rifle Magazine return ──────────────────────────────────────────
        'return_rifle_magazine',
        'return_rifle_magazine_quantity',
        'return_rifle_magazine_timestamp',
        # ── Pistol Ammunition return ───────────────────────────────────────
        'return_pistol_ammunition',
        'return_pistol_ammunition_quantity',
        'return_pistol_ammunition_timestamp',
        # ── Rifle Ammunition return ──────────────────────────────────────────
        'return_rifle_ammunition',
        'return_rifle_ammunition_quantity',
        'return_rifle_ammunition_timestamp',
        # ── Pistol Holster return ───────────────────────────────────────────
        'return_pistol_holster_quantity',
        'return_pistol_holster_timestamp',
        # ── Magazine Pouch return ─────────────────────────────────────────────────────
        'return_magazine_pouch_quantity',
        'return_magazine_pouch_timestamp',
        # ── Rifle Sling return ────────────────────────────────────────────────────────
        'return_rifle_sling_quantity',
        'return_rifle_sling_timestamp',
        # ── Bandoleer return ──────────────────────────────────────────────────────────
        'return_bandoleer_quantity',
        'return_bandoleer_timestamp',
    ]
    search_fields = ['personnel_id__Personnel_ID']
    list_filter = [
        'log_status',
        'withdraw_pistol_timestamp',
        'withdraw_rifle_timestamp',
        'return_pistol_timestamp',
        'return_rifle_timestamp',
    ]
    readonly_fields = ['log_status']

admin.site.register(TransactionLogs, TransactionLogsAdmin)
