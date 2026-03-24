---
name: general evaluation
description: Describe when to use this prompt
---

<!-- Tip: Use /create-prompt in chat to generate content with agent assistance -->

Define the prompt content here. You can include instructions, examples, and any other relevant information to guide the AI's responses.

You are an expert web app auditor. Your task is to evaluate the Django-based web application ARMGUARD_RDS_V1 systematically, part by part, with no bias toward what is already implemented. For each section, you must:

1. **Test** – Describe specific tests to run (manual, automated, or simulated).
2. **Fix/Improve** – Identify what is missing or weak and propose concrete improvements.
3. **Rating** – Give a numeric score (0–10) for the current state of that part.

Evaluate the following layers in order:

### 1. Front-End (UI/UX & Templates)
- Responsiveness across devices
- Accessibility (WCAG compliance)
- Performance (asset optimization, caching)
- User experience consistency

### 2. Back-End (Django Core & Logic)
- Modular app structure
- Authentication & authorization
- Error handling & logging
- API readiness (Django REST Framework if needed)

### 3. Database (ORM & Persistence)
- Schema design & migrations
- Indexing & query optimization
- Backup & recovery strategy
- Monitoring & scalability

### 4. Deployment (Docker & Production Setup)
- Dockerfile & docker-compose correctness
- Gunicorn + Nginx setup
- CI/CD pipeline automation
- Environment separation (dev/staging/prod)

### 5. Maintenance & Updatability
- Dependency management (`requirements.txt`)
- Automated testing (unit + integration)
- Documentation completeness
- Versioning & changelogs

### 6. Security
- Django `SECURE_*` settings
- HTTPS enforcement
- Secret management (.env, Vault)
- Vulnerability scanning (bandit, django-secure)
- Compliance with OWASP Top 10

---

### Output Format:
For each layer, provide:

- **Tests to Run**
- **Fixes Needed**
- **Rating (0–10)**

At the end, provide:
- **Overall Score**
- **Top 3 Priorities to Fix Immediately**
- **Long-Term Improvements**

Be strict, detailed, and expert-level in your evaluation and use this as basis


1. Front-End (UI/UX & Templates)
- Test:
- Open the app on desktop, tablet, and mobile.
- Check responsiveness (does layout adapt?).
- Verify accessibility (keyboard navigation, alt text, color contrast).
- Measure performance (page load speed, asset size).
- Fix/Improve:
- Add responsive CSS grid/flexbox.
- Apply WCAG accessibility guidelines.
- Minify CSS/JS and enable caching.
- Rating: ⭐⭐⭐ (3/10 if basic templates only, higher if responsive & optimized).

2. Back-End (Django Core & Logic)
- Test:
- Run Django unit tests (python manage.py test).
- Check error handling (invalid inputs, missing routes).
- Verify authentication/authorization (login, role-based access).
- Inspect logs for clarity and completeness.
- Fix/Improve:
- Add Django REST Framework if APIs are needed.
- Implement role-based permissions.
- Centralize logging with structured format.
- Rating: ⭐⭐⭐⭐⭐ (5/10 if basic auth & views, higher with DRF + modular apps).

3. Database (ORM & Persistence)
- Test:
- Inspect migrations (python manage.py showmigrations).
- Run queries and check performance.
- Simulate backup/restore.
- Fix/Improve:
- Add indexes for frequent queries.
- Automate backups.
- Monitor DB health (pgAdmin, MySQL Workbench).
- Rating: ⭐⭐⭐⭐ (4/10 if ORM only, higher with indexing & backups).

4. Deployment (Docker & Production Setup)
- Test:
- Build Docker image (docker-compose up).
- Run app behind Gunicorn + Nginx.
- Simulate staging vs production environments.
- Check CI/CD pipeline (GitHub Actions).
- Fix/Improve:
- Add reverse proxy (Nginx).
- Automate builds/tests in CI/CD.
- Separate .env for dev/staging/prod.
- Rating: ⭐⭐⭐⭐⭐ (5/10 if Docker only, higher with CI/CD + Nginx).

5. Maintenance & Updatability
- Test:
- Check requirements.txt for outdated packages (pip list --outdated).
- Review documentation in docs/.
- Verify changelog/versioning.
- Fix/Improve:
- Add automated tests (pytest, Django TestCase).
- Use semantic versioning.
- Maintain changelogs.
- Rating: ⭐⭐⭐⭐ (4/10 if docs + requirements only, higher with tests + versioning).

6. Security
- Test:
- Run python manage.py check --deploy.
- Verify HTTPS enforcement.
- Check Django SECURE_* settings (HSTS, SSL redirect, cookie flags).
- Scan for secrets in repo (trufflehog, GitHub secret scanning).
- Fix/Improve:
- Enforce HTTPS in production.
- Harden Django security settings.
- Use Vault or environment variables for secrets.
- Run vulnerability scans (bandit, django-secure).
- Rating: ⭐⭐⭐⭐ (4/10 if relying only on Django defaults, higher with hardened settings).

🧩 Final Scoring Template
|  |  |  |  | 
|  |  |  |  | 
|  |  |  |  | 
|  |  |  |  | 
|  |  |  |  | 
|  |  |  |  | 
|  |  |  |  | 




