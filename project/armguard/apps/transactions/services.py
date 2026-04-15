"""
C6 FIX: Transaction save() side-effects service layer.

Extracted from Transaction.save() to dissolve the 769-line god-object
anti-pattern.  Each function has a single, documented responsibility and can be
unit-tested independently of the Django save() lifecycle.

Called exclusively by Transaction.save().  All functions run inside the
db_transaction.atomic() block that is already open when they are invoked.
"""
import logging

logger = logging.getLogger('armguard.transactions')


# ─────────────────────────────────────────────────────────────────────────────
# 1. Issuance-type propagation  (M6 fix)
# ─────────────────────────────────────────────────────────────────────────────

def propagate_issuance_type(transaction):
    """
    For new Return transactions with no explicit issuance_type, copy it from the
    most-recent matching Withdrawal so list views never need a correlated subquery.
    No-op for Withdrawals or when issuance_type is already set.

    FIX: For accessories-only returns (no pistol or rifle), use the open
    TransactionLogs record for the specific consumable being returned to resolve
    the issuance_type.  This avoids picking the wrong type when a personnel has
    multiple simultaneous open cycles (e.g. a PAR pistol and a TR-only accessory).
    """
    if transaction.pk or transaction.transaction_type != 'Return' or transaction.issuance_type:
        return
    from armguard.apps.transactions.models import Transaction, TransactionLogs
    qs = (
        Transaction.objects
        .filter(transaction_type='Withdrawal', personnel=transaction.personnel)
        .exclude(issuance_type__isnull=True)
        .exclude(issuance_type='')
    )
    if transaction.pistol:
        qs = qs.filter(pistol=transaction.pistol)
    elif transaction.rifle:
        qs = qs.filter(rifle=transaction.rifle)
    else:
        # Accessories-only return: resolve via the open TransactionLogs row for the
        # specific consumable, so personnel with mixed PAR/TR open cycles get the
        # correct issuance_type rather than whichever Withdrawal is most recent.
        log = None
        if transaction.pistol_magazine:
            log = TransactionLogs.objects.filter(
                personnel_id=transaction.personnel,
                withdraw_pistol_magazine=transaction.pistol_magazine,
                return_pistol_magazine__isnull=True,
            ).order_by('-withdraw_pistol_magazine_timestamp').first()
        elif transaction.rifle_magazine:
            log = TransactionLogs.objects.filter(
                personnel_id=transaction.personnel,
                withdraw_rifle_magazine=transaction.rifle_magazine,
                return_rifle_magazine__isnull=True,
            ).order_by('-withdraw_rifle_magazine_timestamp').first()
        elif transaction.pistol_ammunition:
            log = TransactionLogs.objects.filter(
                personnel_id=transaction.personnel,
                withdraw_pistol_ammunition=transaction.pistol_ammunition,
                return_pistol_ammunition__isnull=True,
            ).order_by('-withdraw_pistol_ammunition_timestamp').first()
        elif transaction.rifle_ammunition:
            log = TransactionLogs.objects.filter(
                personnel_id=transaction.personnel,
                withdraw_rifle_ammunition=transaction.rifle_ammunition,
                return_rifle_ammunition__isnull=True,
            ).order_by('-withdraw_rifle_ammunition_timestamp').first()
        elif transaction.pistol_holster_quantity:
            log = TransactionLogs.objects.filter(
                personnel_id=transaction.personnel,
                withdraw_pistol_holster_quantity__isnull=False,
                return_pistol_holster_quantity__isnull=True,
            ).order_by('-withdraw_pistol_holster_timestamp').first()
        elif transaction.magazine_pouch_quantity:
            log = TransactionLogs.objects.filter(
                personnel_id=transaction.personnel,
                withdraw_magazine_pouch_quantity__isnull=False,
                return_magazine_pouch_quantity__isnull=True,
            ).order_by('-withdraw_magazine_pouch_timestamp').first()
        elif transaction.rifle_sling_quantity:
            log = TransactionLogs.objects.filter(
                personnel_id=transaction.personnel,
                withdraw_rifle_sling_quantity__isnull=False,
                return_rifle_sling_quantity__isnull=True,
            ).order_by('-withdraw_rifle_sling_timestamp').first()
        elif transaction.bandoleer_quantity:
            log = TransactionLogs.objects.filter(
                personnel_id=transaction.personnel,
                withdraw_bandoleer_quantity__isnull=False,
                return_bandoleer_quantity__isnull=True,
            ).order_by('-withdraw_bandoleer_timestamp').first()
        if log and log.issuance_type:
            transaction.issuance_type = log.issuance_type
            return
        # Fall back to the most recent Withdrawal for this personnel when no
        # specific log row can be identified.
    match = qs.order_by('-timestamp').first()
    if match:
        transaction.issuance_type = match.issuance_type


