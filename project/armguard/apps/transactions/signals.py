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
    # Bug 2 fix: use per-row save() instead of bulk .update() so that the
    # post_save signal fires for each row and _write_audit_log() is called,
    # persisting an AuditLog DB record for every issuance_type correction.
    rows_updated = 0
    for log_row in TransactionLogs.objects.filter(query):
        if log_row.issuance_type != transaction.issuance_type:
            log_row.issuance_type = transaction.issuance_type
            log_row.save(update_fields=['issuance_type'])
            rows_updated += 1
    if rows_updated:
        audit_logger.info(
            "[AUDIT] action=RESYNC   model=TransactionLogs      "
            "reason=issuance_type_drift transaction_id=%s rows_updated=%d",
            transaction.pk, rows_updated,
        )


def _resync_log_consumable_fields(transaction):
    """
    When an existing Withdrawal transaction is edited, stamp the current consumable
    field values (magazine, ammunition, accessory) onto all linked TransactionLogs
    rows so the dashboard counts remain accurate.

    All consumable fields are written unconditionally — if an item was removed from
    the transaction, the corresponding TransactionLogs field is set to NULL so the
    dashboard does not over-count it.  Previously only non-null items were written,
    leaving removed items permanently stale (Loophole 1 fix).

    Individual row saves are used (rather than a bulk .update()) so the post_save
    signal fires for each row, persisting an AuditLog DB record for every change
    (Loophole 2 fix: bulk .update() bypassed post_save and the AuditLog table).

    Raw attnames (_id suffix) are used for all FK assignments so that
    save(update_fields=[...]) resolves every column correctly (Loophole 5 fix:
    the previous exists() round-trip is eliminated by iterating directly).

    transaction.transaction_personnel is stamped as the operator on each consumable
    field that is set (Loophole 6 fix: previously these fields were left NULL on
    resync because the current user is not available in the signal context).
    """
    if transaction.transaction_type != 'Withdrawal':
        return
    from django.apps import apps
    from django.db.models import Q
    TransactionLogs = apps.get_model('transactions', 'TransactionLogs')
    ts = transaction.timestamp
    operator = transaction.transaction_personnel

    # Find all log rows associated with this transaction via any withdrawal FK.
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

    # Always write all consumable fields.  Setting a field to None clears it
    # when the item was removed from the transaction since the log was created.
    # Using raw attnames (_id suffix) throughout so save(update_fields=...) works.
    update_kwargs = {
        # --- Magazines ---
        'withdrawal_pistol_magazine_transaction_id':      transaction.pk if transaction.pistol_magazine_id else None,
        'withdraw_pistol_magazine_id':                    transaction.pistol_magazine_id,
        'withdraw_pistol_magazine_quantity':              transaction.pistol_magazine_quantity if transaction.pistol_magazine_id else None,
        'withdraw_pistol_magazine_timestamp':             ts if transaction.pistol_magazine_id else None,
        'withdraw_pistol_magazine_transaction_personnel': operator if transaction.pistol_magazine_id else None,
        'withdrawal_rifle_magazine_transaction_id':       transaction.pk if transaction.rifle_magazine_id else None,
        'withdraw_rifle_magazine_id':                     transaction.rifle_magazine_id,
        'withdraw_rifle_magazine_quantity':               transaction.rifle_magazine_quantity if transaction.rifle_magazine_id else None,
        'withdraw_rifle_magazine_timestamp':              ts if transaction.rifle_magazine_id else None,
        'withdraw_rifle_magazine_transaction_personnel':  operator if transaction.rifle_magazine_id else None,
        # --- Ammunition ---
        'withdrawal_pistol_ammunition_transaction_id':       transaction.pk if transaction.pistol_ammunition_id else None,
        'withdraw_pistol_ammunition_id':                     transaction.pistol_ammunition_id,
        'withdraw_pistol_ammunition_quantity':               transaction.pistol_ammunition_quantity if transaction.pistol_ammunition_id else None,
        'withdraw_pistol_ammunition_timestamp':              ts if transaction.pistol_ammunition_id else None,
        'withdraw_pistol_ammunition_transaction_personnel':  operator if transaction.pistol_ammunition_id else None,
        'withdrawal_rifle_ammunition_transaction_id':        transaction.pk if transaction.rifle_ammunition_id else None,
        'withdraw_rifle_ammunition_id':                      transaction.rifle_ammunition_id,
        'withdraw_rifle_ammunition_quantity':                transaction.rifle_ammunition_quantity if transaction.rifle_ammunition_id else None,
        'withdraw_rifle_ammunition_timestamp':               ts if transaction.rifle_ammunition_id else None,
        'withdraw_rifle_ammunition_transaction_personnel':   operator if transaction.rifle_ammunition_id else None,
        # --- Accessories ---
        'withdrawal_pistol_holster_transaction_id':       transaction.pk if transaction.pistol_holster_quantity else None,
        'withdraw_pistol_holster_quantity':               transaction.pistol_holster_quantity or None,
        'withdraw_pistol_holster_timestamp':              ts if transaction.pistol_holster_quantity else None,
        'withdraw_pistol_holster_transaction_personnel':  operator if transaction.pistol_holster_quantity else None,
        'withdrawal_magazine_pouch_transaction_id':       transaction.pk if transaction.magazine_pouch_quantity else None,
        'withdraw_magazine_pouch_quantity':               transaction.magazine_pouch_quantity or None,
        'withdraw_magazine_pouch_timestamp':              ts if transaction.magazine_pouch_quantity else None,
        'withdraw_magazine_pouch_transaction_personnel':  operator if transaction.magazine_pouch_quantity else None,
        'withdrawal_rifle_sling_transaction_id':          transaction.pk if transaction.rifle_sling_quantity else None,
        'withdraw_rifle_sling_quantity':                  transaction.rifle_sling_quantity or None,
        'withdraw_rifle_sling_timestamp':                 ts if transaction.rifle_sling_quantity else None,
        'withdraw_rifle_sling_transaction_personnel':     operator if transaction.rifle_sling_quantity else None,
        'withdrawal_bandoleer_transaction_id':            transaction.pk if transaction.bandoleer_quantity else None,
        'withdraw_bandoleer_quantity':                    transaction.bandoleer_quantity or None,
        'withdraw_bandoleer_timestamp':                   ts if transaction.bandoleer_quantity else None,
        'withdraw_bandoleer_transaction_personnel':       operator if transaction.bandoleer_quantity else None,
    }
    update_field_names = list(update_kwargs.keys())

    rows_updated = 0
    for log_row in TransactionLogs.objects.filter(query):
        # Bug 1 fix: skip rows that are already correct to avoid spurious
        # AuditLog DB entries on every Withdrawal save.
        # FK fields whose field.name ends in _transaction_id store their raw PK
        # under field.attname = field.name + '_id' in __dict__.  Non-FK fields
        # and FK attnames (e.g. withdraw_pistol_magazine_id) are stored as-is.
        raw_cache = log_row.__dict__
        actually_changed = any(
            raw_cache.get(k + '_id', raw_cache.get(k)) != v
            for k, v in update_kwargs.items()
        )
        if not actually_changed:
            continue
        for attr, val in update_kwargs.items():
            # FK fields whose field.name ends in _transaction_id have attname
            # field.name + '_id'.  setattr with the field.name hits the FK
            # descriptor __set__ which requires a model instance, not an integer.
            # Using the attname bypasses the descriptor and writes the raw PK.
            attname = (attr + '_id') if attr.endswith('_transaction_id') else attr
            setattr(log_row, attname, val)
        log_row.save(update_fields=update_field_names)
        rows_updated += 1

    if rows_updated:
        audit_logger.info(
            "[AUDIT] action=RESYNC   model=TransactionLogs      "
            "reason=consumable_field_drift transaction_id=%s rows_updated=%d",
            transaction.pk, rows_updated,
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
    # Resync magazine/ammo/accessory fields on linked TransactionLogs rows when
    # an existing Withdrawal is edited (e.g. magazine added after initial save).
    if not created and instance.transaction_type == 'Withdrawal':
        _resync_log_consumable_fields(instance)


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
