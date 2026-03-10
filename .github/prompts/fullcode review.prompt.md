---
name: fullcode review
description: Describe when to use this prompt
---

<!-- Tip: Use /create-prompt in chat to generate content with agent assistance -->

Define the prompt content here. You can include instructions, examples, and any other relevant information to guide the AI's responses.

You are a senior software engineer tasked with performing a full code review of my web application. Please analyze both the source code and the app folder/file structure with the following focus areas:

1. **Project & Folder Structure**
   - Evaluate the organization of folders and files (e.g., separation of concerns, modularity).
   - Identify redundant, misplaced, or poorly named files.
   - Suggest improvements for scalability, maintainability, and onboarding new developers.

2. **Architecture & Design Patterns**
   - Assess whether the chosen frameworks, libraries, and patterns are appropriate.
   - Highlight areas where the architecture could be simplified or modernized.

3. **Code Quality**
   - Review readability, maintainability, and adherence to coding standards.
   - Check for consistency in naming conventions, indentation, and formatting.
   - Identify duplicate logic or unnecessary complexity.

4. **Security**
   - Inspect for vulnerabilities (SQL injection, XSS, CSRF, insecure authentication).
   - Review data validation, sanitization, and access control mechanisms.

5. **Performance**
   - Spot inefficient queries, algorithms, or rendering logic.
   - Recommend optimizations for speed and scalability.

6. **Testing & Reliability**
   - Evaluate test coverage and quality of unit/integration tests.
   - Review error handling, logging, and debugging practices.

7. **Dependencies & Environment**
   - Check for outdated or risky dependencies.
   - Review environment configuration files for security and maintainability.

8. **Actionable Recommendations**
   - Provide prioritized fixes (critical, medium, low).
   - Suggest refactoring opportunities and folder/file restructuring.
   - Recommend modern best practices for long-term maintainability.

Deliver the review in a structured format with clear sections, examples from the code and file structure, and practical recommendations for improvement.