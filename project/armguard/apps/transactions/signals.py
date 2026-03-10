"""
Signal-based audit logging for ARMGUARD RDS.

Captures create / update / delete events on Transaction, TransactionLogs,
Pistol, Rifle, and Personnel and writes them to the 'armguard.audit' logger.

Configure the logger in settings.py LOGGING to route to a file handler,
email handler, or any Django-supported backend.

Example settings.py LOGGING entry:
    'armguard.audit': {
        'handlers': ['audit_file'],
        'level': 'INFO',
        'propagate': False,
    },
"""

import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

audit_logger = logging.getLogger('armguard.audit')


# ── helpers ──────────────────────────────────────────────────────────────────

def _pk(instance):
    """Return the primary key value of a model instance."""
    pk_field = instance._meta.pk
    return getattr(instance, pk_field.attname, None) if pk_field else None


def _write_audit_log(action, instance, extra=''):
    """
    G3 FIX: Write a persistent AuditLog record to the database.
    Lazily imports AuditLog to avoid circular imports at module load time.
    Silently swallows all errors so a DB hiccup never kills a request.
    """
    try:
        from django.apps import apps
        AuditLog = apps.get_model('users', 'AuditLog')
        AuditLog.objects.create(
            action=action,
            model_name=type(instance).__name__,
            object_pk=str(_pk(instance) or ''),
            message=extra,
        )
    except Exception:
        pass


def _log(action, instance, extra=''):
    model_name = type(instance).__name__
    pk = _pk(instance)
    audit_logger.info(
        "[AUDIT] action=%-8s model=%-20s pk=%s %s",
        action, model_name, pk, extra,
    )
    # G3 FIX: Also persist to the AuditLog database table.
    _write_audit_log(action, instance, extra)


def _resync_log_issuance_type(transaction):
    """
    Update issuance_type on all TransactionLogs rows linked to this Transaction
    via any of the 10 withdrawal_*_transaction_id FK fields.
    Called on Transaction UPDATE to prevent issuance_type snapshot drift. (REC-06)
    """
    from django.apps import apps
    from django.db.models import Q
    TransactionLogs = apps.get_model('transactions', 'TransactionLogs')
    fk_fields = [
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
    ]
    query = Q()
    for fk in fk_fields:
        query |= Q(**{f'{fk}__pk': transaction.pk})
    updated = TransactionLogs.objects.filter(query).update(
        issuance_type=transaction.issuance_type
    )
    if updated:
        audit_logger.info(
            "[AUDIT] action=RESYNC   model=TransactionLogs      "
            "reason=issuance_type_drift transaction_id=%s rows_updated=%d",
            transaction.pk, updated,
        )


# ── Transaction ───────────────────────────────────────────────────────────────

@receiver(post_save, sender='transactions.Transaction')
def on_transaction_save(sender, instance, created, **kwargs):
    action = 'CREATE' if created else 'UPDATE'
    _log(
        action, instance,
        f"type={instance.transaction_type} "
        f"personnel={instance.personnel_id} "
        f"user={instance.transaction_personnel}",
    )
    # REC-06: On edit (not creation), resync issuance_type on linked TransactionLogs
    # rows to prevent snapshot drift when issuance_type is corrected post-creation.
    if not created and instance.issuance_type:
        _resync_log_issuance_type(instance)


@receiver(post_delete, sender='transactions.Transaction')
def on_transaction_delete(sender, instance, **kwargs):
    _log('DELETE', instance, f"type={instance.transaction_type}")


# ── TransactionLogs ───────────────────────────────────────────────────────────

@receiver(post_save, sender='transactions.TransactionLogs')
def on_transactionlogs_save(sender, instance, created, **kwargs):
    action = 'CREATE' if created else 'UPDATE'
    _log(action, instance, f"status={instance.log_status} personnel={instance.personnel_id_id}")


@receiver(post_delete, sender='transactions.TransactionLogs')
def on_transactionlogs_delete(sender, instance, **kwargs):
    _log('DELETE', instance)


# ── Pistol / Rifle ────────────────────────────────────────────────────────────

@receiver(post_save, sender='inventory.Pistol')
def on_pistol_save(sender, instance, created, **kwargs):
    action = 'CREATE' if created else 'UPDATE'
    _log(action, instance, f"status={instance.item_status} issued_to={instance.item_issued_to_id}")


@receiver(post_delete, sender='inventory.Pistol')
def on_pistol_delete(sender, instance, **kwargs):
    _log('DELETE', instance)


@receiver(post_save, sender='inventory.Rifle')
def on_rifle_save(sender, instance, created, **kwargs):
    action = 'CREATE' if created else 'UPDATE'
    _log(action, instance, f"status={instance.item_status} issued_to={instance.item_issued_to_id}")


@receiver(post_delete, sender='inventory.Rifle')
def on_rifle_delete(sender, instance, **kwargs):
    _log('DELETE', instance)


# ── Personnel ─────────────────────────────────────────────────────────────────

@receiver(post_save, sender='personnel.Personnel')
def on_personnel_save(sender, instance, created, **kwargs):
    action = 'CREATE' if created else 'UPDATE'
    _log(
        action, instance,
        f"rank={instance.rank} status={instance.status} "
        f"pistol={instance.pistol_item_issued} rifle={instance.rifle_item_issued}",
    )


@receiver(post_delete, sender='personnel.Personnel')
def on_personnel_delete(sender, instance, **kwargs):
    _log('DELETE', instance, f"rank={instance.rank}")


# ── Magazine / Ammunition / Accessory ───────────────────────────────────────────
# FIX J: Extend audit coverage to the three pool inventory models.
# Direct admin edits to quantity, duty_type, or type will now appear in audit.log.

@receiver(post_save, sender='inventory.Magazine')
def on_magazine_save(sender, instance, created, **kwargs):
    action = 'CREATE' if created else 'UPDATE'
    _log(action, instance, f"type={instance.type} capacity={instance.capacity} qty={instance.quantity}")


@receiver(post_delete, sender='inventory.Magazine')
def on_magazine_delete(sender, instance, **kwargs):
    _log('DELETE', instance, f"type={instance.type} qty={instance.quantity}")


@receiver(post_save, sender='inventory.Ammunition')
def on_ammunition_save(sender, instance, created, **kwargs):
    action = 'CREATE' if created else 'UPDATE'
    _log(action, instance, f"type={instance.type} lot={instance.lot_number} qty={instance.quantity}")


@receiver(post_delete, sender='inventory.Ammunition')
def on_ammunition_delete(sender, instance, **kwargs):
    _log('DELETE', instance, f"type={instance.type} lot={instance.lot_number} qty={instance.quantity}")


@receiver(post_save, sender='inventory.Accessory')
def on_accessory_save(sender, instance, created, **kwargs):
    action = 'CREATE' if created else 'UPDATE'
    _log(action, instance, f"type={instance.type} qty={instance.quantity}")


@receiver(post_delete, sender='inventory.Accessory')
def on_accessory_delete(sender, instance, **kwargs):
    _log('DELETE', instance, f"type={instance.type} qty={instance.quantity}")
