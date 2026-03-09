# ARMGUARD_RDS_V1 — Database Schema Reference

**Version:** 1.0  
**Last Updated:** 2026-03-05  
**Database Engine:** SQLite (dev) / PostgreSQL (prod-ready)  
**Django Version:** 6.0.2  

> This document reflects the V1 schema as implemented in migrations. It maps directly to the RDS Database Audit report and documents all applied fix-series changes.

---

## 1. Schema Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          AUTH_USER_MODEL (Django built-in)                 │
└────────────────────────────┬────────────────────────────────────────────────┘
                             │ OneToOne (CASCADE)          │ OneToOne (SET_NULL)
                             ▼                             ▼
                      ┌─────────────┐              ┌──────────────┐
                      │ UserProfile │              │  Personnel   │
                      │  (users)    │              │ (personnel)  │
                      └─────────────┘              └──────┬───────┘
                                                          │ FK (PROTECT)
                                                          ▼
      ┌──────────────────────────────────────────────────────────────────┐
      │                      Transaction (transactions)                  │
      │  pistol FK (SET_NULL) ──► Pistol                                 │
      │  rifle FK (SET_NULL) ──► Rifle                                   │
      │  pistol_magazine FK (SET_NULL) ──► Magazine                      │
      │  rifle_magazine FK (SET_NULL) ──► Magazine                       │
      │  pistol_ammunition FK (SET_NULL) ──► Ammunition                  │
      │  rifle_ammunition FK (SET_NULL) ──► Ammunition                   │
      └──────────────────────────────────────────────────────────────────┘
                             │
                             ▼
                    ┌─────────────────────┐
                    │  TransactionLogs    │
                    │  (transactions)     │
                    └─────────────────────┘

      ┌────────────┐  ┌────────────┐  ┌───────────┐  ┌───────────┐
      │   Pistol   │  │   Rifle    │  │  Magazine │  │ Accessory │
      │ (inventory)│  │ (inventory)│  │(inventory)│  │(inventory)│
      └──────┬─────┘  └──────┬─────┘  └─────┬─────┘  └───────────┘
             │               │              │
             └───────────────┴──────────────┴──► Category (FK SET_NULL)

      ┌─────────────────────┐  ┌────────────────────────┐
      │  Inventory_Analytics│  │   AnalyticsSnapshot    │
      │  (inventory)        │  │   (inventory)          │
      └─────────────────────┘  └────────────────────────┘
