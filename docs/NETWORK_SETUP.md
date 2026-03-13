# ARMGUARD RDS — Network Setup Guide

**Target Platform:** HP ProDesk Mini (Ubuntu Server 24.04 LTS)  
**Document Date:** March 13, 2026  
**Purpose:** Connect client workstations (Armory PC, Dev PC) to the ARMGUARD server over LAN.

---

## 1. Network Overview

| Device | Hostname | IP Address | Subnet |
|--------|----------|------------|--------|
| **Server** | `9533rds` | `192.168.0.11` | `192.168.0.x` |
| **Dev PC** | `9533RDS` | `192.168.0.82` | `192.168.0.x` ✅ |
| **Armory PC** | `jay` | `192.168.1.66` | `192.168.1.x` ❌ Wrong subnet |

All devices must be on the **same subnet** (`192.168.0.x`) to communicate with the server.

---

## 2. Check Server IP (Ubuntu Server)

SSH into the server or run directly on it:

```bash
ip a
```

Look for the `enp1s0` interface — the server's LAN IP is the `inet` line:

```
2: enp1s0: ...
    inet 192.168.0.11/24 ...
```

For a quick one-liner:

```bash
hostname -I
```

---

## 3. Configure a Client PC (Windows) — Static IP

Do this on any Windows PC that cannot reach the server (wrong subnet or DHCP conflict).

### Step 1 — Open Network Connections

Press `Win + R`, type `ncpa.cpl`, press **Enter**.

### Step 2 — Open Ethernet Properties

Right-click the **Ethernet** adapter → **Properties**.

### Step 3 — Open IPv4 Settings

Double-click **Internet Protocol Version 4 (TCP/IPv4)**.

### Step 4 — Set Static IP

Select **"Use the following IP address"** and fill in:

| Field | Value |
|-------|-------|
| IP Address | `192.168.0.XX` *(pick an unused address — see §4)* |
| Subnet Mask | `255.255.255.0` |
| Default Gateway | `192.168.0.1` |
| Preferred DNS | `8.8.8.8` |
| Alternate DNS | `8.8.4.4` |

> **Recommended static addresses by role:**
> | Role | Suggested IP |
> |------|-------------|
> | Armory PC | `192.168.0.50` |
> | Admin / Dev PC | `192.168.0.82` *(already set)* |
> | Spare workstation | `192.168.0.51`–`192.168.0.60` |

### Step 5 — Apply

Click **OK** → **OK**. No reboot required.

---

## 4. Verify an IP Address is Free Before Assigning

From the **server**, ping the candidate address before assigning it:

```bash
ping -c 3 192.168.0.50
```

- **All timeouts** → address is free, safe to assign.
- **Replies received** → something is already using it — pick a different number.

---

## 5. Test Connectivity

After changing the IP on the client PC, open **Command Prompt** and run:

```cmd
ping 192.168.0.11
```

Expected output (success):
```
Reply from 192.168.0.11: bytes=32 time<1ms TTL=64
Reply from 192.168.0.11: bytes=32 time<1ms TTL=64
```

If you see `Request timed out` — double-check the IP, subnet mask, and gateway settings.

---

## 6. Access the Application

Once ping succeeds, open a browser on the client PC and navigate to:

```
http://192.168.0.11
```

For HTTPS (after SSL certificate is installed):

```
https://192.168.0.11
```

> **Self-signed certificate:** The first time you visit via HTTPS, the browser will warn about an untrusted certificate. Download and install the server's certificate from:
> ```
> http://192.168.0.11/download/ssl-cert/
> ```
> Then import it into your browser's/OS's trusted certificate store.

---

## 7. Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `Request timed out` on ping | Wrong subnet or firewall | Verify IP is `192.168.0.x`; check UFW on server |
| Ping works but browser fails | Nginx not running | SSH to server: `sudo systemctl status nginx` |
| `Connection refused` on port 80 | Gunicorn or Nginx down | `sudo systemctl restart armguard-gunicorn nginx` |
| Intermittent dropouts | DHCP lease conflict | Assign a static IP (this guide) |
| Cannot reach internet from client | Wrong gateway | Ensure Default Gateway is `192.168.0.1` |

### Check server services (run on server):

```bash
sudo systemctl status armguard-gunicorn
sudo systemctl status nginx
```

### Check UFW firewall (run on server):

```bash
sudo ufw status
```

Ports `80` (HTTP) and `443` (HTTPS) must show `ALLOW`.

---

## 8. Restore Armory PC to Original Settings

If you need to revert the armory PC back to its original network (e.g., reconnecting it to its old network at `192.168.1.x`), follow the steps below.

---

### Option A — Restore Original Static IP (back to 192.168.1.66)

Use this if the armory PC originally had a fixed IP on the `192.168.1.x` network.

1. Press `Win + R` → type `ncpa.cpl` → press **Enter**
2. Right-click **Ethernet** → **Properties**
3. Double-click **Internet Protocol Version 4 (TCP/IPv4)**
4. Select **"Use the following IP address"** and restore the original values:

| Field | Original Value |
|-------|---------------|
| IP Address | `192.168.1.66` |
| Subnet Mask | `255.255.255.0` |
| Default Gateway | `192.168.1.1` |
| Preferred DNS | `8.8.8.8` |
| Alternate DNS | `8.8.4.4` |

5. Click **OK** → **OK**

---

### Option B — Switch Back to Automatic IP (DHCP)

Use this if the armory PC originally obtained its IP automatically from a router.

1. Press `Win + R` → type `ncpa.cpl` → press **Enter**
2. Right-click **Ethernet** → **Properties**
3. Double-click **Internet Protocol Version 4 (TCP/IPv4)**
4. Select:
   - ✅ **Obtain an IP address automatically**
   - ✅ **Obtain DNS server address automatically**
5. Click **OK** → **OK**

The PC will request a new IP from the router's DHCP server within a few seconds.

---

### Verify the Restore

Open **Command Prompt** and run:

```cmd
ipconfig
```

Confirm the IP address matches what you restored. Then test the original network:

```cmd
ping 192.168.1.1
```

---

> **Note:** After restoring, the armory PC will **no longer be able to reach the ARMGUARD server** at `192.168.0.11` unless both networks are bridged by a router or a switch with inter-VLAN routing. To reconnect to ARMGUARD in the future, repeat §3 of this guide.

---

## 9. Reference — Server Network Config

```
Interface : enp1s0
IP Address: 192.168.0.11
Subnet    : 255.255.255.0  (/24)
Gateway   : 192.168.0.1
MAC       : ac:e2:d3:04:9b:70
```

## 10. Reference — Armory PC Original Config (before ARMGUARD setup)

```
Interface : Ethernet
IP Address: 192.168.1.66
Subnet    : 255.255.255.0  (/24)
Gateway   : 192.168.1.1
Hostname  : jay
```

## 11. Reference — Dev PC Config

```
Interface : Ethernet
IP Address: 192.168.0.82
Subnet    : 255.255.255.0  (/24)
Gateway   : 192.168.0.1
Hostname  : 9533RDS
```
