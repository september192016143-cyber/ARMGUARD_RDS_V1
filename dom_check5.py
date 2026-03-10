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

# Find inline script blocks with context
print('=== INLINE SCRIPT BLOCKS ===')
for m in re.finditer(r'<script(?![^>]*src)[^>]*>(.*?)</script>', body, re.DOTALL):
    snippet = m.group(0)[:500]
    print(repr(snippet))
    print()

# Find inline event handlers with context
print('=== INLINE EVENT HANDLERS ===')
for m in re.finditer(r'.{0,80}(onclick|onchange|onfocus|onblur|onkeydown|onsubmit)=["\'][^"\']{0,100}["\'].{0,80}', body):
    print(repr(m.group(0)))
    print()
