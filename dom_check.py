import os, sys
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
resp = c.get('/transactions/new/', HTTP_HOST='127.0.0.1:8000')
body = resp.content.decode()

checks = [
    'tb_transaction_type',
    'tb_issuance_type',
    'tb_purpose',
    'tb_purpose_other',
    'btn-tr-preview',
    'btn-tr-submit',
    'txn-form',
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
]

print('Status:', resp.status_code)
for pat in checks:
    status = 'FOUND' if pat in body else '*** MISSING ***'
    print(f'  {status}: {pat}')
