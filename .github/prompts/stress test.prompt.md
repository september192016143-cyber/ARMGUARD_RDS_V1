---
name: stress test
description: Describe when to use this prompt
---

<!-- Tip: Use /create-prompt in chat to generate content with agent assistance -->

Define the prompt content here. You can include instructions, examples, and any other relevant information to guide the AI's responses.

You are a senior DevOps and performance testing expert. I want to benchmark the concurrency limits of my Python web application (ARMGUARD_RDS_V1) deployed with Gunicorn + Nginx using Docker Compose on Ubuntu Server. The hardware is an HP ProDesk mini PC (Intel i5-6500T, 4 cores, 8 GB RAM, 4 GB swap). 

Your tasks:
1. Create automated stress‑test scripts that:
   - Detect server specs (CPU cores, RAM).
   - Run incremental load tests using ApacheBench (`ab`) and wrk.
   - Start with low concurrency (10 users) and scale up (50, 100, 200, 500).
   - Log throughput (requests/sec), latency, and error rates at each level.
   - Save results to timestamped log files for later analysis.
2. Ensure the scripts are reusable and require no manual setup:
   - Auto‑install required tools (`ab`, `wrk`) if missing.
   - Auto‑detect the server’s IP/hostname from environment variables.
   - Run tests against the Gunicorn/Nginx endpoint automatically.
3. Provide a master script (`stress_test.sh`) that orchestrates the tests, evaluates results, and outputs a summary of the maximum stable concurrency the server can handle.
4. Include clear instructions on how to run the script and interpret the results.

Deliver the output as ready‑to‑use Bash scripts with comments explaining each step, plus a short guide on how to run them and analyze the results.