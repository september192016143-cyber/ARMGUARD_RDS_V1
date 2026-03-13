---
name: diagnostic review
description: Describe when to use this prompt
---

---
name: diagnostic review
description: Deep Django diagnostic of ARMGUARD_RDS_V1 — bugs, sync/link problems, ORM issues, security gaps, and performance risks. Run when chasing a specific bug or doing a pre-release health check.
applyTo: "**"
---

You are a senior Django developer performing a full diagnostic review of the **ARMGUARD_RDS_V1** application.

**Project context:**
- Stack: Django 5.x + Gunicorn (gthread) + Nginx + Ubuntu 24.04 LTS (bare-metal systemd, no Docker)
- Database: SQLite
- Deploy path: `/var/www/ARMGUARD_RDS_V1`
- Key directories: `armguard/` (Django apps), `scripts/` (deploy/backup/update), `templates/`, `static/`

**Rules — enforce these for every section:**
1. **Read the actual files** before reporting — do not give generic advice without citing a specific file path and line number.
2. For each confirmed issue: state the file, function/line, what is wrong, and the exact fix.
3. For each potential risk: state why it is fragile and under what condition it breaks.
4. Skip any sub-item where no problem exists — write "No issues found."
5. Do not invent problems. Only report what you actually see in the code.

---

### 1. Folder & File Structure
- Is business logic separated from views (no fat views, no DB queries in templates)?
- Are `models.py`, `views.py`, `urls.py`, `forms.py`, `admin.py`, `migrations/` in their correct app?
- Any misplaced files, dead modules, or apps that should be merged or split?

### 2. Confirmed Bugs
- Syntax errors, `NameError`/`AttributeError` risks, broken imports.
- Misconfigured `settings.py` values (e.g., wrong `ALLOWED_HOSTS`, `STATIC_ROOT`, `MEDIA_ROOT`).
- Incorrect URL routing: missing `app_name`, reversed URLs that don't resolve, named patterns that conflict.
- Template tags or context variables referenced but never passed by the view.

### 3. Sync & Link Problems
- Migration state: check the migration files in each app's `migrations/` directory — are any squashed migrations unreplaced, or is there a gap in the numbered sequence?
- Foreign keys and M2M: `on_delete` policy correct? Any missing `related_name` causing reverse accessor clashes?
- Signals: `post_save`/`pre_delete` receivers — are they connected via `AppConfig.ready()` in `apps.py`? Missing `ready()` import is the most common reason signals silently don't fire.
- Static/media file paths: `STATICFILES_DIRS`, `MEDIA_ROOT`, Nginx `location` blocks — any broken references?
- Template `{% url %}` tags and `{% static %}` tags — do the names and paths exist?

### 4. Potential Bugs & Risks
- Fragile querysets: `.get()` calls without `try/except ObjectDoesNotExist`, `.first()` with unchecked `None`.
- Forms: missing `cleaned_data` checks, `commit=False` saves without explicit `.save_m2m()`.
- Views: any `request.POST` values accessed directly without form validation.
- Dependency risks in `requirements.txt`: pinned to a known-broken or CVE-affected version?

### 5. Security
- Authentication: are all non-public views protected with `@login_required` or `LoginRequiredMixin`?
- Authorization: role/permission checks on views that modify data — not just authenticate.
- CSRF: any `@csrf_exempt` decorators that shouldn't be?
- Querysets: raw SQL (`cursor.execute`, `extra()`, `RawQuerySet`) — parameterized correctly?
- File uploads: is `MEDIA_ROOT` separate from `STATIC_ROOT`? Does the Nginx config serving `MEDIA_ROOT` require authentication, or are uploaded files publicly accessible without a login?

### 6. Performance & Reliability
- N+1 patterns: loops over querysets that trigger per-row queries — needs `select_related`/`prefetch_related`.
- Missing indexes: fields used in `.filter()`, `.order_by()`, or FK lookups without `db_index=True`.
- Heavy view logic: any synchronous external calls (requests, subprocess) without timeout or async alternative?
- Error handling: bare `except:` clauses, silent `pass`, or exceptions swallowed without logging.

---

### Output Format

For each section:

**Confirmed issues**
- `path/to/file.py:line` — what is wrong — exact fix

**Potential risks**
- `path/to/file.py:line` — why it is fragile — what triggers it

---

At the end:

Priority key: 🔴 Critical (breaks in production) | 🟠 Medium (breaks under edge cases) | 🟢 Low (code smell / tech debt)

Add one row per finding. Do not limit the number of rows.

| # | Priority | File | Issue | Fix |
|---|---|---|---|---|

**Refactoring opportunities** (if any — cite specific files)