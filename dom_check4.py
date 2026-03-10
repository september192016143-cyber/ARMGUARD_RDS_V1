import os, sys
sys.path.insert(0, r'C:\Users\9533RDS\Desktop\hermosa\ARMGUARD_RDS_V1\project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'armguard.settings')
import django
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.filter(is_superuser=True).first() or User.objects.first()
print('User:', user)

c = Client()
c.force_login(user)

# Set the correct OTP session flag
session = c.session
session['_otp_step_done'] = True
session.save()

resp = c.get('/transactions/new/', HTTP_HOST='127.0.0.1:8000', follow=True)
print('GET status:', resp.status_code, 'redirects:', [(r[0], r[1]) for r in resp.redirect_chain])
body = resp.content.decode()

checks = [
    'txn-form',
    'tb_transaction_type',
    'tb_issuance_type',
    'tb_purpose',
    'tb_purpose_other',
    'btn-tr-preview',
    'btn-tr-submit',
    'issuance-wrapper',
    'purpose-wrapper',
    'par-doc-section',
    'notes-placeholder',
    'transaction_form.js',
    'novalidate',
    'data-personnel-url',
    'data-item-url',
    'data-tr-preview-url',
    'personnel-status-banner',
    'pistol-status-banner',
    'rifle-status-banner',
    'btn-tr-preview-close',
    'tr-preview-modal',
    'tr-preview-iframe',
    'fe_qr_personnel_id',
    'fe_qr_item_id',
]

print('\nDOM element check:')
for pat in checks:
    status = 'FOUND' if pat in body else '*** MISSING ***'
    print(f'  {status}: {pat}')

# Count inline scripts/handlers
import re
inline_scripts = len(re.findall(r'<script(?:[^s]|s(?!rc))', body))
inline_handlers = len(re.findall(r'\s(onclick|onchange|onfocus|onblur|onkeydown|onsubmit)\s*=', body))
print(f'\nInline <script> blocks (not src=): {inline_scripts}')
print(f'Inline event handlers: {inline_handlers}')

# Show the script tags
scripts = re.findall(r'<script[^>]*>', body)
print('\nAll <script> tags:')
for s in scripts:
    print(' ', s)
