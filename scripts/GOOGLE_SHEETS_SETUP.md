# Google Sheets Import — Setup Guide
ARMGUARD RDS V1

---

## Overview

This feature allows bulk import of personnel records directly from a restricted
Google Sheet instead of uploading an `.xlsx` file. An optional `photo` column
accepts Google Drive share links for 2×2 photos.

Access is controlled at two levels:
- The Google Sheet is **restricted** — only the service account can read it
- The import page (`/personnel/import/`) requires a **superuser login**

---

## Prerequisites

- A Google account (personal Gmail is fine — no subscription needed)
- SSH access to the production server (`192.168.0.11`)
- PowerShell on your Windows machine (for `upload-sa-key.ps1`)

---

## Step 1 — Google Cloud: Create a Service Account

1. Go to [https://console.cloud.google.com](https://console.cloud.google.com)
2. Select (or create) the project: **Personnel Data for Armguard**
3. In the top search bar, search **"Google Sheets API"** → click Enable
4. Search **"Google Drive API"** → click Enable
5. Go to **IAM & Admin → Service Accounts**
6. Click **+ Create Service Account**
   - Name: `armguard-importer`
   - Click through — no roles needed
7. Click the newly created service account → **Keys tab**
8. Click **Add Key → Create new key → JSON** → download the file

> **Security:** Keep this file secret. Never commit it to Git.
> The `.gitignore` already blocks `*.json` and `project/utils/googlesheet/`.

Place the downloaded key at:
```
project\utils\googlesheet\<filename>.json
```

---

## Step 2 — Share the Google Sheet

1. Open your Google Sheet
2. Click **Share** (top right)
3. Paste the service account email (found inside the JSON under `client_email`):
   ```
   armguard-importer@personnel-data-for-armguard.iam.gserviceaccount.com
   ```
4. Set role to **Viewer** → click Send

The sheet stays restricted — no one else can access it through the link.

---

## Step 3 — Upload the Key to the Server

Run this from your Windows machine in PowerShell from the project root:

```powershell
cd "C:\Users\9533RDS\Desktop\hermosa\final\ARMGUARD_RDS_V1"
.\scripts\upload-sa-key.ps1
```

The script will:
- SCP the JSON key to `/var/www/armguard-sa.json` on the server
- Set permissions: `chmod 600` + `chown armguard:armguard`
- Print the exact `.env` line to add

To use a different key file or server:
```powershell
.\scripts\upload-sa-key.ps1 -KeyFile "C:\path\to\key.json" -Server "192.168.0.11" -User "armguard"
```

---

## Step 4 — Configure the Server .env

SSH into the server:
```bash
ssh armguard@192.168.0.11
```

Add the following line to `/var/www/ARMGUARD_RDS_V1/.env`:
```
GOOGLE_SA_JSON=/var/www/armguard-sa.json
```

Using nano:
```bash
sudo nano /var/www/ARMGUARD_RDS_V1/.env
```

---

## Step 5 — Run the Update Script

```bash
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/update-server.sh
```

The script will:
- Install `gspread` and `google-auth` from `requirements.txt`
- Verify the key file exists and has correct permissions
- Log whether the feature is enabled or misconfigured

Expected output:
```
[INFO]  Google Sheets import: gspread + google-auth present.
[INFO]  Service account key: /var/www/armguard-sa.json (permissions secured)
```

---

## Step 6 — Using the Import Page

1. Log in as a superuser at `https://192.168.0.11`
2. Go to **Personnel → Import**
3. The **Google Sheets** tab will now appear next to the Excel Upload tab
4. Paste your sheet URL and click **Import from Sheet**

---

## Google Sheet Column Layout

The first row must be a header row with these exact column names
(case-insensitive, order does not matter):

| Column | Required | Notes |
|---|---|---|
| `rank` | Yes | Exact abbreviation: `SGT`, `CPT`, etc. |
| `first_name` | Yes | Max 20 chars |
| `last_name` | Yes | Max 20 chars |
| `middle_initial` | Yes | Single letter |
| `afsn` | Yes | Unique. Enlisted: number; Officers: O-XXXX |
| `group` | Yes* | `HAS`, `951st`, `952nd`, `953rd` |
| `squadron` | Yes | Squadron name or designation |
| `tel` | Yes | Digits only, max 11 chars. Must be unique. |
| `status` | No | `Active` (default) or `Inactive` |
| `photo` | No | Google Drive share link for a 2×2 photo |

*`group` can be omitted if **Group Override** is selected in the import form.

---

## Photo Column (Optional)

To include 2×2 photos:

1. Upload each photo to Google Drive
2. Right-click the file → **Share** → change to **Anyone with the link → Viewer**
3. Copy the share link (e.g. `https://drive.google.com/file/d/FILE_ID/view`)
4. Paste it in the `photo` column for that person's row

The server will extract the file ID and download the image automatically during import.

> **Note:** Only the photos need to be publicly shared — the sheet itself stays restricted.

---

## Key Rotation (When to Revoke and Regenerate)

Revoke and regenerate the service account key if:
- The key file was ever shared, emailed, or visible in a conversation
- You suspect unauthorized access

To rotate:
1. [console.cloud.google.com](https://console.cloud.google.com) → IAM & Admin → Service Accounts
2. Click `armguard-importer` → **Keys tab** → delete the current key
3. **Add Key → Create new key → JSON** → download
4. Replace the local file and re-run `upload-sa-key.ps1`
5. No `.env` change needed — the path stays the same

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Google Sheets tab not visible | `GOOGLE_SA_JSON` not set in `.env`, or `update-server.sh` not run after setting it |
| "Could not read Google Sheet" error | Service account email not added as Viewer on the sheet |
| Key file not found warning in update script | Wrong path in `GOOGLE_SA_JSON`, or file not uploaded yet |
| Photo not imported | Photo not shared publicly on Drive; or Drive returned an HTML page instead of image bytes (file too large for direct download) |
| `gspread` not found | Run `update-server.sh` — it installs from `requirements.txt` |
