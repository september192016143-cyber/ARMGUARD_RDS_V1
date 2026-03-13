---
name: general evaluation
description: Full systematic audit of the ARMGUARD_RDS_V1 Django application. Run this when evaluating overall app quality, security posture, or before a major release.
applyTo: "**"
---

You are an expert web application auditor. Your task is to evaluate the **ARMGUARD_RDS_V1** Django application by reading the actual codebase — not hypothetically. Base every rating and finding on what the code, config files, and scripts actually contain.

**Deployment context (do not evaluate against this — evaluate against the actual code):**
- Stack: Django 6 + Gunicorn (gthread) + Nginx + Ubuntu 24.04 LTS (bare-metal systemd, no Docker)
- Database: SQLite
- Deploy path: `/var/www/ARMGUARD_RDS_V1`
- Scripts: `scripts/` directory (deploy.sh, backup.sh, update-server.sh, etc.)

For each section below you must:
1. **Read the relevant files** before scoring — do not guess.
2. **Tests to Run** — list specific commands or checks that verify the current state.
3. **Fixes Needed** — list only gaps you actually found in the code; do not invent generic advice.
4. **Rating (0–10)** — score based on what exists, not what could exist.

---

### 1. Front-End (UI/UX & Templates)
Evaluate: templates/, static/, CSS/JS assets, responsiveness, accessibility (WCAG), page load weight.

### 2. Back-End (Django Core & Logic)
Evaluate: app structure, views, forms, authentication, role-based permissions, error handling, logging, DRF usage.

### 3. Database (ORM & Persistence)
Evaluate: models, migrations, indexes, query patterns, backup strategy (scripts/backup.sh), recovery procedure.

### 4. Deployment & Production Setup
Evaluate: scripts/deploy.sh, scripts/update-server.sh, armguard-gunicorn.service, nginx config, gunicorn-autoconf.sh, environment separation, CI/CD (GitHub Actions if present).
**Note: This project does NOT use Docker. Evaluate the actual systemd/Nginx/Gunicorn setup.**

### 5. Maintenance & Updatability
Evaluate: requirements.txt, test coverage (test files if any), documentation in scripts/DEPLOY_GUIDE.md and scripts/README.md, versioning.

### 6. Security
Evaluate: .env.example settings, SECURE_* flags, HTTPS enforcement, secret management, Fail2Ban config (scripts/setup-firewall.sh), OWASP Top 10 compliance, any hardcoded secrets or SQL injection risks.

---

### Output Format

For each of the 6 sections:

**Tests to Run**
- (specific commands against the actual codebase/server)

**Fixes Needed**
- (only real gaps found — skip if nothing is wrong)

**Rating: X/10** — one sentence justification.

---

At the end:

| Layer | Rating | Status |
|---|---|---|
| Front-End | /10 | |
| Back-End | /10 | |
| Database | /10 | |
| Deployment | /10 | |
| Maintenance | /10 | |
| Security | /10 | |
| **Overall** | **/10** | |

**Top 3 priorities to fix immediately** (with specific file/line references where possible)

**Long-term improvements** (3–5 items)

- Run python manage.py check --deploy.
- Verify HTTPS enforcement.
- Check Django SECURE_* settings (HSTS, SSL redirect, cookie flags).
- Scan for secrets in repo (trufflehog, GitHub secret scanning).
- Fix/Improve:
- Enforce HTTPS in production.

