# ARMGUARD RDS — Full Application Review
**Date:** April 10, 2026

---

## Summary by Priority

| Priority | Count | Categories |
|----------|-------|------------|
| CRITICAL | 1 | Security |
| HIGH | 4 | Security, Performance |
| MEDIUM | 12 | Security, Data Integrity, Performance, Missing Features |
| LOW | 8 | UX, Code Quality, Dead Code |

---

## 1. Security

### 1.1 Missing Permission Check on PersonnelCardPreviewView ⚠️ CRITICAL
- **File:** `armguard/apps/personnel/views.py:233`
- **Issue:** `PersonnelCardPreviewView` uses `LoginRequiredMixin` only — no `test_func` permission check. Any logged-in user can generate ID card previews (rank, name, AFSN, photo) for any personnel record.
- **Fix:** Add `UserPassesTestMixin` with `test_func()` calling `can_view_personnel(request.user)`.

### 1.2 PersonnelImportView Bypasses Fine-Grained Permissions — HIGH
- **File:** `armguard/apps/personnel/views.py:417`
- **Issue:** `test_func()` checks `is_superuser` only. Bulk personnel creation bypasses the `perm_personnel_add` permission flag.
- **Fix:** Add `or can_add_personnel(self.request.user)` to the `test_func` check.

### 1.3 File Upload Validation Missing in Card Preview — HIGH
- **File:** `armguard/apps/personnel/views.py:261`
- **Issue:** Uploaded photo saved with no extension whitelist, no size limit, and no filename sanitization. The `photo_file.name` used directly to construct temp path.
- **Fix:** Validate extensions against `{'.jpg', '.jpeg', '.png'}`, enforce max 5 MB, use `uuid4()` for temp filenames.

### 1.4 Broad Exception Catch in Camera Views — MEDIUM
- **File:** `armguard/apps/camera/views.py:401`
- **Issue:** `except (ValueError, Exception)` catches `SystemExit`, `KeyboardInterrupt`, etc. Device lockout tracking bypassed on unexpected errors.
- **Fix:** Catch specific exceptions: `ValueError`, `IOError`, `UnicodeDecodeError` only.

### 1.5 No Rate Limiting on API Endpoints — MEDIUM
- **File:** `armguard/apps/api/views.py:37`
- **Issue:** `_ReadOnlyModelViewSet`, `PersonnelViewSet`, and `TransactionViewSet` have no `throttle_classes`. Sensitive PII and operational data exposed to brute-force scraping.
- **Fix:** Add `throttle_classes = [AnonRateThrottle]` with appropriate rates (e.g., 100 req/hour).

### 1.6 created_by / updated_by as CharField Instead of ForeignKey — MEDIUM
- **File:** `armguard/apps/inventory/models.py:205`
- **Issue:** Pistol, Rifle, Magazine, Ammunition, Accessory models store `created_by`/`updated_by` as plain text. No referential integrity — deleted users leave orphaned audit strings.
- **Fix:** Migrate to `ForeignKey(User, on_delete=models.SET_NULL, null=True)`.

---

## 2. Performance

### 2.1 Dashboard Loads Full Tables Into Memory — HIGH
- **File:** `armguard/apps/dashboard/views.py:88`
- **Issue:** `_build_inventory_table()` calls `.all()` on Pistol, Rifle, and Transaction without limits, loading every row into Python RAM just to compute aggregates.
- **Fix:** Replace with DB-level aggregation: `Pistol.objects.values('model').annotate(count=Count('id'), ...)`.

### 2.2 TransactionListView — Per-Row Subquery Annotations — HIGH
- **File:** `armguard/apps/transactions/views.py:56`
- **Issue:** Multiple nested `Subquery` annotations (`_prior_withdrawal_issuance`, `_rifle_returned_ts`, etc.) trigger one subquery per row. 100 transactions = 100+ queries.
- **Fix:** Denormalize `issuance_type` to the Return model or use a single JOIN-based annotation.

