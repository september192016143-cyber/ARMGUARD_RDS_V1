import os, sys
sys.path.insert(0, r'C:\Users\9533RDS\Desktop\hermosa\ARMGUARD_RDS_V1\project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'armguard.settings')
import django
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from armguard.apps.personnel.models import Personnel
from armguard.apps.inventory.models import Pistol

User = get_user_model()
user = User.objects.filter(is_superuser=True).first() or User.objects.first()
print('User:', user)

# Try to find valid data
personnel = Personnel.objects.first()
print('First personnel:', personnel)

c = Client()
c.force_login(user)

# Manually set the OTP verified session flag
session = c.session
session['_otp_verified'] = True
session.save()

resp = c.get('/transactions/new/', HTTP_HOST='127.0.0.1:8000', follow=True)
print('GET final status:', resp.status_code, 'redirects:', [(r[0], r[1]) for r in resp.redirect_chain])
body = resp.content.decode()
checks = ['txn-form', 'tb_transaction_type', 'transaction_form.js']
for pat in checks:
    print(f'  {"FOUND" if pat in body else "MISSING"}: {pat}')
