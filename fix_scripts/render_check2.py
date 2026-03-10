import sys
sys.path.insert(0, r'C:\Users\9533RDS\Desktop\hermosa\ARMGUARD_RDS_V1\project')
import django, os
os.environ['DJANGO_SETTINGS_MODULE'] = 'armguard.settings.development'
django.setup()
from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.filter(is_superuser=True).first()
c = Client(enforce_csrf_checks=False)
c.force_login(user)
session = c.session
session['_otp_step_done'] = True
session.save()

resp = c.get('/transactions/new/', HTTP_HOST='127.0.0.1:8000', SERVER_NAME='127.0.0.1', SERVER_PORT='8000')
print('Status:', resp.status_code)
if resp.status_code == 200:
    content = resp.content.decode('utf-8')
    checks = [
        ('transaction_form.js', 'transaction_form.js'),
        ('txn-form',            'id=\x22txn-form\x22'),
        ('data-personnel-url',  'data-personnel-url'),
        ('data-item-url',       'data-item-url'),
        ('data-tr-preview-url', 'data-tr-preview-url'),
        ('btn-tr-submit',       'btn-tr-submit'),
        ('btn-tr-preview',      'btn-tr-preview'),
        ('defer',               'defer'),
        ('script src',          '<script src'),
        ('name=personnel',      'name=\x22personnel\x22'),
        ('load static',         '{% load static %}'),
    ]
    for label, needle in checks:
        status = 'FOUND' if needle in content else '*** MISSING ***'
        print(f'{label}: {status}')
    # Find script tag
    import re
    scripts = re.findall(r'<script[^>]*>', content)
    print('\nScript tags found:')
    for s in scripts:
        print(' ', s)
elif resp.status_code in (301, 302):
    print('Redirect to:', resp.get('Location', '?'))
