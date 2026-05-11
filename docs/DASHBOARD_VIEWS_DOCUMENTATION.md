# Dashboard Views — Developer Documentation

**File:** `project/armguard/apps/dashboard/views.py`
**Module:** `armguard.apps.dashboard`
**Last reviewed:** 2026-05-09

---

## Table of Contents

1. [Overview](#1-overview)
2. [Module-Level Constants](#2-module-level-constants)
3. [Private Table-Builder Functions](#3-private-table-builder-functions)
   - [_build_inventory_table()](#31-_build_inventory_table)
   - [_build_ammo_table()](#32-_build_ammo_table)
   - [_build_magazine_table()](#33-_build_magazine_table)
   - [_build_accessory_table()](#34-_build_accessory_table)
4. [Public View Functions](#4-public-view-functions)
   - [dashboard_view](#41-dashboard_view)
   - [download_ssl_cert](#42-download_ssl_cert)
   - [ssl_cert_status](#43-ssl_cert_status)
   - [dashboard_cards_json](#44-dashboard_cards_json)
   - [dashboard_tables_json](#45-dashboard_tables_json)
   - [issued_stats_json](#46-issued_stats_json)
5. [Caching Architecture](#5-caching-architecture)
6. [URL Routing](#6-url-routing)
7. [Data Flow Diagram](#7-data-flow-diagram)
8. [Query Optimisation Notes](#8-query-optimisation-notes)
9. [Security Notes](#9-security-notes)

---

## 1. Overview

`dashboard/views.py` is the data-aggregation and rendering layer for the ArmGuard RDS main dashboard. It provides:

- **One full-page HTML view** (`dashboard_view`) that renders stat cards and analytics tables on the initial page load.
- **Three JSON polling endpoints** (`dashboard_cards_json`, `dashboard_tables_json`, `issued_stats_json`) consumed by front-end JavaScript for live updates without full-page reloads.
- **Two public utility endpoints** (`download_ssl_cert`, `ssl_cert_status`) that allow LAN users to install the server's self-signed TLS certificate.
- **Four private helper functions** (`_build_inventory_table`, `_build_ammo_table`, `_build_magazine_table`, `_build_accessory_table`) that build per-type analytics table data using optimised aggregate queries.

All authenticated views require `@login_required` **and** the `can_view_inventory` permission. Unauthenticated requests are redirected to `/accounts/login/`. Users without inventory view permission receive HTTP 403.

---

## 2. Module-Level Constants

These constants are defined at the top of the module and shared across all helper functions. They do **not** change at runtime.

### `_NOMENCLATURE` — `dict[str, str]`

Maps the internal firearm `model` string (as stored in the `Pistol` / `Rifle` models) to its official Philippine Air Force nomenclature display label.

| Key (model string) | Value (display label) |
|---|---|
| `'Glock 17 9mm'` | `'Pistol, 9mm: Glock 17'` |
| `'M1911 Cal.45'` | `'Pistol, Cal.45: M1911'` |
| `'Armscor Hi Cap Cal.45'` | `'Pistol, Cal.45: Hi Cap (Armscor)'` |
| `'RIA Hi Cap Cal.45'` | `'Pistol, Cal.45: Hi Cap (RIA)'` |
| `'M1911 Customized Cal.45'` | `'Pistol, Cal.45: M1911 (Customized)'` |
| `'M4 Carbine DSAR-15 5.56mm'` | `'Carbine, 5.56mm: M4 (DSAR-15)'` |
| `'M4 14.5" DGIS EMTAN 5.56mm'` | `'Carbine, 5.56mm: M4 14.5" (EMTAN)'` |
| `'M16A1 Rifle 5.56mm'` | `'Rifle, 5.56mm: M16'` |
| `'M14 Rifle 7.62mm'` | `'Rifle, 7.62mm: M14'` |
| `'M653 Carbine 5.56mm'` | `'Carbine, 5.56mm: M653'` |

### `_MODEL_ORDER` — `list[str]`

Defines the fixed display order of firearm models in the inventory analytics table. Rifles/carbines are listed first, then pistols — matching the standard PAF armory register order.

```
M4 Carbine DSAR-15 5.56mm
M4 14.5" DGIS EMTAN 5.56mm
M653 Carbine 5.56mm
Glock 17 9mm
Armscor Hi Cap Cal.45
RIA Hi Cap Cal.45
M1911 Cal.45
M1911 Customized Cal.45
M16A1 Rifle 5.56mm
M14 Rifle 7.62mm
```

### `_AMMO_NOMENCLATURE` — `dict[str, str]`

Maps `Ammunition.type` values to official nomenclature display labels for the ammunition analytics table.

| Key (ammo type) | Value (display label) |
|---|---|
| `'M193 5.56mm Ball 428 Ctg'` | `'(428) Ctg, 5.56mm: Ball, M193'` |
| `'M855 5.56mm Ball 429 Ctg'` | `'(429) Ctg, 5.56mm: Ball, M855'` |
| `'M80 7.62x51mm Ball 431 Ctg'` | `'(431) Ctg, 7.62x51mm: Ball, M80'` |
| `'M882 9x19mm Ball 435 Ctg'` | `'(435) Ctg, 9x19mm: Ball, M882'` |
| `'Cal.45 Ball 433 Ctg'` | `'(433) Ctg, Cal.45: Ball'` |

### `_AMMO_ORDER` — `list[str]`

Fixed display order for ammunition rows. Rifle calibres are listed before pistol calibres.

```
M193 5.56mm Ball 428 Ctg
M855 5.56mm Ball 429 Ctg
M80 7.62x51mm Ball 431 Ctg
M882 9x19mm Ball 435 Ctg
Cal.45 Ball 433 Ctg
```

### `_PISTOL_AMMO_TYPES` — `set[str]`

Set of ammo types classified as pistol ammunition. Used in `_build_ammo_table()` to separate pistol and rifle `TransactionLogs` queries.

```python
_PISTOL_AMMO_TYPES = {'Cal.45 Ball 433 Ctg', 'M882 9x19mm Ball 435 Ctg'}
```

---

## 3. Private Table-Builder Functions

All four builder functions follow the same pattern:
1. Execute optimised aggregate queries against the database.
2. Build a list of `dict` row objects with standard field names.
3. Build a `totals` dict summing all numeric columns.
4. Return `(rows, totals)`.

They are called by `dashboard_view()` and `dashboard_tables_json()` and their results are written to the `'dashboard_inventory_tables'` cache key.

---

### 3.1 `_build_inventory_table()`

**Returns:** `(rows: list[dict], totals: dict)`

Builds the small-arms (Pistol + Rifle) accountability table.

#### Query Strategy

Uses **2 grouped aggregate queries** (one for `Pistol`, one for `Rifle`), keyed by `model`, instead of 10 individual per-model queries.

```python
_AGG_FIELDS = dict(
    possessed     = Count('item_id'),
    on_stock      = Count(..., filter=Q(item_status__in=('Available', 'Under Maintenance', 'For Turn In'))),
    issued        = Count(..., filter=Q(item_status='Issued')),
    serviceable   = Count(..., filter=Q(item_condition='Serviceable')),
    unserviceable = Count(..., filter=Q(item_condition='Unserviceable')),
    lost          = Count(..., filter=Q(item_condition='Lost')),
    tampered      = Count(..., filter=Q(item_condition='Tampered')),
)
```

PAR/TR issuance split uses a `Subquery` annotation on the `Pistol`/`Rifle` queryset to fetch the `issuance_type` from the most recent `Transaction` for each item, then accumulates counts in Python using `collections.defaultdict`.

#### Row Dict Fields

| Field | Type | Description |
|---|---|---|
| `nomenclature` | `str` | Display label from `_NOMENCLATURE` |
| `item_type` | `str` | `'pistol'` or `'rifle'` |
| `model` | `str` | Raw model string |
| `list_url` | `str` | URL to inventory list filtered by this model |
| `possessed` | `int` | Total units in the armory (all statuses) |
| `on_stock` | `int` | Units with status Available, Under Maintenance, or For Turn In |
| `issued` | `int` | Units with status Issued |
| `issued_par` | `int` | Issued units under PAR issuance type |
| `issued_tr` | `int` | Issued units under TR issuance type |
| `serviceable` | `int` | Units with condition Serviceable |
| `unserviceable` | `int` | Units with condition Unserviceable |
| `lost` | `int` | Units with condition Lost |
| `tampered` | `int` | Units with condition Tampered |

#### Totals Dict Keys

Same as row fields (all numeric): `possessed`, `on_stock`, `issued`, `issued_par`, `issued_tr`, `serviceable`, `unserviceable`, `lost`, `tampered`.

---

### 3.2 `_build_ammo_table()`

**Returns:** `(rows: list[dict], totals: dict)`

Builds the ammunition accountability table showing on-hand quantities and issued quantities per ammo type.

#### Query Strategy

- **1 aggregate query** on `Ammunition` grouped by `type` → `on_hand` per type.
- **1 query** on open `TransactionLogs` for pistol ammo types.
- **1 query** on open `TransactionLogs` for rifle ammo types.

Total: 3 DB queries instead of the previous 10+.

`open_statuses = ('Open', 'Partially Returned')` — only logs where issued items have not been fully returned are counted as "issued".

Issued quantity per type is: `max(withdraw_quantity - return_quantity, 0)` (net issued, never negative).

#### Row Dict Fields

| Field | Type | Description |
|---|---|---|
| `nomenclature` | `str` | Display label from `_AMMO_NOMENCLATURE` |
| `ammo_type` | `str` | Raw `Ammunition.type` string |
| `basic_load` | `int` | `on_hand + issued` (total accounted quantity) |
| `issued` | `int` | Net issued quantity (all open logs) |
| `issued_par` | `int` | Net issued under PAR issuance type |
| `issued_tr` | `int` | Net issued under TR issuance type |
| `unserviceable` | `int` | Always `0` — not tracked at this level |
| `serviceable` | `int` | Equal to `on_hand` |
| `on_hand` | `int` | Current on-hand inventory quantity |
| `lost` | `int` | Always `0` — not tracked at this level |
| `list_url` | `str` | URL to the ammunition list page |

#### Totals Dict Keys

`basic_load`, `issued`, `issued_par`, `issued_tr`, `unserviceable`, `serviceable`, `on_hand`, `lost`.

---

### 3.3 `_build_magazine_table()`

**Returns:** `(rows: list[dict], totals: dict)`

Builds the magazine accountability table for all 8 magazine types (4 pistol + 4 rifle).

#### Query Strategy

Uses a **single conditional aggregate** inner function `_mag_agg(qs_filter)` that computes withdraw/return quantities for all 8 magazine types in one DB round-trip, using Django's `Sum(..., filter=Q(...))` conditional aggregation.

Called three times with different `qs_filter` arguments:
- `_mag_agg({})` → totals (all issuance types)
- `_mag_agg({'issuance_type': _PAR})` → PAR-only
- `_mag_agg({'issuance_type': _TR})` → TR-only

Net issued per type: `max(withdraw_quantity - return_quantity, 0)`.

On-stock quantities are obtained with a single `Magazine.objects.values('type', 'capacity').annotate(total=Sum('quantity'))` query.

#### Magazine Types Covered

| Internal Key | Label | Nomenclature |
|---|---|---|
| `Pistol-9mm` | Pistol | `Mag Assy, 9mm: Glock 17` |
| `Pistol-45-7` | Pistol | `Mag Assy, Cal.45: 7 rds Cap` |
| `Pistol-45-8` | Pistol | `Mag Assy, Cal.45: 8 rds Cap` |
| `Pistol-45-hi` | Pistol | `Mag Assy, Cal.45: Hi Cap` |
| `Rifle-20` | Rifle | `Mag Assy, 5.56mm: 20 rds Cap Alloy` |
| `Rifle-30` | Rifle | `Mag Assy, 5.56mm: 30 rds Cap Alloy` |
| `Rifle-M14` | Rifle | `Mag Assy, 7.62mm: M14` |
| `Rifle-EMTAN` | Rifle | `Mag Assy, 5.56mm: EMTAN` |

> **Note on rifle magazine aggregation:** Rifle magazines are aggregated by `capacity` value (`'20-rounds'`, `'30-rounds'`, `'M14'`, `'EMTAN'`), not by type string, because `TransactionLogs` stores the FK-linked object and its capacity is the most reliable discriminator.

#### Row Dict Fields

| Field | Type | Description |
|---|---|---|
| `label` | `str` | `'Pistol'` or `'Rifle'` |
| `nomenclature` | `str` | Full magazine type name |
| `type` | `str` | Internal type key (e.g., `'Pistol-9mm'`) |
| `on_stock` | `int` | Current on-hand quantity |
| `issued` | `int` | Net issued (total, all issuance types) |
| `issued_par` | `int` | Net issued under PAR |
| `issued_tr` | `int` | Net issued under TR |
| `list_url` | `str` | URL to the magazine list page |

#### Totals Dict Keys

`on_stock`, `issued`, `issued_par`, `issued_tr`.

---

### 3.4 `_build_accessory_table()`

**Returns:** `(rows: list[dict], totals: dict)`

Builds the accessories accountability table for the 4 accessory types.

#### Query Strategy

Uses one conditional aggregate inner function `_build_acc_agg(extra_filter)` that computes withdraw/return quantities for all 4 accessory types in one DB round-trip, called three times (total, PAR, TR).

On-stock: single `Accessory.objects.values('type').annotate(total=Sum('quantity'))` query.

#### Accessory Types Covered

| Type Key | Label | Nomenclature |
|---|---|---|
| `Pistol Holster` | Pistol | `Pistol Holster` |
| `Pistol Magazine Pouch` | Pistol | `Pistol Magazine Pouch` |
| `Rifle Sling` | Rifle | `Rifle Sling` |
| `Bandoleer` | Rifle | `Bandoleer` |

#### Row Dict Fields

| Field | Type | Description |
|---|---|---|
| `label` | `str` | `'Pistol'` or `'Rifle'` |
| `nomenclature` | `str` | Accessory type name |
| `type` | `str` | `Accessory.type` string |
| `on_stock` | `int` | Current on-hand quantity |
| `issued` | `int` | Net issued (all issuance types) |
| `issued_par` | `int` | Net issued under PAR |
| `issued_tr` | `int` | Net issued under TR |
| `list_url` | `str` | URL to the accessory list page |

#### Totals Dict Keys

`on_stock`, `issued`, `issued_par`, `issued_tr`.

---

## 4. Public View Functions

### 4.1 `dashboard_view`

```python
@login_required
def dashboard_view(request):
```

**URL:** `GET /dashboard/`
**Template:** `dashboard/dashboard.html`
**Auth:** `@login_required` + `can_view_inventory` check (returns HTTP 403 on failure)

#### Purpose

Renders the full dashboard HTML page on first load. Provides all stat card values and all analytics table data to the template context.

#### Execution Flow

1. **Permission check** — calls `_can_view_inv(request.user)`; returns `HttpResponseForbidden` if denied.
2. **Stats cache check** — looks up `'dashboard_stats_{today}'` in Django cache.
   - **Cache miss:** executes 6 aggregate DB queries (personnel, pistol, rifle, magazine, transaction, transaction-logs) and stores result for **60 seconds**.
   - **Cache hit:** uses stored dict directly.
3. **Inventory tables cache check** — looks up `'dashboard_inventory_tables'`.
   - **Cache miss:** calls all four `_build_*_table()` helpers and stores result for **30 seconds**.
   - **Cache hit:** uses stored dict directly.
4. Merges stats and tables into a single `context` dict and calls `render()`.

#### Context Variables Passed to Template

**Personnel stats:**

| Variable | Type | Description |
|---|---|---|
| `total_personnel` | `int` | Total active personnel count |
| `inactive_personnel` | `int` | Inactive personnel count |
| `officers_count` | `int` | Active officers (by rank) |
| `enlisted_count` | `int` | Active enlisted (active − officers) |

**Firearm stats:**

| Variable | Type | Description |
|---|---|---|
| `total_pistols` | `int` | Total pistol units |
| `pistols_available` | `int` | Pistols with status Available |
| `pistols_issued` | `int` | Pistols with status Issued |
| `total_rifles` | `int` | Total rifle units |
| `rifles_available` | `int` | Rifles with status Available |
| `rifles_issued` | `int` | Rifles with status Issued |

**Magazine stats:**

| Variable | Type | Description |
|---|---|---|
| `total_magazine_qty` | `int` | Total magazine units (all types) |
| `short_magazine_available` | `int` | 20-round rifle mags on-hand |
| `long_magazine_available` | `int` | 30-round and EMTAN rifle mags on-hand |
| `short_magazine_issued` | `int` | 20-round rifle mags currently issued (net) |
| `long_magazine_issued` | `int` | 30-round/EMTAN rifle mags currently issued (net) |

**Ammunition stats:**

| Variable | Type | Description |
|---|---|---|
| `total_ammo_qty` | `int` | Total ammunition rounds on-hand |

**Transaction stats:**

| Variable | Type | Description |
|---|---|---|
| `total_transactions` | `int` | All-time transaction count |
| `total_transactions_today` | `int` | Withdrawals + returns today |
| `withdrawals_today` | `int` | Withdrawal transactions today |
| `returns_today` | `int` | Return transactions today |
| `issued_TR` | `int` | Firearms currently issued under TR |
| `issued_PAR` | `int` | Firearms currently issued under PAR |
| `total_issued` | `int` | `issued_TR + issued_PAR` |

**Analytics table data:**

| Variable | Type | Description |
|---|---|---|
| `inventory_rows` | `list[dict]` | Small-arms rows (see §3.1) |
| `inventory_totals` | `dict` | Small-arms column totals |
| `ammo_rows` | `list[dict]` | Ammunition rows (see §3.2) |
| `ammo_totals` | `dict` | Ammunition column totals |
| `magazine_rows` | `list[dict]` | Magazine rows (see §3.3) |
| `magazine_totals` | `dict` | Magazine column totals |
| `accessory_rows` | `list[dict]` | Accessory rows (see §3.4) |
| `accessory_totals` | `dict` | Accessory column totals |

---

### 4.2 `download_ssl_cert`

```python
def download_ssl_cert(request):
```

**URL:** `GET /download/ssl-cert/`
**Auth:** None (public endpoint)
**Returns:** `FileResponse` — the server's self-signed TLS certificate as a `.crt` file download.

#### Purpose

Serves the server's self-signed SSL certificate so LAN users can install it on their devices without needing to navigate the browser's certificate export flow. The certificate path is read from `settings.SSL_CERT_PATH` (configured via `SSL_CERT_PATH` env var in production settings; defaults to `/etc/ssl/certs/armguard-selfsigned.crt`).

#### Behaviour

- If the cert file does not exist at `settings.SSL_CERT_PATH`, raises `Http404`.
- Otherwise streams the file with:
  - `Content-Type: application/x-x509-ca-cert`
  - `Content-Disposition: attachment; filename="armguard-selfsigned.crt"`

#### Installation Instructions (embedded in docstring)

| Platform | Steps |
|---|---|
| Android | Settings → Security → Install from storage → CA certificate |
| Windows | Open `.crt` → Install Certificate → Trusted Root CA |
| iOS | Download → Settings → Profile Downloaded → Install |

#### Security Note

The certificate is public information — it is transmitted in every TLS handshake. Making it downloadable via the app does not expose any private key material. No authentication is required intentionally, because the user may need to install the certificate before they can authenticate over HTTPS.

---

### 4.3 `ssl_cert_status`

```python
def ssl_cert_status(request):
```

**URL:** `GET /download/ssl-cert-status/`
**Auth:** None (public endpoint)
**Returns:** `JsonResponse`

#### Purpose

Returns the modification time (`mtime`) of the SSL certificate file. The front-end stores a localStorage acknowledgment (`certMtimeAck`) and compares it to this value to decide whether to show the certificate install banner.

#### Response Format

```json
{ "cert_mtime": 1746789000.123 }
```

Returns `{"cert_mtime": 0.0}` when no certificate file exists.

#### Design

No sensitive data is exposed. The `mtime` is a float (Unix timestamp) sufficient for the client-side comparison. No authentication is required for the same reason as `download_ssl_cert`.

---

### 4.4 `dashboard_cards_json`

```python
@login_required
def dashboard_cards_json(request):
```

**URL:** `GET /dashboard/cards-stats/`
**Auth:** `@login_required` + `can_view_inventory`
**Returns:** `JsonResponse`
**Cache:** `'dashboard_cards_{today}'` — **10 seconds**

#### Purpose

Live-polling endpoint for the four dashboard stat cards (Personnel, Firearms, Transactions Today, Issued Firearms). Polled every 10 seconds by `static/js/dashboard_cards.js`.

The 10-second cache TTL matches the JS poll interval so the database is hit at most once per 10-second window, regardless of how many tabs or workers are open.

Cache invalidation: `create_transaction()` in `transactions/views.py` calls `cache.delete('dashboard_cards_{today}')` immediately after saving a new transaction, ensuring the stat cards reflect the latest state within one poll cycle.

#### Response JSON Fields

```json
{
    "total_personnel":          120,
    "officers_count":           25,
    "enlisted_count":           95,
    "total_magazine_qty":       340,
    "short_magazine_available": 48,
    "long_magazine_available":  72,
    "short_magazine_issued":    12,
    "long_magazine_issued":     8,
    "issued_TR":                35,
    "issued_PAR":               10,
    "total_issued":             45,
    "total_transactions_today": 18,
    "withdrawals_today":        10,
    "returns_today":            8
}
```

> **Note:** Pistol and rifle counts are **not** included in this endpoint's response because the dashboard Firearms card is populated directly from `total_pistols` / `total_rifles` etc., which are provided by the initial `dashboard_view` template render and updated by this endpoint. The JS in `dashboard_cards.js` computes the Firearms card total as `d.total_pistols + d.total_rifles` where those values originate from the template on first load.

---

### 4.5 `dashboard_tables_json`

```python
@login_required
def dashboard_tables_json(request):
```

**URL:** `GET /dashboard/tables-json/`
**Auth:** `@login_required` + `can_view_inventory`
**Returns:** `JsonResponse`
**Cache:** `'dashboard_inventory_tables'` — **30 seconds** (shared with `dashboard_view`)

#### Purpose

Returns the full analytics table data (inventory, ammo, magazine, accessory) as JSON for front-end table refresh without a full page reload. Reads from the same `'dashboard_inventory_tables'` cache key that `dashboard_view()` populates, so the expensive aggregate queries are not duplicated.

#### Response JSON Structure

```json
{
    "inventory": {
        "rows": [
            {
                "nomenclature": "Carbine, 5.56mm: M4 (DSAR-15)",
                "list_url": "/inventory/pistols/?q=...",
                "possessed": 15, "on_stock": 10, "issued_par": 3, "issued_tr": 2,
                "serviceable": 13, "unserviceable": 1, "lost": 0, "tampered": 0
            },
            ...
        ],
        "totals": { "possessed": 120, "on_stock": 85, ... }
    },
    "ammo": {
        "rows": [
            {
                "nomenclature": "(428) Ctg, 5.56mm: Ball, M193",
                "list_url": "/inventory/ammunition/",
                "basic_load": 5000, "on_hand": 4200, "issued": 800,
                "issued_par": 400, "issued_tr": 400,
                "serviceable": 4200, "unserviceable": 0, "lost": 0
            },
            ...
        ],
        "totals": { ... }
    },
    "magazine": {
        "rows": [
            {
                "nomenclature": "Mag Assy, 9mm: Glock 17",
                "list_url": "/inventory/magazines/",
                "on_stock": 45, "issued_par": 5, "issued_tr": 10
            },
            ...
        ],
        "totals": { "on_stock": 200, "issued_par": 30, "issued_tr": 50 }
    },
    "accessory": {
        "rows": [
            {
                "nomenclature": "Pistol Holster",
                "list_url": "/inventory/accessories/",
                "on_stock": 30, "issued_par": 5, "issued_tr": 20
            },
            ...
        ],
        "totals": { "on_stock": 120, "issued_par": 15, "issued_tr": 55 }
    }
}
```

---

### 4.6 `issued_stats_json`

```python
@login_required
def issued_stats_json(request):
```

**URL:** `GET /dashboard/issued-stats/`
**Auth:** `@login_required` + `can_view_inventory`
**Returns:** `JsonResponse`
**Cache:** **None** — always queries live data.

#### Purpose

Returns the current issued TR/PAR firearm counts in real-time. No caching is applied because this endpoint is designed for immediate accuracy — it is called when a user needs the freshest possible count (e.g., after completing a transaction).

#### Response JSON Fields

```json
{
    "issued_TR":    35,
    "issued_PAR":   10,
    "total_issued": 45
}
```

#### Counting Logic

Counts `TransactionLogs` records where:
- `log_status` is `'Open'` or `'Partially Returned'`
- `issuance_type` matches `'TR (Temporary Receipt)'` or `'PAR (Property Acknowledgement Receipt)'`
- A firearm was withdrawn (`withdraw_pistol` or `withdraw_rifle` is not null)
- The firearm has not yet been returned (`return_pistol` or `return_rifle` is null)

Pistol and rifle counts are summed separately for each issuance type (4 queries total).

---

## 5. Caching Architecture

| Cache Key | TTL | Populated By | Invalidated By |
|---|---|---|---|
| `'dashboard_stats_{today}'` | 60 s | `dashboard_view()` | Date change (new key per day) |
| `'dashboard_inventory_tables'` | 30 s | `dashboard_view()`, `dashboard_tables_json()` | TTL expiry only |
| `'dashboard_cards_{today}'` | 10 s | `dashboard_cards_json()` | `create_transaction()` (explicit `cache.delete`), date change |

### Cache Backend Notes

- **Development / default:** `FileBasedCache` — stored on disk, shared across Gunicorn workers via filesystem. `cache.add()` and `cache.incr()` are not atomically guaranteed.
- **Production (recommended):** `RedisCache` — configure `CACHE_BACKEND=django.core.cache.backends.redis.RedisCache` and `CACHE_LOCATION=redis://127.0.0.1:6379/1` in the production `.env` file for fully atomic operations.

The `dashboard_cards` key uses the date as a suffix (`{today}`) so a day rollover automatically shifts to a new cache key. This ensures `withdrawals_today` / `returns_today` counters reset cleanly at midnight without requiring an explicit invalidation.

---

## 6. URL Routing

Registered in `armguard/urls.py`:

```python
from armguard.apps.dashboard.views import (
    dashboard_view,
    download_ssl_cert,
    ssl_cert_status,
    issued_stats_json,
    dashboard_cards_json,
    dashboard_tables_json,
)

urlpatterns = [
    path('dashboard/',                dashboard_view,        name='dashboard'),
    path('dashboard/issued-stats/',   issued_stats_json,     name='issued-stats-json'),
    path('dashboard/cards-stats/',    dashboard_cards_json,  name='dashboard-cards-json'),
    path('dashboard/tables-json/',    dashboard_tables_json, name='dashboard-tables-json'),
    path('download/ssl-cert/',        download_ssl_cert,     name='download-ssl-cert'),
    path('download/ssl-cert-status/', ssl_cert_status,       name='ssl-cert-status'),
]
```

---

## 7. Data Flow Diagram

```
Browser (initial load)
    │
    ▼
GET /dashboard/
    │
    ├─ cache.get('dashboard_stats_{today}')
    │       miss → 6 aggregate DB queries → cache.set(60s)
    │       hit  → use cached dict
    │
    ├─ cache.get('dashboard_inventory_tables')
    │       miss → 4 × _build_*_table() → cache.set(30s)
    │       hit  → use cached dict
    │
    └─ render('dashboard/dashboard.html', context)

Browser (JS polling — every 10 s)
    │
    ▼
GET /dashboard/cards-stats/
    │
    ├─ cache.get('dashboard_cards_{today}')
    │       miss → ~8 simple count/aggregate queries → cache.set(10s)
    │       hit  → return JsonResponse immediately
    │
    └─ JsonResponse(data)

Browser (JS refresh — on user action)
    │
    ▼
GET /dashboard/tables-json/
    │
    ├─ cache.get('dashboard_inventory_tables')
    │       miss → 4 × _build_*_table() → cache.set(30s)
    │       hit  → return cached tables
    │
    └─ JsonResponse(structured table data)

POST /transactions/create/ (transaction saved)
    │
    └─ cache.delete('dashboard_cards_{today}')  ← immediate invalidation
```

---

## 8. Query Optimisation Notes

The following optimisations were applied (tagged in the source as `N+1 FIX` and `5.6 FIX`):

| Area | Before | After |
|---|---|---|
| `_build_inventory_table()` | 10 per-model DB queries | 2 grouped aggregates + 2 annotation queries |
| `_build_ammo_table()` | 5 × 2 per-type queries | 3 queries total (1 on-hand + 2 logs) |
| `_build_magazine_table()` | Multiple per-type queries | 1 conditional aggregate function × 3 filters |
| `_build_accessory_table()` | 3 separate aggregate queries per type | 1 conditional aggregate function × 3 filters |
| `dashboard_view()` stats | 17 individual count/aggregate queries | 6 conditional aggregate queries |
| `dashboard_cards_json()` | Separate queries per stat | ~8 targeted queries with 10-second cache |

The PAR/TR split in `_build_inventory_table()` uses a `Subquery` annotation rather than a `Subquery-inside-Count` because the latter produces unreliable results across Django and SQLite versions. The accumulation is done in Python using `collections.defaultdict` after a single annotated queryset fetch.

---

## 9. Security Notes

| Control | Implementation |
|---|---|
| Authentication | `@login_required` on all non-public views |
| Permission check | `can_view_inventory(request.user)` — returns 403 on failure |
| CSRF | All views are GET-only; no CSRF token required |
| Public endpoints | `download_ssl_cert` and `ssl_cert_status` are intentionally unauthenticated; they expose only public certificate metadata |
| Cache key isolation | Cache keys include `{today}` to prevent cross-day data leakage |
| No raw SQL | All queries use the Django ORM with parameterised values |
| No user-controlled query params | Table builder functions do not accept any request input; all filters are hardcoded |
| IP not logged here | IP and user logging is handled by `ActivityLogMiddleware`, not in these views |
