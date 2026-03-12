---
name: server optimization prompt
description: Describe when to use this prompt
---

<!-- Tip: Use /create-prompt in chat to generate content with agent assistance -->

Define the prompt content here. You can include instructions, examples, and any other relevant information to guide the AI's responses.

You are a senior DevOps and Python deployment expert. Review my GitHub repository [ARMGUARD_RDS_V1], which contains a Python web application deployed with Gunicorn + Nginx using Docker Compose on Ubuntu Server. The hardware is an HP ProDesk mini PC (Intel i5-6500T, 4 cores, 8 GB RAM, 4 GB swap).

Your tasks:
1. Analyze the deployment scripts (Dockerfile, docker-compose.yml, Nginx configs, helper scripts) for weaknesses, inefficiencies, and missing best practices.
2. Optimize Gunicorn worker/thread settings for this hardware, balancing performance and memory usage.
3. Implement auto-tuning improvements:
   - Dynamically adjust Gunicorn workers based on CPU/RAM availability.
   - Add Docker health checks and restart policies for self-healing.
   - Suggest monitoring hooks that can trigger scaling or alerts.
4. Improve Docker Compose with resource limits, logging, environment variable management, and restart policies.
5. Harden Nginx for production: SSL (Let’s Encrypt), caching, gzip compression, static file handling.
6. Suggest monitoring and logging improvements suitable for a small server (htop, Netdata, Prometheus/Grafana).
7. Recommend security best practices: SSH hardening, firewall rules, Fail2Ban, unattended upgrades.
8. Estimate realistic concurrent user capacity for this setup and explain the trade-offs.
9. Provide production-ready configuration examples (docker-compose.yml, Gunicorn systemd service file, Nginx site config) tailored to this environment.
10. Explain the rationale behind each optimization so I understand why it improves performance, reliability, or security.

Deliver the output as clear, ready-to-use configuration files and step-by-step instructions, with rationale for each improvement.