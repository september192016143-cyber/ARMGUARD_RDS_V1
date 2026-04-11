# =============================================================================
# ARMGUARD RDS V1 — Upload Google Service Account Key to Server
# =============================================================================
# Run this ONCE from your Windows machine to securely copy the SA JSON key
# to the production server and set correct permissions.
#
# Usage (from project root):
#   .\scripts\upload-sa-key.ps1
#
# Or with custom parameters:
#   .\scripts\upload-sa-key.ps1 -KeyFile "C:\path\to\sa-key.json" -Server "192.168.0.11" -User "armguard"
# =============================================================================

param(
    [string]$KeyFile  = "$PSScriptRoot\..\project\utils\googlesheet\personnel-data-for-armguard-38f338af74f0.json",
    [string]$Server   = "192.168.0.11",
    [string]$User     = "armguard",
    [string]$RemotePath = "/var/www/armguard-sa.json"
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  ARMGUARD RDS — Upload Service Account Key" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Resolve key file path
$KeyFile = Resolve-Path $KeyFile -ErrorAction SilentlyContinue
if (-not $KeyFile -or -not (Test-Path $KeyFile)) {
    Write-Host "[ERROR] Key file not found: $KeyFile" -ForegroundColor Red
    Write-Host "        Place the JSON key file at the expected path and retry." -ForegroundColor Red
    exit 1
}

Write-Host "[INFO]  Key file : $KeyFile" -ForegroundColor Cyan
Write-Host "[INFO]  Server   : $User@${Server}:${RemotePath}" -ForegroundColor Cyan
Write-Host ""

# Step 1 — SCP the key file to the server
Write-Host ">>> Copying key file to server..." -ForegroundColor White
scp "$KeyFile" "${User}@${Server}:${RemotePath}"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] scp failed. Check SSH access to $Server." -ForegroundColor Red
    exit 1
}
Write-Host "[OK]    Key file copied." -ForegroundColor Green

# Step 2 — Set permissions on the server
Write-Host ">>> Setting permissions on server..." -ForegroundColor White
ssh "${User}@${Server}" "sudo chmod 600 '$RemotePath' && sudo chown ${User}:${User} '$RemotePath'"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] SSH permission command failed." -ForegroundColor Red
    exit 1
}
Write-Host "[OK]    Permissions set (600, owned by $User)." -ForegroundColor Green

# Step 3 — Remind about .env
Write-Host ""
Write-Host "[INFO]  Add this line to /var/www/ARMGUARD_RDS_V1/.env on the server:" -ForegroundColor Cyan
Write-Host "        GOOGLE_SA_JSON=$RemotePath" -ForegroundColor Yellow
Write-Host ""
Write-Host "[INFO]  Then run the update script to activate Google Sheets import:" -ForegroundColor Cyan
Write-Host "        sudo bash /var/www/ARMGUARD_RDS_V1/scripts/update-server.sh" -ForegroundColor Yellow
Write-Host ""
Write-Host "[OK]    Done." -ForegroundColor Green
