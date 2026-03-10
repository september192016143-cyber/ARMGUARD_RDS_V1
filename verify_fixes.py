import os, sys, re
sys.path.insert(0, r'C:\Users\9533RDS\Desktop\hermosa\ARMGUARD_RDS_V1\project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'armguard.settings')
import django
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.filter(is_superuser=True).first() or User.objects.first()

c = Client()
c.force_login(user)
session = c.session
session['_otp_step_done'] = True
session.save()

resp = c.get('/transactions/new/', HTTP_HOST='127.0.0.1:8000')
body = resp.content.decode()

print('Status:', resp.status_code)

# Check no inline event handler attributes remain (except any we intentionally kept)
handlers = re.findall(r'(onclick|onchange|onfocus|onblur|onkeydown|onsubmit)\s*=\s*"([^"]{1,100})"', body)
if handlers:
    print(f'\nInline handlers ({len(handlers)}):')
    for attr, val in handlers:
        print(f'  {attr}="{val}"')
else:
    print('\nNo inline event handlers (PASS)')

# Check sidebar toggle button
print('\nsidebar-toggle id:', 'FOUND' if 'id="sidebar-toggle"' in body else 'MISSING')
print('onclick="toggleSidebar":', 'PRESENT (CSP VIOLATION)' if 'onclick="toggleSidebar' in body else 'ABSENT (PASS)')

# Check notification button
print('\nnotif-btn id:', 'FOUND' if 'id="notif-btn"' in body else 'MISSING')
print('onclick="toggleNotif":', 'PRESENT (CSP VIOLATION)' if 'onclick="toggleNotif' in body else 'ABSENT (PASS)')

# Check notif-clear
print('\nnotif-clear-btn id:', 'FOUND' if 'id="notif-clear-btn"' in body else 'MISSING')
print('onclick="clearNotifs":', 'PRESENT (CSP VIOLATION)' if 'onclick="clearNotifs' in body else 'ABSENT (PASS)')

# Verify nav-group-header no longer has onclick
print('\nnav-group-header onclick REMOVED:', 'PASS' if "nav-group-header\" onclick" not in body else 'FAIL - still present')
print('nav-group-header element:', 'FOUND' if 'nav-group-header' in body else 'MISSING')

# All key elements for transaction form
txn_elements = ['txn-form', 'tb_transaction_type', 'btn-tr-submit', 'transaction_form.js']
print('\nTransaction form elements:')
for e in txn_elements:
    print(f'  {"FOUND" if e in body else "MISSING"}: {e}')