# ─────────────────────────────────────────────────────────────────────────────
# 2. Personnel & item issued-status sync
# ─────────────────────────────────────────────────────────────────────────────

def sync_personnel_and_items(transaction, username):
    """
    Call Personnel.set_issued() and Pistol/Rifle.set_issued() for every item type
    present in this transaction.  Must be called after super().save() inside the
    atomic block.
    """
    p = transaction.personnel
    if not p:
        return
    pid = p.Personnel_ID
    ts = transaction.timestamp

    if transaction.transaction_type == 'Withdrawal':
        if transaction.pistol:
            p.set_issued('pistol', transaction.pistol.item_id, ts, username)
            transaction.pistol.set_issued(pid, ts, username)
        if transaction.rifle:
            p.set_issued('rifle', transaction.rifle.item_id, ts, username)
            transaction.rifle.set_issued(pid, ts, username)
        if transaction.pistol_magazine:
            p.set_issued('pistol_magazine', str(transaction.pistol_magazine), ts, username,
                         quantity=transaction.pistol_magazine_quantity)
        if transaction.rifle_magazine:
            p.set_issued('rifle_magazine', str(transaction.rifle_magazine), ts, username,
                         quantity=transaction.rifle_magazine_quantity)
        if transaction.pistol_ammunition:
            p.set_issued('pistol_ammunition', str(transaction.pistol_ammunition), ts, username,
                         quantity=transaction.pistol_ammunition_quantity)
        if transaction.rifle_ammunition:
            p.set_issued('rifle_ammunition', str(transaction.rifle_ammunition), ts, username,
                         quantity=transaction.rifle_ammunition_quantity)
        if transaction.pistol_holster_quantity:
            p.set_issued('pistol_holster', 'Pistol Holster', ts, username,
                         quantity=transaction.pistol_holster_quantity)
        if transaction.magazine_pouch_quantity:
            p.set_issued('magazine_pouch', 'Pistol Magazine Pouch', ts, username,
                         quantity=transaction.magazine_pouch_quantity)
        if transaction.rifle_sling_quantity:
            p.set_issued('rifle_sling', 'Rifle Sling', ts, username,
                         quantity=transaction.rifle_sling_quantity)
        if transaction.bandoleer_quantity:
            p.set_issued('bandoleer', 'Bandoleer', ts, username,
                         quantity=transaction.bandoleer_quantity)

    elif transaction.transaction_type == 'Return':
        if transaction.pistol:
            p.set_issued('pistol', None, None, None)
            transaction.pistol.set_issued(None, None, None)
        if transaction.rifle:
            p.set_issued('rifle', None, None, None)
            transaction.rifle.set_issued(None, None, None)
        if transaction.pistol_magazine:
            p.set_issued('pistol_magazine', None, None, None, quantity=None)
        if transaction.rifle_magazine:
            p.set_issued('rifle_magazine', None, None, None, quantity=None)
        if transaction.pistol_ammunition:
            p.set_issued('pistol_ammunition', None, None, None, quantity=None)
        if transaction.rifle_ammunition:
            p.set_issued('rifle_ammunition', None, None, None, quantity=None)
        if transaction.pistol_holster_quantity:
            p.set_issued('pistol_holster', None, None, None, quantity=None)
        if transaction.magazine_pouch_quantity:
            p.set_issued('magazine_pouch', None, None, None, quantity=None)
        if transaction.rifle_sling_quantity:
            p.set_issued('rifle_sling', None, None, None, quantity=None)
        if transaction.bandoleer_quantity:
            p.set_issued('bandoleer', None, None, None, quantity=None)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Consumable quantity adjustments (Magazine, Ammunition, Accessory)
