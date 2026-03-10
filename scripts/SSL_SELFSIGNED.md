# ARMGUARD RDS V1 — Self-Signed SSL (LAN-Only)

Use this guide when the server is accessed **only inside the local network** and you do not have a public domain name. A self-signed certificate encrypts traffic between browser and server.

By default browsers show a "Not secure" or "Your connection is not private" warning for self-signed certs. **Section 8** of this guide explains how to import the certificate into Windows so the warning disappears permanently — no public DNS, no internet exposure required.

> **Server IP used in this guide:** `192.168.0.11`  
> Replace it with your actual LAN IP if different.

---

## STEP 1 — Generate the self-signed certificate

> **Important:** The `-addext subjectAltName` flag is required. Without it, Chrome/Edge will always show "Not secure" even after importing the cert into Windows.

```bash
sudo openssl req -x509 -nodes -days 1095 -newkey rsa:2048 \
  -keyout /etc/ssl/private/armguard-selfsigned.key \
  -out /etc/ssl/certs/armguard-selfsigned.crt \
  -subj "/C=PH/ST=Metro Manila/L=Manila/O=ArmGuard RDS/CN=192.168.0.11" \
  -addext "subjectAltName=IP:192.168.0.11"
```

This creates:
- `/etc/ssl/private/armguard-selfsigned.key` — private key (keep secret)
- `/etc/ssl/certs/armguard-selfsigned.crt` — certificate (3-year validity)

---

## STEP 2 — Generate DH parameters (for strong cipher suites)

```bash
sudo openssl dhparam -out /etc/ssl/certs/dhparam.pem 2048
```

This takes ~30–60 seconds. Only needs to be done once.

---

## STEP 3 — Update the Nginx configuration

Open the Nginx site config:

```bash
sudo nano /etc/nginx/sites-available/armguard
```

**Replace** the current `listen 80` server block:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name 192.168.0.11;
    ...
}
```

**With** this SSL server block:

```nginx
# Redirect HTTP → HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name 192.168.0.11;
    return 301 https://$host$request_uri;
}

# HTTPS server
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name 192.168.0.11;

    server_tokens off;
    client_max_body_size 20M;

    # Self-signed certificate
    ssl_certificate     /etc/ssl/certs/armguard-selfsigned.crt;
    ssl_certificate_key /etc/ssl/private/armguard-selfsigned.key;
    ssl_dhparam         /etc/ssl/certs/dhparam.pem;

    # Modern TLS settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # Gzip compression for dynamic responses
    gzip            on;
    gzip_vary       on;
    gzip_proxied    any;
    gzip_comp_level 5;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/html text/xml
               application/json application/javascript
               application/xml application/xml+rss text/javascript;

    # Static files
    location /static/ {
        alias /var/www/ARMGUARD_RDS_V1/project/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
        access_log off;
        gzip on;
        gzip_types text/css application/javascript application/json;
    }

    location /media/ {
        alias /var/www/ARMGUARD_RDS_V1/project/media/;
        expires 7d;
        add_header Cache-Control "public";
        access_log off;
        location ~* \.(php|py|sh|cgi|rb|pl)$ {
            deny all;
        }
    }

    # Rate-limited login
    location /accounts/login/ {
        limit_req zone=armguard_login burst=3 nodelay;
        limit_req_status 429;
        proxy_pass http://armguard_app;
        include /etc/nginx/snippets/proxy-params.conf;
    }

    # Django application
    location / {
        proxy_pass http://armguard_app;
        include /etc/nginx/snippets/proxy-params.conf;
        proxy_connect_timeout 60s;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
    }

    location ~ /\. {
        deny all;
        access_log off;
        log_not_found off;
    }

    location = /favicon.ico { log_not_found off; access_log off; }
    location = /robots.txt  { proxy_pass http://armguard_app; include /etc/nginx/snippets/proxy-params.conf; access_log off; }
}
```

Save and exit: `Ctrl+O` → `Enter` → `Ctrl+X`

---

## STEP 4 — Allow HTTPS through the firewall

```bash
sudo ufw allow 443/tcp comment 'HTTPS (self-signed)'
sudo ufw status
```

---

## STEP 5 — Test and reload Nginx

```bash
sudo nginx -t
sudo systemctl reload nginx
```

---

## STEP 6 — Update the .env file to enable HTTPS flags

```bash
sudo nano /var/www/ARMGUARD_RDS_V1/.env
```

Change these lines:

```env
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
CSRF_TRUSTED_ORIGINS=https://192.168.0.11
```

Save and restart Gunicorn:

```bash
sudo systemctl restart armguard-gunicorn
```

---

## STEP 7 — Access the app

Open a browser and go to:

```
https://192.168.0.11
```

The browser will warn: **"Your connection is not private"** or **"Not Secure"**.

- **Chrome/Edge:** Click **Advanced** → **Proceed to 192.168.0.11 (unsafe)**
- **Firefox:** Click **Advanced** → **Accept the Risk and Continue**

This warning is expected. Traffic is still encrypted — the browser just cannot verify a trusted CA signed the certificate.

---

## STEP 8 — Eliminate the browser warning (Windows cert import)

Importing the certificate into Windows as a Trusted Root CA makes Chrome, Edge, and any other browser on that machine trust the cert permanently — no more warning, green padlock.

Do this **once on each Windows PC** that needs to access the app.

### Method A — Download from the app (easiest)

After logging into the ArmGuard web interface, click **"Install SSL Cert"** in the sidebar footer (above Sign out). The browser downloads `armguard-selfsigned.crt` automatically.

Once downloaded:
1. Double-click the `.crt` file on your Desktop
2. Click **Install Certificate**
3. Choose **Local Machine** → **Next**
4. Select **Place all certificates in the following store** → **Browse** → **Trusted Root Certification Authorities** → **OK**
5. Click **Next** → **Finish**
6. Restart Chrome/Edge completely (close all windows, then reopen)

Navigate to `https://192.168.0.11` — the padlock will now show with no warning.