### 2.3 No Pagination on Magazine / Ammunition / Accessory Lists — MEDIUM
- **File:** `armguard/apps/inventory/views.py`
- **Issue:** `MagazineListView`, `AmmunitionListView`, `AccessoryListView` have no `paginate_by`. Large armouries render entire tables in one response.
- **Fix:** Add `paginate_by = 25` to all three ListView subclasses and add pagination controls to their templates.

### 2.4 N+1 Queries in TransactionDetailView — MEDIUM
- **File:** `armguard/apps/transactions/views.py:185`
- **Issue:** Multiple conditional FK queries inside `get_context_data()` without `prefetch_related`. Each related TransactionLog field triggers a separate DB hit.
- **Fix:** Use `prefetch_related` with `Prefetch` objects to control depth on TransactionLogs.

---

## 3. Data Integrity

### 3.1 No Audit Trail for Permission Changes — MEDIUM
- **File:** `armguard/apps/users/views.py:234`
- **Issue:** `UserProfileUpdateView` sets `perm_inventory_view`, `perm_personnel_add`, etc. without logging who changed what permission and when.
- **Fix:** Write an `AuditLog` record (user, timestamp, field, old_value, new_value) on every permission change.

### 3.2 Personnel.created / .updated Allow NULL — MEDIUM
- **File:** `armguard/apps/personnel/models.py:83`
- **Issue:** created/updated timestamps have `null=True` — old records may have no creation date, making audit trail incomplete.
- **Fix:** Add data migration to backfill NULLs with a sentinel date, then set `null=False`.

### 3.3 SET_NULL on Assigned Items with No Guard — MEDIUM
- **File:** `armguard/apps/inventory/models.py:217`
- **Issue:** `Pistol.item_assigned_to` uses `on_delete=SET_NULL`. Deleting a Personnel record silently orphans their assigned weapons with no audit log and no admin warning.
- **Fix:** Override `PersonnelDeleteView` to reject deletion if items are currently assigned/issued.

---

## 4. Missing Features

### 4.1 No Bulk CSV / Excel Export for Transactions
- **Scope:** `armguard/apps/transactions/views.py`
- **Issue:** TransactionListView has filtered pagination but no export. Users cannot get all filtered results for fiscal reconciliation without manual manipulation.
- **Fix:** Add "Export CSV" button that applies active filters and streams a `text/csv` response.

### 4.2 No Scheduled Overdue-Returns Email Report
- **Issue:** Dashboard shows overdue counts but no automated daily alert to admin. Overdue weapons may go unnoticed.
- **Fix:** Add a Celery beat task to email a daily overdue-returns summary to all System Administrator accounts.

### 4.3 Discrepancy Workflow Has No Status Lifecycle
- **Issue:** Firearm discrepancies are logged but never formally resolved. The report list becomes noise with no Reported → Under Review → Resolved flow.
- **Fix:** Add `status` field to `FirearmDiscrepancy`; add approval/rejection actions to the discrepancy detail view.

### 4.4 Bulk Item Tag Printing Not Supported
- **File:** `armguard/apps/print/views.py:71`
- **Issue:** Generating item tags for 50 new M4s requires 50 separate PDF downloads.
- **Fix:** Add batch mode — "Generate all tags for model X" output as one multi-page PDF.

### 4.5 API TransactionViewSet Has No Filtering
- **File:** `armguard/apps/api/views.py:65`
- **Issue:** Returns all transactions with no filter params. External integrations must download the entire table to find one record.
- **Fix:** Add `django-filter` FilterSet exposing `personnel__Personnel_ID`, `transaction_type`, `timestamp__gte/lte`.

---

## 5. Error Handling

### 5.1 Bare `except Exception` Without Logging
- **Files:**
  - `armguard/apps/camera/permissions.py:69`
  - `armguard/apps/transactions/signals.py:50`
  - `armguard/apps/print/views.py:232`