# ─────────────────────────────────────────────────────────────────────────────

def adjust_consumable_quantities(transaction):
    """
    Decrease pool quantities on Withdrawal or restore them on Return for every
    Magazine, Ammunition, and Accessory type linked to this transaction.
    """
    from armguard.apps.inventory.models import Accessory
    sign = -1 if transaction.transaction_type == 'Withdrawal' else 1

    if transaction.pistol_magazine and transaction.pistol_magazine_quantity:
        transaction.pistol_magazine.adjust_quantity(sign * transaction.pistol_magazine_quantity)
    if transaction.rifle_magazine and transaction.rifle_magazine_quantity:
        transaction.rifle_magazine.adjust_quantity(sign * transaction.rifle_magazine_quantity)
    if transaction.pistol_ammunition and transaction.pistol_ammunition_quantity:
        transaction.pistol_ammunition.adjust_quantity(sign * transaction.pistol_ammunition_quantity)
    if transaction.rifle_ammunition and transaction.rifle_ammunition_quantity:
        transaction.rifle_ammunition.adjust_quantity(sign * transaction.rifle_ammunition_quantity)

    for acc_type, acc_qty in [
        ('Pistol Holster',        transaction.pistol_holster_quantity),
        ('Pistol Magazine Pouch', transaction.magazine_pouch_quantity),
        ('Rifle Sling',           transaction.rifle_sling_quantity),
        ('Bandoleer',             transaction.bandoleer_quantity),
    ]:
        if acc_qty:
            pool = Accessory.objects.filter(type=acc_type).first()
            if pool:
                pool.adjust_quantity(sign * acc_qty)


# ─────────────────────────────────────────────────────────────────────────────
# 4. TransactionLogs — Withdrawal (create new record)
# ─────────────────────────────────────────────────────────────────────────────