---

### Method B — Copy manually via PowerShell (alternative)

Use this if you need to install the cert **before** logging into the app (e.g. first-time setup).

#### 8a — Copy the certificate from the server to Windows

In **Windows PowerShell** (normal user, not admin):

```powershell
scp rds@192.168.0.11:/etc/ssl/certs/armguard-selfsigned.crt "$env:USERPROFILE\Desktop\armguard.crt"
```

Enter the server password when prompted. The file saves to your Desktop.

#### 8b — Import into Windows Trusted Root store

In **PowerShell as Administrator** (right-click PowerShell → Run as administrator):

```powershell
certutil -addstore "Root" "$env:USERPROFILE\Desktop\armguard.crt"
```

Expected output:
```
Root "Trusted Root Certification Authorities"
Certificate "ArmGuard RDS" added to store.
CertUtil: -addstore command completed successfully.
```

#### 8c — Restart Chrome/Edge completely

Close **all** browser windows (check the system tray — Chrome may stay running). Then reopen and go to `https://192.168.0.11`.

---

### Repeat for each additional PC

Repeat Step 8 (either method) on every Windows machine that needs access. The cert file on the server does not change.

### If the warning returns after cert renewal

Whenever the certificate is regenerated (Step 1 or Certificate Renewal below), you must:
1. Delete the old cert from Windows: `certutil -delstore "Root" "ArmGuard RDS"`
2. Re-import the new cert using Method A or Method B above

---

## Certificate renewal

The certificate is valid for **3 years** (`-days 1095`). To renew manually before expiry:

```bash
sudo openssl req -x509 -nodes -days 1095 -newkey rsa:2048 \
  -keyout /etc/ssl/private/armguard-selfsigned.key \
  -out /etc/ssl/certs/armguard-selfsigned.crt \
  -subj "/C=PH/ST=Metro Manila/L=Manila/O=ArmGuard RDS/CN=192.168.0.11" \
  -addext "subjectAltName=IP:192.168.0.11"

sudo systemctl reload nginx
```

After renewing, re-import the new cert on all Windows PCs (see Step 8).

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Browser says "ERR_CONNECTION_REFUSED" on port 443 | Check `sudo ufw status` — port 443 must be open |
| Nginx fails to start after config change | Run `sudo nginx -t` to find the syntax error |
| Login form redirects loop | Confirm `CSRF_TRUSTED_ORIGINS=https://192.168.0.11` in `.env` |
| Static files not loading after switching to HTTPS | Run `sudo systemctl reload nginx` |
| 500 error after enabling `SECURE_SSL_REDIRECT` | Confirm Nginx is serving HTTPS before setting this to `True` |
