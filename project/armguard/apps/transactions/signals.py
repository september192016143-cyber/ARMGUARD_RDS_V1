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
import os
from django.conf import settings
from django.db.models.signals import pre_save, post_save, post_delete
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
    except Exception as _audit_exc:
        audit_logger.warning('AuditLog write failed: %s', _audit_exc)


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


def _remove_file(relative_name):
    """Delete a MEDIA_ROOT-relative file silently."""
    if not relative_name:
        return
    try:
        path = os.path.join(settings.MEDIA_ROOT, relative_name)
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


# ── Transaction ───────────────────────────────────────────────────────────────

@receiver(pre_save, sender='transactions.Transaction')
def on_transaction_pre_save(sender, instance, **kwargs):
    """Delete old par_document when it is replaced on an existing record."""
    if not instance.pk:
        return
    try:
        old = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    old_doc = old.par_document.name if old.par_document else None
    new_doc = instance.par_document.name if instance.par_document else None
    if old_doc and old_doc != new_doc:
        _remove_file(old_doc)


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
    if instance.par_document and instance.par_document.name:
        _remove_file(instance.par_document.name)


# ── TransactionLogs ───────────────────────────────────────────────────────────

@receiver(post_save, sender='transactions.TransactionLogs')
def on_transactionlogs_save(sender, instance, created, **kwargs):
    action = 'CREATE' if created else 'UPDATE'
    _log(action, instance, f"status={instance.log_status} personnel={instance.personnel_id_id}")


@receiver(post_delete, sender='transactions.TransactionLogs')
def on_transactionlogs_delete(sender, instance, **kwargs):
    _log('DELETE', instance)


# ── Pistol / Rifle ────────────────────────────────────────────────────────────

@receiver(pre_save, sender='inventory.Pistol')
def on_pistol_pre_save(sender, instance, **kwargs):
    """Delete old serial_image, qr_code_image, item_tag when replaced."""
    if not instance.pk:
        return
    try:
        old = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    for attr in ('serial_image', 'qr_code_image', 'item_tag'):
        old_f = getattr(old, attr)
        new_f = getattr(instance, attr)
        old_name = old_f.name if old_f else None
        new_name = new_f.name if new_f else None
        if old_name and old_name != new_name:
            _remove_file(old_name)


@receiver(post_save, sender='inventory.Pistol')
def on_pistol_save(sender, instance, created, **kwargs):
    action = 'CREATE' if created else 'UPDATE'
    _log(action, instance, f"status={instance.item_status} issued_to={instance.item_issued_to_id}")


@receiver(post_delete, sender='inventory.Pistol')
def on_pistol_delete(sender, instance, **kwargs):
    _log('DELETE', instance)
    for attr in ('serial_image', 'qr_code_image', 'item_tag'):
        f = getattr(instance, attr)
        if f and f.name:
            _remove_file(f.name)


@receiver(pre_save, sender='inventory.Rifle')
def on_rifle_pre_save(sender, instance, **kwargs):
    """Delete old serial_image, qr_code_image, item_tag when replaced."""
    if not instance.pk:
        return
    try:
        old = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    for attr in ('serial_image', 'qr_code_image', 'item_tag'):
        old_f = getattr(old, attr)
        new_f = getattr(instance, attr)
        old_name = old_f.name if old_f else None
        new_name = new_f.name if new_f else None
        if old_name and old_name != new_name:
            _remove_file(old_name)


@receiver(post_save, sender='inventory.Rifle')
def on_rifle_save(sender, instance, created, **kwargs):
    action = 'CREATE' if created else 'UPDATE'
    _log(action, instance, f"status={instance.item_status} issued_to={instance.item_issued_to_id}")


@receiver(post_delete, sender='inventory.Rifle')
def on_rifle_delete(sender, instance, **kwargs):
    _log('DELETE', instance)
    for attr in ('serial_image', 'qr_code_image', 'item_tag'):
        f = getattr(instance, attr)
        if f and f.name:
            _remove_file(f.name)


# ── Personnel ─────────────────────────────────────────────────────────────────


@receiver(pre_save, sender='personnel.Personnel')
def on_personnel_pre_save(sender, instance, **kwargs):
    """When personnel_image or qr_code_image is replaced, delete the old file."""
    if not instance.pk:
        return  # new record — nothing to clean up
    try:
        old = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    # Delete old personnel photo if it changed
    old_photo = old.personnel_image.name if old.personnel_image else None
    new_photo = instance.personnel_image.name if instance.personnel_image else None
    if old_photo and old_photo != new_photo:
        _remove_file(old_photo)
    # Delete old QR image if it changed
    old_qr = old.qr_code_image.name if old.qr_code_image else None
    new_qr = instance.qr_code_image.name if instance.qr_code_image else None
    if old_qr and old_qr != new_qr:
        _remove_file(old_qr)

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
    # Clean up all files on disk that belong to this personnel record.
    if instance.personnel_image and instance.personnel_image.name:
        _remove_file(instance.personnel_image.name)
    if instance.qr_code_image and instance.qr_code_image.name:
        _remove_file(instance.qr_code_image.name)
    # ID card files (combined, front, back)
    pid = instance.Personnel_ID
    card_dir = os.path.join(settings.MEDIA_ROOT, 'personnel_id_cards')
    for suffix in ('', '_front', '_back'):
        _remove_file(os.path.join('personnel_id_cards', f"{pid}{suffix}.png"))


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


# ── SerialImageCapture ────────────────────────────────────────────────────────

@receiver(post_delete, sender='inventory.SerialImageCapture')
def on_serial_image_capture_delete(sender, instance, **kwargs):
    if instance.image and instance.image.name:
        _remove_file(instance.image.name)


# ── FirearmDiscrepancy ────────────────────────────────────────────────────────

@receiver(pre_save, sender='inventory.FirearmDiscrepancy')
def on_discrepancy_pre_save(sender, instance, **kwargs):
    """Delete old discrepancy images when replaced."""
    if not instance.pk:
        return
    try:
        old = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    for attr in ('image', 'image_2', 'image_3', 'image_4', 'image_5'):
        old_f = getattr(old, attr)
        new_f = getattr(instance, attr)
        old_name = old_f.name if old_f else None
        new_name = new_f.name if new_f else None
        if old_name and old_name != new_name:
            _remove_file(old_name)


@receiver(post_delete, sender='inventory.FirearmDiscrepancy')
def on_discrepancy_delete(sender, instance, **kwargs):
    for attr in ('image', 'image_2', 'image_3', 'image_4', 'image_5'):
        f = getattr(instance, attr)
        if f and f.name:
            _remove_file(f.name)


# ── SystemSettings (app_logo) ──────────────────────────────────────────────────

@receiver(pre_save, sender='users.SystemSettings')
def on_system_settings_pre_save(sender, instance, **kwargs):
    """Delete old app_logo when it is replaced."""
    if not instance.pk:
        return
    try:
        old = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    old_logo = old.app_logo.name if old.app_logo else None
    new_logo = instance.app_logo.name if instance.app_logo else None
    if old_logo and old_logo != new_logo:
        _remove_file(old_logo)


@receiver(post_delete, sender='users.SystemSettings')
def on_system_settings_delete(sender, instance, **kwargs):
    if instance.app_logo and instance.app_logo.name:
        _remove_file(instance.app_logo.name)