def create_withdrawal_log(transaction, username, TransactionLogs):
    """
    Create one TransactionLogs record for a Withdrawal event.
    - Pistol + rifle in the same transaction share one log row.
    - A standalone log row is created for magazine/ammo/accessory-only withdrawals.
    """
    txn = transaction
    ts = txn.timestamp

    # Shared consumable fields present on every log type
    shared = {
        'personnel_id': txn.personnel,
        'log_status': 'Open',
        'withdrawal_pistol_magazine_transaction_id':   txn if txn.pistol_magazine else None,
        'withdrawal_rifle_magazine_transaction_id':    txn if txn.rifle_magazine else None,
        'withdrawal_pistol_ammunition_transaction_id': txn if txn.pistol_ammunition else None,
        'withdrawal_rifle_ammunition_transaction_id':  txn if txn.rifle_ammunition else None,
        'withdraw_pistol_magazine':                    txn.pistol_magazine or None,
        'withdraw_pistol_magazine_quantity':           txn.pistol_magazine_quantity if txn.pistol_magazine else None,
        'withdraw_pistol_magazine_timestamp':          ts if txn.pistol_magazine else None,
        'withdraw_pistol_magazine_transaction_personnel': username if txn.pistol_magazine else None,
        'withdraw_rifle_magazine':                     txn.rifle_magazine or None,
        'withdraw_rifle_magazine_quantity':            txn.rifle_magazine_quantity if txn.rifle_magazine else None,
        'withdraw_rifle_magazine_timestamp':           ts if txn.rifle_magazine else None,
        'withdraw_rifle_magazine_transaction_personnel': username if txn.rifle_magazine else None,
        'withdraw_pistol_ammunition':                  txn.pistol_ammunition or None,
        'withdraw_pistol_ammunition_quantity':         txn.pistol_ammunition_quantity if txn.pistol_ammunition else None,
        'withdraw_pistol_ammunition_timestamp':        ts if txn.pistol_ammunition else None,
        'withdraw_pistol_ammunition_transaction_personnel': username if txn.pistol_ammunition else None,
        'withdraw_rifle_ammunition':                   txn.rifle_ammunition or None,
        'withdraw_rifle_ammunition_quantity':          txn.rifle_ammunition_quantity if txn.rifle_ammunition else None,
        'withdraw_rifle_ammunition_timestamp':         ts if txn.rifle_ammunition else None,
        'withdraw_rifle_ammunition_transaction_personnel': username if txn.rifle_ammunition else None,
        'withdrawal_pistol_holster_transaction_id':    txn if txn.pistol_holster_quantity else None,
        'withdraw_pistol_holster_quantity':            txn.pistol_holster_quantity or None,
        'withdraw_pistol_holster_timestamp':           ts if txn.pistol_holster_quantity else None,
        'withdraw_pistol_holster_transaction_personnel': username if txn.pistol_holster_quantity else None,
        'withdrawal_magazine_pouch_transaction_id':    txn if txn.magazine_pouch_quantity else None,
        'withdraw_magazine_pouch_quantity':            txn.magazine_pouch_quantity or None,
        'withdraw_magazine_pouch_timestamp':           ts if txn.magazine_pouch_quantity else None,
        'withdraw_magazine_pouch_transaction_personnel': username if txn.magazine_pouch_quantity else None,
        'withdrawal_rifle_sling_transaction_id':       txn if txn.rifle_sling_quantity else None,
        'withdraw_rifle_sling_quantity':               txn.rifle_sling_quantity or None,
        'withdraw_rifle_sling_timestamp':              ts if txn.rifle_sling_quantity else None,
        'withdraw_rifle_sling_transaction_personnel':  username if txn.rifle_sling_quantity else None,
        'withdrawal_bandoleer_transaction_id':         txn if txn.bandoleer_quantity else None,
        'withdraw_bandoleer_quantity':                 txn.bandoleer_quantity or None,
        'withdraw_bandoleer_timestamp':                ts if txn.bandoleer_quantity else None,
        'withdraw_bandoleer_transaction_personnel':    username if txn.bandoleer_quantity else None,
    }

    if txn.pistol and txn.rifle:
        TransactionLogs.objects.create(
            withdrawal_pistol_transaction_id=txn,
            withdraw_pistol=txn.pistol,
            withdraw_pistol_timestamp=ts,
            withdraw_pistol_transaction_personnel=username,
            withdrawal_rifle_transaction_id=txn,
            withdraw_rifle=txn.rifle,
            withdraw_rifle_timestamp=ts,
            withdraw_rifle_transaction_personnel=username,
            **shared,
        )
    elif txn.pistol:
        TransactionLogs.objects.create(
            withdrawal_pistol_transaction_id=txn,
            withdraw_pistol=txn.pistol,
            withdraw_pistol_timestamp=ts,
            withdraw_pistol_transaction_personnel=username,
            **shared,
        )
    elif txn.rifle:
        TransactionLogs.objects.create(
            withdrawal_rifle_transaction_id=txn,
            withdraw_rifle=txn.rifle,
            withdraw_rifle_timestamp=ts,
            withdraw_rifle_transaction_personnel=username,
            **shared,
        )

    # Magazine/ammo/accessories-only withdrawal (no pistol or rifle) → standalone row
    has_consumable = any([
        txn.pistol_magazine, txn.rifle_magazine,
        txn.pistol_ammunition, txn.rifle_ammunition,
        txn.pistol_holster_quantity, txn.magazine_pouch_quantity,
        txn.rifle_sling_quantity, txn.bandoleer_quantity,
    ])
    if not txn.pistol and not txn.rifle and has_consumable:
        TransactionLogs.objects.create(**shared)


