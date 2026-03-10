import django, os, sys
sys.path.insert(0, r'C:\Users\9533RDS\Desktop\hermosa\ARMGUARD_RDS_V1\project')
os.environ['DJANGO_SETTINGS_MODULE'] = 'armguard.settings.development'
django.setup()

from django.test import RequestFactory
from django.contrib.auth import get_user_model
from armguard.apps.transactions.views import TransactionCreateView
from django.contrib.messages.storage.fallback import FallbackStorage

User = get_user_model()
user = User.objects.filter(is_superuser=True).first()
if not user:
    print('No superuser found')
else:
    print('User:', user)
    factory = RequestFactory()
    req = factory.get('/transactions/new/')
    req.user = user
    req.session = {}
    req._messages = FallbackStorage(req)
    req.session['_otp_user_id'] = user.pk
    try:
        resp = TransactionCreateView.as_view()(req)
        print('Status:', resp.status_code)
        if hasattr(resp, 'render'):
            resp.render()
            content = resp.content.decode('utf-8')
            checks = [
                ('transaction_form.js', 'transaction_form.js'),
                ('txn-form', 'id="txn-form"'),
                ('data-personnel-url', 'data-personnel-url'),
                ('data-item-url', 'data-item-url'),
                ('data-tr-preview-url', 'data-tr-preview-url'),
                ('btn-tr-submit', 'btn-tr-submit'),
                ('btn-tr-preview', 'btn-tr-preview'),
                ('defer', 'defer'),
            ]
            for label, needle in checks:
                status = 'FOUND' if needle in content else '*** MISSING ***'
                print(f'{label}: {status}')
        else:
            print('Redirect to:', resp.get('Location', '?'))
    except Exception as e:
        import traceback
        print('ERROR:', e)
        traceback.print_exc()
