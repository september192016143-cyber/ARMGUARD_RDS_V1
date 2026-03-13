"""
Tests for armguard/apps/personnel/ views.
Covers list, detail, create, update, delete and permission enforcement.
"""
from django.test import TestCase, Client
from django.urls import reverse
from armguard.apps.personnel.models import Personnel
from armguard.tests.factories import make_user, make_admin_user, make_personnel, otp_login


class TestPersonnelListView(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user(username='pers_list_user', role='Armorer')
        make_personnel(afsn='AF000001')

    def test_requires_login(self):
        resp = self.client.get(reverse('personnel-list'))
        self.assertIn(resp.status_code, (301, 302))

    def test_armorer_sees_list(self):
        otp_login(self.client, self.user)
        resp = self.client.get(reverse('personnel-list'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'personnel/personnel_list.html')

    def test_search_returns_matching_personnel(self):
        otp_login(self.client, self.user)
        resp = self.client.get(reverse('personnel-list') + '?q=AF000001')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'AF000001')

    def test_search_no_match_returns_empty(self):
        otp_login(self.client, self.user)
        resp = self.client.get(reverse('personnel-list') + '?q=ZZZNOTEXISTING')
        self.assertEqual(resp.status_code, 200)
        qs = resp.context.get('personnel') or resp.context.get('object_list') or []
        self.assertEqual(len(qs), 0)


class TestPersonnelDetailView(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user(username='pers_det_user', role='Armorer')
        self.personnel = make_personnel(afsn='AF000002')

    def test_requires_login(self):
        resp = self.client.get(
            reverse('personnel-detail', args=[self.personnel.Personnel_ID])
        )
        self.assertIn(resp.status_code, (301, 302))

    def test_detail_renders_for_armorer(self):
        otp_login(self.client, self.user)
        resp = self.client.get(
            reverse('personnel-detail', args=[self.personnel.Personnel_ID])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'personnel/detail.html')
        self.assertIn('personnel', resp.context)

    def test_404_for_nonexistent_personnel(self):
        otp_login(self.client, self.user)
        resp = self.client.get(reverse('personnel-detail', args=['NONEXISTENT-ID-99']))
        self.assertEqual(resp.status_code, 404)


class TestPersonnelCreateView(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = make_admin_user(username='pers_create_admin')
        self.armorer = make_user(username='pers_create_arm', role='Armorer')

    def test_armorer_cannot_access_create(self):
        otp_login(self.client, self.armorer)
        resp = self.client.get(reverse('personnel-create'))
        self.assertIn(resp.status_code, (302, 403))

    def test_admin_can_access_create(self):
        otp_login(self.client, self.admin)
        resp = self.client.get(reverse('personnel-create'))
        self.assertEqual(resp.status_code, 200)


class TestPersonnelUpdateView(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = make_admin_user(username='pers_upd_admin')
        self.armorer = make_user(username='pers_upd_arm', role='Armorer')
        self.personnel = make_personnel(afsn='AF000003')

    def test_armorer_cannot_update(self):
        otp_login(self.client, self.armorer)
        resp = self.client.get(
            reverse('personnel-update', args=[self.personnel.Personnel_ID])
        )
        self.assertIn(resp.status_code, (302, 403))

    def test_admin_can_access_update(self):
        otp_login(self.client, self.admin)
        resp = self.client.get(
            reverse('personnel-update', args=[self.personnel.Personnel_ID])
        )
        self.assertEqual(resp.status_code, 200)


class TestPersonnelDeleteView(TestCase):
    def setUp(self):
        self.client = Client()
        self.system_admin = make_user(
            username='pers_del_sa',
            role='System Administrator',
            is_superuser=True,
            is_staff=True,
        )
        self.administrator = make_user(username='pers_del_adm', role='Administrator')
        self.personnel = make_personnel(afsn='AF000004')

    def test_administrator_cannot_delete(self):
        """Administrators may add/edit but not delete — only System Admins can."""
        otp_login(self.client, self.administrator)
        resp = self.client.post(
            reverse('personnel-delete', args=[self.personnel.Personnel_ID])
        )
        self.assertIn(resp.status_code, (302, 403))
        # Personnel record still exists
        self.assertTrue(
            Personnel.objects.filter(Personnel_ID=self.personnel.Personnel_ID).exists()
        )

    def test_system_admin_can_delete(self):
        otp_login(self.client, self.system_admin)
        resp = self.client.post(
            reverse('personnel-delete', args=[self.personnel.Personnel_ID])
        )
        # Should redirect after delete (302) or confirm page (200)
        self.assertIn(resp.status_code, (200, 302))