# ─────────────────────────────────────────────────────────────────────────────
# 5. TransactionLogs — Return (find and update matching open logs)
# ─────────────────────────────────────────────────────────────────────────────

def _apply_return_fields(logs_to_save, obj, fields):
    """
    Merge field mutations into logs_to_save keyed by record_id.
    Accumulating into a shared dict ensures that pistol + rifle on the same
    combined log record are mutated together rather than fetched twice from DB.
    """
    if obj is None:
        return
    existing = logs_to_save.get(obj.record_id, obj)
    for attr, val in fields.items():
        setattr(existing, attr, val)
    logs_to_save[obj.record_id] = existing


def update_return_logs(transaction, username, user, TransactionLogs):
    """
    For a Return transaction, locate each item type's matching open log row,
    stamp the return data on it, recompute log_status, and persist.
    All mutations accumulate in logs_to_save (keyed by record_id) so a combined
    pistol+rifle log row is updated cohesively by both item queries.
    """
    txn = transaction
    ts = txn.timestamp
    logs_to_save = {}  # record_id → TransactionLogs instance

    if txn.pistol:
        obj = TransactionLogs.objects.select_for_update().filter(
            personnel_id=txn.personnel, withdraw_pistol=txn.pistol,
            return_pistol__isnull=True,
        ).order_by('-withdraw_pistol_timestamp').first()
        _apply_return_fields(logs_to_save, obj, {
            'return_pistol_transaction_id': txn,
            'return_pistol': txn.pistol,
            'return_pistol_timestamp': ts,
            'return_pistol_transaction_personnel': username,
        })

    if txn.rifle:
        obj = TransactionLogs.objects.select_for_update().filter(
            personnel_id=txn.personnel, withdraw_rifle=txn.rifle,
            return_rifle__isnull=True,
        ).order_by('-withdraw_rifle_timestamp').first()
        _apply_return_fields(logs_to_save, obj, {
            'return_rifle_transaction_id': txn,
            'return_rifle': txn.rifle,
            'return_rifle_timestamp': ts,
            'return_rifle_transaction_personnel': username,
        })

    if txn.pistol_magazine:
        obj = TransactionLogs.objects.select_for_update().filter(
            personnel_id=txn.personnel, withdraw_pistol_magazine=txn.pistol_magazine,
            return_pistol_magazine__isnull=True,
        ).order_by('-withdraw_pistol_magazine_timestamp').first()
        _apply_return_fields(logs_to_save, obj, {
            'return_pistol_magazine_transaction_id': txn,
            'return_pistol_magazine': txn.pistol_magazine,
            'return_pistol_magazine_quantity': txn.pistol_magazine_quantity,
            'return_pistol_magazine_timestamp': ts,
            'return_pistol_magazine_transaction_personnel': username,
        })

    if txn.rifle_magazine:
        obj = TransactionLogs.objects.select_for_update().filter(
            personnel_id=txn.personnel, withdraw_rifle_magazine=txn.rifle_magazine,
            return_rifle_magazine__isnull=True,
        ).order_by('-withdraw_rifle_magazine_timestamp').first()
        _apply_return_fields(logs_to_save, obj, {
            'return_rifle_magazine_transaction_id': txn,
            'return_rifle_magazine': txn.rifle_magazine,
            'return_rifle_magazine_quantity': txn.rifle_magazine_quantity,
            'return_rifle_magazine_timestamp': ts,
            'return_rifle_magazine_transaction_personnel': username,
        })

    if txn.pistol_ammunition:
        obj = TransactionLogs.objects.select_for_update().filter(
            personnel_id=txn.personnel, withdraw_pistol_ammunition=txn.pistol_ammunition,
            return_pistol_ammunition__isnull=True,
        ).order_by('-withdraw_pistol_ammunition_timestamp').first()
        _apply_return_fields(logs_to_save, obj, {
            'return_pistol_ammunition_transaction_id': txn,
            'return_pistol_ammunition': txn.pistol_ammunition,
            'return_pistol_ammunition_quantity': txn.pistol_ammunition_quantity,
            'return_pistol_ammunition_timestamp': ts,
            'return_pistol_ammunition_transaction_personnel': username,
        })

    if txn.rifle_ammunition:
        obj = TransactionLogs.objects.select_for_update().filter(
            personnel_id=txn.personnel, withdraw_rifle_ammunition=txn.rifle_ammunition,
            return_rifle_ammunition__isnull=True,
        ).order_by('-withdraw_rifle_ammunition_timestamp').first()
        _apply_return_fields(logs_to_save, obj, {
            'return_rifle_ammunition_transaction_id': txn,
            'return_rifle_ammunition': txn.rifle_ammunition,
            'return_rifle_ammunition_quantity': txn.rifle_ammunition_quantity,
            'return_rifle_ammunition_timestamp': ts,
            'return_rifle_ammunition_transaction_personnel': username,
        })

    # Accessory types — quantity-based lookup (no FK column)
    for acc_qty, w_qty_field, r_field, ts_field in [
        (txn.pistol_holster_quantity, 'withdraw_pistol_holster_quantity',
         'return_pistol_holster', 'withdraw_pistol_holster_timestamp'),
        (txn.magazine_pouch_quantity, 'withdraw_magazine_pouch_quantity',
         'return_magazine_pouch', 'withdraw_magazine_pouch_timestamp'),
        (txn.rifle_sling_quantity, 'withdraw_rifle_sling_quantity',
         'return_rifle_sling', 'withdraw_rifle_sling_timestamp'),
        (txn.bandoleer_quantity, 'withdraw_bandoleer_quantity',
         'return_bandoleer', 'withdraw_bandoleer_timestamp'),
    ]:
        if not acc_qty:
            continue
        obj = TransactionLogs.objects.select_for_update().filter(**{
            'personnel_id': txn.personnel,
            f'{w_qty_field}__isnull': False,
            f'{r_field}_quantity__isnull': True,
        }).order_by(f'-{ts_field}').first()
        _apply_return_fields(logs_to_save, obj, {
            f'{r_field}_transaction_id': txn,
            f'{r_field}_quantity': acc_qty,
            f'{r_field}_timestamp': ts,
            f'{r_field}_transaction_personnel': username,
        })

    for lobj in logs_to_save.values():
        lobj.update_log_status()
        lobj.save(user=user)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Audit log entry  (N3 fix)
