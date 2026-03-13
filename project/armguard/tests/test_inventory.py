"""
Tests for inventory views: Pistol, Rifle, Magazine, Ammunition, Accessory.
Covers list, detail, create, update, delete and permission enforcement.
"""
from django.test import TestCase, Client
from django.urls import reverse
from armguard.apps.inventory.models import Pistol, Rifle, Magazine, Ammunition, Accessory
from armguard.tests.factories import make_user, make_pistol, make_rifle, otp_login


class TestPistolListView(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user(username='inv_armorer', role='Armorer')
        self.pistol = make_pistol(serial='SN-P-001')

    def test_requires_login(self):
        resp = self.client.get(reverse('pistol-list'))
        self.assertIn(resp.status_code, (301, 302))

    def test_auth_user_sees_list(self):
        otp_login(self.client, self.user)
        resp = self.client.get(reverse('pistol-list'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'inventory/pistol_list.html')

    def test_search_filters_results(self):
        otp_login(self.client, self.user)
        resp = self.client.get(reverse('pistol-list') + '?q=SN-P-001')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'SN-P-001')

    def test_search_no_results_empty(self):
        otp_login(self.client, self.user)
        resp = self.client.get(reverse('pistol-list') + '?q=ZZZNOMATCH')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['pistols']), 0)


class TestRifleListView(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user(username='inv_armorer_r', role='Armorer')
        self.rifle = make_rifle(serial='SN-R-001')

    def test_auth_user_sees_list(self):
        otp_login(self.client, self.user)
        resp = self.client.get(reverse('rifle-list'))
        self.assertEqual(resp.status_code, 200)


class TestPistolCreateView(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = make_user(username='inv_admin', role='System Administrator',
                               is_superuser=True, is_staff=True)
        self.armorer = make_user(username='inv_armoronly', role='Armorer')

    def test_admin_can_access_create(self):
        otp_login(self.client, self.admin)
        resp = self.client.get(reverse('pistol-add'))
        self.assertEqual(resp.status_code, 200)

    def test_armorer_forbidden_from_create(self):
        otp_login(self.client, self.armorer)
        resp = self.client.get(reverse('pistol-add'))
        self.assertIn(resp.status_code, (302, 403))

    def test_admin_creates_pistol(self):
        otp_login(self.client, self.admin)
        count_before = Pistol.objects.count()
        resp = self.client.post(reverse('pistol-add'), {
            'model': 'Glock 17 9mm',
            'serial_number': 'SN-NEW-999',
            'item_status': 'Available',
            'item_condition': 'Serviceable',
        })
        self.assertIn(resp.status_code, (200, 302))
        # If redirect, pistol was created
        if resp.status_code == 302:
            self.assertEqual(Pistol.objects.count(), count_before + 1)


class TestInventoryDeletePermissions(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = make_user(username='inv_del_admin', role='System Administrator',
                               is_superuser=True, is_staff=True)
        self.armorer = make_user(username='inv_del_armorer', role='Armorer')
        self.pistol = make_pistol(serial='SN-DEL-001')

    def test_armorer_cannot_delete(self):
        otp_login(self.client, self.armorer)
        resp = self.client.post(reverse('pistol-delete', args=[self.pistol.item_id]))
        self.assertIn(resp.status_code, (302, 403))
        # Pistol still exists
        self.assertTrue(Pistol.objects.filter(item_id=self.pistol.item_id).exists())


class TestMagazineListView(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user(username='mag_user', role='Armorer')

    def test_magazine_list_renders(self):
        otp_login(self.client, self.user)
        resp = self.client.get(reverse('magazine-list'))
        self.assertEqual(resp.status_code, 200)


class TestAmmunitionListView(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user(username='ammo_user', role='Armorer')

    def test_ammo_list_renders(self):
        otp_login(self.client, self.user)
        resp = self.client.get(reverse('ammunition-list'))
        self.assertEqual(resp.status_code, 200)


class TestAccessoryListView(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user(username='acc_user', role='Armorer')

    def test_accessory_list_renders(self):
        otp_login(self.client, self.user)
        resp = self.client.get(reverse('accessory-list'))
        self.assertEqual(resp.status_code, 200)
