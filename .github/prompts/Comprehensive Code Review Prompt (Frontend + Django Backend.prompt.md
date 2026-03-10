---
name: Comprehensive Code Review Prompt (Frontend + Django Backend
description: Describe when to use this prompt
---

<!-- Tip: Use /create-prompt in chat to generate content with agent assistance -->

Define the prompt content here. You can include instructions, examples, and any other relevant information to guide the AI's responses.

Please perform a detailed code review of the following Django + frontend project with emphasis on:

1. **Frontend-to-Backend Connection**
   - Verify that API endpoints are correctly defined and consumed.
   - Check if frontend requests (fetch/axios/etc.) properly match Django backend routes.
   - Ensure consistent use of HTTP methods (GET, POST, PUT, DELETE).
   - Confirm error handling and response parsing are implemented.

2. **Sync Links & Routing**
   - Review frontend routing (React Router, Vue Router, etc.) for correct link synchronization.
   - Ensure navigation paths align with backend routes and return expected JSON data.
   - Check for broken links, mismatched paths, or hardcoded URLs vs. environment-based API endpoints.

3. **Data Flow & State Management**
   - Validate that data retrieved from the backend is correctly stored in state (Redux, Context, Vuex, etc.).
   - Confirm updates propagate properly between frontend and backend.
   - Ensure CRUD operations sync correctly across both layers.

4. **Django Backend (REST API)**
   - Verify that Django REST Framework (DRF) views, serializers, and URLs are correctly defined.
   - Check if models are exposed properly through serializers without leaking sensitive fields.
   - Confirm that API endpoints follow REST conventions (GET, POST, PUT, DELETE).
   - Validate authentication/permissions setup (JWT, session, or token-based).

5. **Frontend Integration with Django**
   - Ensure frontend requests include CSRF tokens or JWT headers where required.
   - Verify error handling for failed requests (400/500 responses).
   - Confirm that data returned from the backend is parsed and displayed correctly.

6. **Security & Best Practices**
   - Look for proper handling of authentication tokens or session data.
   - Ensure sensitive data is not exposed in API responses or frontend code.
   - Verify proper use of Django settings (DEBUG, ALLOWED_HOSTS, CORS).
   - Check that authentication tokens are stored securely (avoid localStorage if possible).

7. **Code Quality**
   - Identify redundant code, unused imports, or inconsistent naming conventions.
   - Suggest improvements for readability, maintainability, and scalability.
   - Ensure consistent project structure and adherence to best practices across both frontend and backend.