# ─────────────────────────────────────────────────────────────────────────────

def write_audit_entry(transaction, username):
    """Write a structured INFO-level audit log for every committed transaction."""
    personnel_label = (
        f"{transaction.personnel.rank} {transaction.personnel.last_name} "
        f"[{transaction.personnel.Personnel_ID}]"
        if transaction.personnel else 'Unknown'
    )
    items = []
    if transaction.pistol:
        items.append(f"Pistol {transaction.pistol.item_id}")
    if transaction.rifle:
        items.append(f"Rifle {transaction.rifle.item_id}")
    if transaction.pistol_magazine:
        items.append(f"Pistol Mag x{transaction.pistol_magazine_quantity}")
    if transaction.rifle_magazine:
        items.append(f"Rifle Mag x{transaction.rifle_magazine_quantity}")
    if transaction.pistol_ammunition:
        items.append(f"Pistol Ammo x{transaction.pistol_ammunition_quantity}")
    if transaction.rifle_ammunition:
        items.append(f"Rifle Ammo x{transaction.rifle_ammunition_quantity}")
    logger.info(
        "ARMORY %s | txn_id=%s | personnel=%s | issuance=%s | items=[%s] | by=%s",
        transaction.transaction_type.upper(),
        transaction.transaction_id,
        personnel_label,
        transaction.issuance_type or 'N/A',
        ', '.join(items) or 'accessories',
        username or 'system',
    )
