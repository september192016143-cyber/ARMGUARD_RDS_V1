"""
Management command: backfill_user_groups

Assigns existing users to the correct ArmGuard role Group based on their
current UserProfile.role + perm flags.  Safe to run multiple times.

Logic:
  is_superuser                                    → no group (role syncs via post_save)
  role='System Administrator'                     → no group (treat same as superuser)
  role='Administrator', can_add=True, can_edit=True → Administrator — Edit & Add
  role='Administrator', otherwise                 → Administrator — View Only
  role='Armorer'                                  → Armorer

Run on the server after deploying the Groups feature:
    python manage.py backfill_user_groups

Pass --dry-run to preview without making any changes.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group


def _target_group(user):
    """Return the Group name that best matches this user's current profile, or None."""
    if user.is_superuser:
        return None  # superuser needs no group — role is set via post_save signal

    try:
        profile = user.profile
    except Exception:
        return None

    role     = profile.role or ''
    can_add  = bool(getattr(profile, 'perm_can_add',  False))
    can_edit = bool(getattr(profile, 'perm_can_edit', False))

    if role == 'System Administrator':
        return None  # same as superuser — managed directly
    if role == 'Administrator':
        return 'Administrator \u2014 Edit & Add' if (can_add and can_edit) else 'Administrator \u2014 View Only'
    if role == 'Armorer':
        return 'Armorer'
    return None


class Command(BaseCommand):
    help = 'Assign existing users to ArmGuard role Groups based on their current UserProfile.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would happen without making any changes.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        User    = get_user_model()

        # Pre-load all three groups once
        groups = {g.name: g for g in Group.objects.filter(name__in=[
            'Armorer',
            'Administrator \u2014 View Only',
            'Administrator \u2014 Edit & Add',
        ])}

        if len(groups) < 3:
            self.stderr.write(self.style.ERROR(
                'One or more ArmGuard groups are missing. '
                'Run "python manage.py setup_groups" first.'
            ))
            return

        assigned = skipped = superusers = 0

        for user in User.objects.select_related('profile').all():
            target_name = _target_group(user)

            if target_name is None:
                superusers += 1
                self.stdout.write(f'  [skip]   {user.username!r} — superuser / System Administrator')
                continue

            target_group   = groups[target_name]
            current_groups = set(user.groups.values_list('name', flat=True))

            if current_groups == {target_name}:
                skipped += 1
                self.stdout.write(f'  [ok]     {user.username!r} — already in {target_name!r}')
                continue

            if dry_run:
                self.stdout.write(
                    f'  [DRY]    {user.username!r} → {target_name!r}'
                    + (f'  (was: {", ".join(sorted(current_groups))})' if current_groups else '')
                )
            else:
                user.groups.set([target_group])   # triggers m2m_changed → profile sync
                assigned += 1
                self.stdout.write(f'  [assign] {user.username!r} → {target_name!r}')

        if dry_run:
            self.stdout.write(self.style.WARNING('\nDry run — no changes made.'))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'\nDone. {assigned} assigned, {skipped} already correct, {superusers} skipped (superuser).'
            ))
