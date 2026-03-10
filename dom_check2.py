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
resp = c.get('/transactions/new/', HTTP_HOST='127.0.0.1:8000', follow=True)
body = resp.content.decode()

# Show where we ended up
print('Final status:', resp.status_code)
print('Final URL chain:', [(r[0], r[1]) for r in resp.redirect_chain])

checks = [
    'tb_transaction_type',
    'tb_issuance_type',
    'tb_purpose',
    'btn-tr-preview',
    'btn-tr-submit',
    'txn-form',
    'issuance-wrapper',
    'transaction_form.js',
    'novalidate',
]

for pat in checks:
    status = 'FOUND' if pat in body else '*** MISSING ***'
    print(f'  {status}: {pat}')