- **Issue:** Exceptions caught and swallowed with no `logger.exception()` call. Silent failures complicate debugging; security incidents go unrecorded.
- **Fix:** Replace `except Exception: pass` with `except Exception: logger.exception("context message")`.

### 5.2 OSError Swallowed Silently in File Operations
- **Files:**
  - `armguard/apps/personnel/models.py:745`
  - `armguard/apps/camera/views.py:748`
- **Issue:** `except OSError: pass` hides disk-full or permission-denied errors.
- **Fix:** Log at `WARNING` level: `logger.warning("Failed to delete file %s", path, exc_info=True)`.

### 5.3 Missing PDF Template Not Reported Clearly
- **File:** `armguard/apps/print/pdf_filler/form_filler.py:67`
- **Issue:** If a PDF template file is missing at runtime, the user sees a generic 500 error with no detail.
- **Fix:** Add a startup check that logs `ERROR: PDF template not found at [path]` with an actionable message.

---

## 6. UX / UI Gaps

| Issue | Location | Fix |
|-------|----------|-----|
| No loading spinner during AJAX card preview | `templates/personnel/personnel_form.html` | Show spinner between field change and updated preview |
| No error message when card preview fails | `apps/personnel/views.py:238` | Return `{"error": "..."}` JSON with 400 status |
| `item_number` validation only shows on POST | `apps/inventory/forms.py:30` | Add `help_text` with constraint description for immediate guidance |

---

## 7. Dead / Unreachable Code

### 7.1 Deprecated Magazine Fields on Personnel Model
- **File:** `armguard/apps/personnel/models.py:108`
- **Issue:** `magazine_item_issued`, `magazine_item_issued_quantity` marked deprecated in comments but never removed. Four fields bloating the schema.
- **Fix:** Plan removal migration after confirming all data is in per-weapon fields.

### 7.2 RifleAdminForm Defined But Not Used in UI
- **File:** `armguard/apps/inventory/forms.py:54`
- **Issue:** `RifleAdminForm` only referenced in Django admin, while `RifleForm` is used everywhere in the UI. Duplication likely unintentional.
- **Fix:** Remove `RifleAdminForm` or consolidate into `RifleForm`.

---

## 8. Code Duplication

### 8.1 QR Generation Logic Duplicated in Pistol and Rifle
- **File:** `armguard/apps/inventory/models.py`
- **Issue:** `Pistol.save()` and `Rifle.save()` contain nearly identical QR code generation code.
- **Fix:** Extract to `SmallArm.generate_qr()` method on the abstract base class.

### 8.2 `os.unlink` Try/Except Pattern Repeated in 3+ Files
- **Files:** `personnel/models.py:745`, `camera/views.py:745`, `print/views.py:515`
- **Issue:** Same `try: os.unlink(path) / except OSError: pass` pattern duplicated. The `_remove_file()` utility already exists in `signals.py` but isn't reused here.
- **Fix:** Move `_remove_file()` to `armguard/utils/files.py` and import from all three sites.

### 8.3 Manual Permission Checks Instead of Using Helpers
- **Files:** `apps/inventory/views.py:30`, `apps/print/views.py:153`, `apps/transactions/views.py:14`
- **Issue:** Some views check permissions inline instead of using the `armguard.utils.permissions` helpers introduced by H1 FIX.
- **Fix:** Replace all inline role/flag checks with the appropriate `can_X(user)` helper.

---

## Recommended Fix Order

1. **`PersonnelCardPreviewView` permission check** — 5-line fix, CRITICAL security gap
2. **Dashboard aggregate queries** — eliminates full table RAM loads
3. **`paginate_by` on Magazine / Ammunition / Accessory lists** — quick win, high user impact
4. **`logger.exception()` on all bare excepts** — improves debuggability across the app
5. **File upload validation** in card preview — closes DoS / traversal risk
6. **CSV export for Transactions** — most-requested missing feature in armory systems
7. **Discrepancy status lifecycle** — makes the discrepancy module actionable
8. **API rate limiting** — one-line addition per ViewSet
