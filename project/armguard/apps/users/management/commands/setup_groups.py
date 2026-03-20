"""
Management command: setup_groups
Creates (or updates) the three ArmGuard role Groups.

Run once after deploy:
    python manage.py setup_groups

Groups and their effect on UserProfile when assigned:
  Armorer                   → role='Armorer',        perm_can_add=False, perm_can_edit=False
  Administrator — View Only → role='Administrator',  perm_can_add=False, perm_can_edit=False
  Administrator — Edit & Add→ role='Administrator',  perm_can_add=True,  perm_can_edit=True

System Administrator is managed via is_superuser or by setting role directly —
no Group is needed for that level.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group


ARMGUARD_GROUPS = [
    'Armorer',
    'Administrator \u2014 View Only',
    'Administrator \u2014 Edit & Add',
]


class Command(BaseCommand):
    help = 'Create ArmGuard role Groups (Armorer, Administrator variants).'

    def handle(self, *args, **options):
        for name in ARMGUARD_GROUPS:
            group, created = Group.objects.get_or_create(name=name)
            status = 'created' if created else 'already exists'
            self.stdout.write(f'  {name!r} \u2014 {status}')
        self.stdout.write(self.style.SUCCESS('ArmGuard groups ready.'))