```

---

## 2. Table Definitions

### 2.1 `Personnel`
**App:** `armguard.apps.personnel`  
**File:** `armguard/apps/personnel/models.py`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `Personnel_ID` | CharField(50) | PK, unique, auto-generated | Format: `PEP-<AFSN>-<timestamp>` (enlisted) / `POF_O-<AFSN>-<timestamp>` (officer) |
| `rank` | CharField(20) | choices=ALL_RANKS | Enlisted + Officer ranks (PAF) |
| `first_name` | CharField(20) | — | — |
| `last_name` | CharField(20) | — | — |
| `middle_initial` | CharField(1) | — | — |
| `AFSN` | CharField(10) | unique | Air Force Serial Number |
| `group` | CharField(10) | choices: HAS/951st/952nd/953rd | — |
| `squadron` | CharField(20) | — | — |
| `tel` | CharField(11) | unique, nullable, digits-only | Required for TR issuance |
| `personnel_image` | ImageField | upload_to='personnel_images', nullable | — |
| `qr_code` | CharField(100) | unique | QR code data string |
| `qr_code_image` | ImageField | upload_to='qr_code_images_personnel/', nullable | — |
| `created` | DateTimeField | nullable | Set on first save |
| `created_by` | CharField(50) | nullable | Username of creator |
| `updated` | DateTimeField | nullable | Set on each update |
| `updated_by` | CharField(50) | nullable | Username of updater |
| `status` | CharField(10) | choices: Active/Inactive, default=Active | — |
| `user` | OneToOneField → User | SET_NULL, nullable | Links to login account (optional) |
| `duty_type` | CharField(50) | nullable | Optional duty type |
| `rifle_item_assigned` | CharField(100) | nullable | Snapshot of assigned rifle ID |
| `rifle_item_issued` | CharField(100) | nullable | Snapshot of issued rifle ID |
| `pistol_item_assigned` | CharField(100) | nullable | Snapshot of assigned pistol ID |
| `pistol_item_issued` | CharField(100) | nullable | Snapshot of issued pistol ID |
| `pistol_magazine_item_issued` | CharField(100) | nullable | REC-05: split from magazine_item_issued |
| `rifle_magazine_item_issued` | CharField(100) | nullable | REC-05: split from magazine_item_issued |
| `magazine_item_issued` | CharField(100) | nullable | **DEPRECATED** (keep for compat, see RI-05) |
| `ammunition_item_issued` | CharField(100) | nullable | Snaphot of issued ammo |
| `pistol_ammunition_item_issued` | CharField(100) | nullable | REC-06 split |
| `rifle_ammunition_item_issued` | CharField(100) | nullable | REC-06 split |
| `pistol_holster_issued` | CharField(100) | nullable | Accessory snapshot |
| `magazine_pouch_issued` | CharField(100) | nullable | Accessory snapshot |
| `rifle_sling_issued` | CharField(100) | nullable | Accessory snapshot |
| `bandoleer_issued` | CharField(100) | nullable | Accessory snapshot |
| *(plus `_quantity`, `_timestamp`, `_by` suffixes for each issuance field)* | — | nullable | Audit detail per-snapshot |

**Computed Properties (not stored in DB):**

| Method | Returns | Source |
|---|---|---|
| `get_current_pistol()` | Issued pistol snapshot or None | TransactionLogs |
| `get_current_rifle()` | Issued rifle snapshot or None | TransactionLogs |
| `get_current_pistol_magazine()` | Pistol magazine info or None | TransactionLogs |
| `get_current_rifle_magazine()` | Rifle magazine info or None | TransactionLogs |
| `get_current_ammunition()` | All issued ammo | TransactionLogs |
| `get_current_accessories()` | All issued accessories | TransactionLogs |
| `has_any_issued_items()` | Boolean | TransactionLogs |
| `has_pistol_issued()` | Boolean | `pistol_item_issued` field |
| `has_rifle_issued()` | Boolean | `rifle_item_issued` field |

---

### 2.2 `Pistol`
**App:** `armguard.apps.inventory`  
**Inherits from:** `SmallArm` (abstract base)

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `item_id` | CharField(50) | PK, unique, auto-generated | Format: `IP-<model_code>-<serial>` |
| `item_number` | CharField(4) | auto-assigned | Sequential per model |
| `category` | FK → Category | SET_NULL, nullable | — |
| `model` | CharField(30) | choices=PISTOL_MODELS | One of 5 pistol models |
| `serial_number` | CharField(50) | unique | — |
| `serial_image` | ImageField | nullable | Photo of serial plate |
| `qr_code` | CharField(100) | unique | QR data string |
| `qr_code_image` | ImageField | nullable | — |
| `item_tag` | ImageField | nullable | Printable ID tag |
| `description` | TextField | nullable | — |
| `created` | DateTimeField | nullable | — |
| `created_by` | CharField(50) | nullable | — |
| `updated` | DateTimeField | nullable | — |
| `updated_by` | CharField(100) | nullable | — |
| `item_status` | CharField | choices: Available/Issued/Assigned/Maintenance | — |
| `item_assigned_to` | FK → Personnel | SET_NULL, nullable | C1: real FK |
| `item_issued_to` | FK → Personnel | SET_NULL, nullable | — |
| `item_assigned_timestamp` | DateTimeField | nullable | — |
| `item_issued_timestamp` | DateTimeField | nullable | — |

---

### 2.3 `Rifle`
**App:** `armguard.apps.inventory`  
**Inherits from:** `SmallArm` (abstract base)  
**Identical structure to `Pistol`**, with differences:
- `item_id` format: `IR-<model_code>-<serial>` (or `PAF\d+` for factory-QR M4s)
- `model` choices: `RIFLE_MODELS` (5 rifle/carbine models)
- Upload paths: `qr_code_images_rifle/`, `serial_images_rifle/`

---

### 2.4 `Magazine`
**App:** `armguard.apps.inventory`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | AutoField | PK | — |
| `category` | FK → Category | SET_NULL, nullable | C4 fix |
| `weapon_type` | CharField | choices: Pistol/Rifle | Pool type |
| `quantity` | PositiveIntegerField | MinValueValidator(0) | Total in pool |
| `quantity_available` | PositiveIntegerField | MinValueValidator(0) | Available count |
| `description` | TextField | nullable | — |
| `created` | DateTimeField | nullable | — |
| `created_by` | CharField | nullable | — |
| `updated` | DateTimeField | nullable | — |
| `updated_by` | CharField | nullable | — |

**Method:** `adjust_quantity(delta)` — atomic `F() + Greatest(0, ...)` update

---

### 2.5 `Ammunition`
**App:** `armguard.apps.inventory`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | AutoField | PK | — |
| `type` | CharField | choices=AMMUNITION_TYPES | 5 military-designation ammo types |
| `quantity` | PositiveIntegerField | MinValueValidator(0) | Total in pool |
| `quantity_available` | PositiveIntegerField | MinValueValidator(0) | Available count |
| `description` | TextField | nullable | — |
| *(audit fields)* | — | nullable | — |

**Method:** `adjust_quantity(delta)` — atomic `F() + Greatest(0, ...)` update

---

### 2.6 `Accessory`
**App:** `armguard.apps.inventory`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | AutoField | PK | — |
| `accessory_type` | CharField | choices=ACCESSORY_TYPES | Pistol Holster, Magazine Pouch, Rifle Sling, Bandoleer |
| `quantity` | PositiveIntegerField | MinValueValidator(0) | Total in pool |
| `quantity_available` | PositiveIntegerField | MinValueValidator(0) | Available count |
| `description` | TextField | nullable | — |
| *(audit fields)* | — | nullable | — |

---

### 2.7 `Category`
**App:** `armguard.apps.inventory`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | AutoField | PK | — |
| `name` | CharField(50) | unique | e.g., 'Small Arms', 'Ammunition' |
| `description` | TextField | nullable | — |

---

### 2.8 `Transaction`
**App:** `armguard.apps.transactions`  
**File:** `armguard/apps/transactions/models.py`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `transaction_id` | AutoField | PK | — |
| `transaction_type` | CharField(20) | choices: Withdrawal/Return | — |
| `issuance_type` | CharField(100) | choices: PAR/TR, nullable | Document type |
| `purpose` | CharField(100) | not null, default='Others' | Duty type reason (BUG-05 fix) |
| `purpose_other` | CharField(100) | nullable | Custom purpose when 'Others' selected |
| `pistol` | FK → Pistol | SET_NULL, nullable | FIX A: history survives item removal |
| `rifle` | FK → Rifle | SET_NULL, nullable | FIX A |
| `pistol_magazine` | FK → Magazine | SET_NULL, nullable | limit_choices_to weapon_type=Pistol |
| `pistol_magazine_quantity` | PositiveIntegerField | nullable | — |
| `rifle_magazine` | FK → Magazine | SET_NULL, nullable | limit_choices_to weapon_type=Rifle |
| `rifle_magazine_quantity` | PositiveIntegerField | nullable | — |
| `pistol_ammunition` | FK → Ammunition | SET_NULL, nullable | limit_choices_to pistol ammo types |
| `pistol_ammunition_quantity` | PositiveIntegerField | nullable | — |
| `rifle_ammunition` | FK → Ammunition | SET_NULL, nullable | limit_choices_to rifle ammo types |
| `rifle_ammunition_quantity` | PositiveIntegerField | nullable | — |
| `pistol_holster_quantity` | PositiveIntegerField | nullable | max 1 |
| `magazine_pouch_quantity` | PositiveIntegerField | nullable | max 3 |
| `rifle_sling_quantity` | PositiveIntegerField | nullable | max 1 |
| `bandoleer_quantity` | PositiveIntegerField | nullable | max 1 |
| `personnel` | FK → Personnel | **PROTECT** | FIX B: prevents deletion of active personnel |
| `timestamp` | DateTimeField | auto_now_add | Creation time |
| `updated_at` | DateTimeField | auto_now | REC-09: last modification time |
| `transaction_personnel` | CharField(100) | nullable | System user who processed |
| `notes` | TextField | nullable | — |

**Indexes (REC-01, REC-10):**
- `txn_type_ts_idx` — (`transaction_type`, `timestamp`)
- `txn_type_purpose_ts_idx` — (`transaction_type`, `purpose`, `timestamp`)
- `txn_person_type_ts_idx` — (`personnel_id`, `transaction_type`, `timestamp`)

**Custom Permissions (C8):**
- `can_process_withdrawal`
- `can_process_return`
- `can_view_transaction_logs`

---

### 2.9 `TransactionLogs`
**App:** `armguard.apps.transactions`

| Column | Type | Description |
|---|---|---|
| `record_id` | AutoField PK | — |
| `issuance_type` | CharField | Snapshot of Transaction.issuance_type |
| `log_status` | CharField | Open / Partially Returned / Closed |
| `personnel` | FK → Personnel | SET_NULL |
| `withdrawal_pistol_transaction_id` | IntegerField nullable | References Transaction.transaction_id |
| `withdrawal_rifle_transaction_id` | IntegerField nullable | — |
| `withdrawal_pistol_magazine_transaction_id` | IntegerField nullable | — |
| `withdrawal_rifle_magazine_transaction_id` | IntegerField nullable | — |
| `withdrawal_pistol_ammunition_transaction_id` | IntegerField nullable | — |
| `withdrawal_rifle_ammunition_transaction_id` | IntegerField nullable | — |
| `withdrawal_pistol_holster_transaction_id` | IntegerField nullable | — |
| `withdrawal_magazine_pouch_transaction_id` | IntegerField nullable | — |
| `withdrawal_rifle_sling_transaction_id` | IntegerField nullable | — |
| `withdrawal_bandoleer_transaction_id` | IntegerField nullable | — |
| `return_pistol_transaction_id` | IntegerField nullable | — |
| `return_rifle_transaction_id` | IntegerField nullable | — |
| *(+ all return_ variants)* | — | — |
| *(+ quantity, timestamp, by fields for each item type)* | — | BUG-03 fix |
| `created_at` | DateTimeField auto_now_add | — |
| `updated_at` | DateTimeField auto_now | — |

> **Note (REC-08 deferred):** TransactionLogs is a wide table (~125 columns). Normalization into a related schema would be a major migration. Deferred at current scale.

---

### 2.10 `UserProfile`
**App:** `armguard.apps.users`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `user` | OneToOneField → User | CASCADE, PK | Mirror of auth account lifecycle |
| `role` | CharField(30) | choices: System Administrator/Administrator/Armorer, default=Armorer | — |
| `last_session_key` | CharField(40) | nullable, blank | Current active session key; used by `SingleSessionMiddleware` for concurrent-session prevention |

**Auto-creation:** `post_save` signal on `User` creates a `UserProfile` automatically via `get_or_create`.

---

### 2.11 `AuditLog`
**App:** `armguard.apps.users`  
**Migration:** `0002_auditlog_and_session_key`, `0003_auditlog_useragent_hash_deletedrecord`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | BigAutoField | PK | — |
| `user` | FK → User | SET_NULL, nullable | Null if user account was deleted |
| `action` | CharField(20) | choices: CREATE/UPDATE/DELETE/LOGIN/LOGOUT/OTHER | — |
| `model_name` | CharField(100) | blank | Dotted model path (e.g. `armguard.apps.inventory.Pistol`) |
| `object_pk` | CharField(100) | blank | String PK of the affected record |
| `message` | TextField | blank | Human-readable description of the change |
| `ip_address` | GenericIPAddressField | null, blank | Client IP (X-Forwarded-For aware) |
| `user_agent` | CharField(512) | blank | HTTP User-Agent header (truncated at 512 chars) |
| `integrity_hash` | CharField(64) | blank | SHA-256 of `"{ts}|{username}|{action}|{message}"` — auto-computed on write |
| `timestamp` | DateTimeField | auto_now_add=True | Immutable creation time |

**Methods:**
- `compute_hash()` — returns SHA-256 hex string of the canonical fields
- `verify_integrity()` — returns `True` if stored hash matches recomputed hash; detects DB tampering
- `save()` — inserts row first, then updates `integrity_hash` via a second `filter().update()` call to include the auto-assigned PK in the hash input

**Admin:** Fully read-only `AuditLogAdmin` registered; no add/change/delete permissions.

---

### 2.12 `DeletedRecord`
**App:** `armguard.apps.users`  
**Migration:** `0003_auditlog_useragent_hash_deletedrecord`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | BigAutoField | PK | — |
| `model_name` | CharField(100) | — | Dotted model path of the deleted object |
| `object_pk` | CharField(100) | — | String PK of the deleted record |
| `data` | JSONField | — | Full JSON snapshot of the record at deletion time |
| `deleted_by` | FK → User | SET_NULL, nullable | User who performed the deletion |
| `deleted_at` | DateTimeField | auto_now_add=True | Immutable deletion timestamp |

**Purpose:** Written before any hard-delete to provide a queryable archive of deleted records. Enables chain-of-custody audit for removed personnel, weapons, or transactions.

---

### 2.13 `PasswordHistory`
**App:** `armguard.apps.users`  
**Migration:** `0004_passwordhistory`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | BigAutoField | PK | — |
| `user` | FK → User | CASCADE | Owner of the password entry |
| `password_hash` | CharField(255) | — | Django-format hashed password (e.g. `pbkdf2_sha256$...`). Raw password is never stored. |
| `created_at` | DateTimeField | auto_now_add=True | When this password was set |

**Purpose:** `PasswordHistoryValidator` queries the last 5 entries for a user during password change/creation to prevent password reuse. Records are written by `UserCreateView` and `UserUpdateView` whenever a password is saved.

---

### 2.14 `Inventory_Analytics`
**App:** `armguard.apps.inventory`  
**File:** `inventory_analytics_model.py`

Live analytics snapshot upserted on each admin changelist load. Stores per-model/per-type breakdowns of inventory and issuance state.

---

### 2.15 `AnalyticsSnapshot`
**App:** `armguard.apps.inventory`  
**File:** `inventory_analytics_model.py`

Immutable daily historical snapshot (append-only). Used for trend analysis over time.

---

## 3. Migration State

| App | Migration File | Status |
|---|---|---|
| `armguard.apps.inventory` | `0001_initial.py` | ✅ Applied |
| `armguard.apps.personnel` | `0001_initial.py` | ✅ Applied |
| `armguard.apps.transactions` | `0001_initial.py` | ✅ Applied |
| `armguard.apps.transactions` | `0002_add_ammo_return_indexes.py` | ✅ Applied |
| `armguard.apps.transactions` | `0003_sanitize_par_upload.py` | ✅ Applied |
| `armguard.apps.users` | `0001_initial.py` | ✅ Applied |
| `armguard.apps.users` | `0002_auditlog_and_session_key.py` | ✅ Applied |
| `armguard.apps.users` | `0003_auditlog_useragent_hash_deletedrecord.py` | ✅ Applied |
| `armguard.apps.users` | `0004_passwordhistory.py` | ✅ Applied |
| `otp_totp` | 3 migrations | ✅ Applied |
| `otp_static` | 3 migrations | ✅ Applied |
| `rest_framework.authtoken` | 1 migration | ✅ Applied |
| `django.contrib.auth` | (built-in) | ✅ Applied |
| `django.contrib.admin` | (built-in) | ✅ Applied |
| `django.contrib.contenttypes` | (built-in) | ✅ Applied |
| `django.contrib.sessions` | (built-in) | ✅ Applied |

### Migration Detail

| Migration | Description |
|---|---|
| `transactions/0002_add_ammo_return_indexes` | Adds 2 compound indexes on `TransactionLogs` for ammo-return queries |
| `transactions/0003_sanitize_par_upload` | Changes `Transaction.par_document` `upload_to` from string to `_sanitize_par_upload` callable |
| `users/0002_auditlog_and_session_key` | Creates `AuditLog` model; adds `last_session_key` to `UserProfile` |
| `users/0003_auditlog_useragent_hash_deletedrecord` | Adds `user_agent` + `integrity_hash` to `AuditLog`; creates `DeletedRecord` model |
| `users/0004_passwordhistory` | Creates `PasswordHistory` model for password-reuse prevention |

---

## 4. Key Business Rules (Enforced at Model Level)

### 4.1 Withdrawal Rules
| Rule | Enforcement |
|---|---|
| Pistol: personnel may not have two pistols issued | `clean()` checks `personnel.has_pistol_issued()` |
| Rifle: same restriction | `clean()` checks `personnel.has_rifle_issued()` |
| Magazine: withdrawal qty ≤ pool quantity_available | `clean()` queries Magazine.quantity_available |
| Ammunition: withdrawal qty ≤ pool quantity_available | `clean()` queries Ammunition.quantity_available |
| Holster: max 1 per transaction | `clean()` enforces ≤1 |
| Magazine pouch: max 3 per transaction | `clean()` enforces ≤3 |
| Rifle sling: max 1 per transaction | `clean()` enforces ≤1 |
| Bandoleer: max 1 per transaction | `clean()` enforces ≤1 |
| At least one item required | `clean()` raises ValidationError if no items |
| Personnel required | `clean()` raises ValidationError if no personnel |

### 4.2 Return Rules
| Rule | Enforcement |
|---|---|
| Matching open withdrawal must exist | `clean()` queries TransactionLogs for Open/Partially Returned log |
| Return qty ≤ original withdrawal qty | `clean()` computes delta against log |
| Ammunition caliber ↔ weapon compatibility | `AMMO_WEAPON_COMPATIBILITY` dict in `clean()` |

### 4.3 Referential Integrity Rules
| Rule | Mechanism |
|---|---|
| Personnel with transactions cannot be deleted | `Transaction.personnel = FK(PROTECT)` |
| Item removal does not delete transaction history | All item FKs use `SET_NULL` |
| User account deletion does not delete Personnel record | `Personnel.user = SET_NULL` |
| User account deletion removes UserProfile | `UserProfile.user = CASCADE` |

---

## 5. Known Deferred Schema Issues

| ID | Issue | Impact | Plan |
|---|---|---|---|
| RI-01 | Personnel CharFields can become stale if items are deleted directly (outside Transaction flow) | Medium | Mitigated by computed properties; acceptable at managed scale |
| RI-05 | Deprecated `magazine_item_issued` fields still present on Personnel | Low | Data-migrate to `pistol_magazine_item_issued` / `rifle_magazine_item_issued`, then drop |
| REC-08 | TransactionLogs is a 125-column wide table (denormalized) | Medium | Normalize into related rows for v2 |
