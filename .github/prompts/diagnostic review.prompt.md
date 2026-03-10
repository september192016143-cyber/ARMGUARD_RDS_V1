---
name: diagnostic review
description: Describe when to use this prompt
---

<!-- Tip: Use /create-prompt in chat to generate content with agent assistance -->

Define the prompt content here. You can include instructions, examples, and any other relevant information to guide the AI's responses.

You are a senior Django developer tasked with performing a full diagnostic review of my Django web application. Please analyze all app code, including the app folder and file structure, with the following focus areas:

1. **Folder & File Structure**
   - Review the organization of `apps/`, `models.py`, `views.py`, `urls.py`, `forms.py`, `admin.py`, `migrations/`, and `settings.py`.
   - Identify misplaced logic (e.g., business logic inside views instead of models/services).
   - Suggest improvements for modularity, scalability, and maintainability.

2. **Bug Identification**
   - Detect syntax errors, runtime errors, and logical flaws in Django models, views, templates, and forms.
   - Highlight broken imports, misconfigured settings, or incorrect URL routing.
   - Identify broken functions, incorrect variable usage, or misapplied frameworks.

3. **Issues & Problems**
   - Spot poor coding practices, inconsistent naming, or missing documentation.
   - Identify areas where code may break under edge cases or unusual inputs.

4. **Sync & Link Problems**
   - Check database migrations for consistency and synchronization issues.
   - Verify that models are correctly linked with foreign keys, many-to-many relationships, and signals.
   - Review URL routing, template linking, and static/media file handling for broken paths or mismatches.
   - Inspect API integrations and external service connections for sync issues.
   - Check synchronization between frontend and backend logic.

5. **Potential Bugs & Risks**
   - Predict where future bugs may occur due to weak error handling, fragile querysets, or improper use of Django ORM.
   - Flag dependency mismatches, version conflicts, or outdated libraries in `requirements.txt`.

6. **Security**
   - Review authentication, authorization, CSRF protection, and session handling.
   - Check for unsafe querysets, unsanitized user input, or insecure file/media handling.

7. **Performance & Reliability**
   - Identify inefficient queries, N+1 problems, or heavy logic inside views.
   - Spot inefficient loops, rendering logic, or concurrency issues.
   - Suggest caching, pagination, or async improvements where needed.

8. **Actionable Recommendations**
   - Provide a prioritized list of fixes (critical, medium, low).
   - Suggest refactoring opportunities for models, views, templates, and folder/file structure.
   - Recommend best practices for migrations, signals, debugging, logging, and monitoring.

Deliver the review in a structured format with clear sections:
- **Confirmed Bugs/Issues**
- **Sync/Link Problems**
- **Potential Risks**
- **Recommendations**

Include specific examples from the Django code and folder structure wherever possible.