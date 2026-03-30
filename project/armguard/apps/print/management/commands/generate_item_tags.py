"""
Management command: generate_item_tags
=======================================
Generate (or regenerate) PNG tag files for all inventory items.

Usage:
    python manage.py generate_item_tags            # generate only missing tags
    python manage.py generate_item_tags --force    # regenerate ALL tags
    python manage.py generate_item_tags --item IP-GL17-AFP052973   # single item
"""

from django.core.management.base import BaseCommand, CommandError
from armguard.apps.inventory.models import Pistol, Rifle


class Command(BaseCommand):
    help = 'Generate item tag PNGs for inventory items'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force', action='store_true',
            help='Regenerate even if a tag PNG already exists on disk'
        )
        parser.add_argument(
            '--item', type=str, default=None,
            help='Generate tag for a single item_id only'
        )

    def handle(self, *args, **options):
        import os
        from django.conf import settings
        from utils.item_tag_generator import generate_item_tag

        force   = options['force']
        item_id = options['item']

        tag_dir = os.path.join(settings.MEDIA_ROOT, 'item_id_tags')
        existing = set(os.listdir(tag_dir)) if os.path.isdir(tag_dir) else set()

        if item_id:
            # Single-item mode
            item = None
            try:
                item = Pistol.objects.get(item_id=item_id)
            except Pistol.DoesNotExist:
                try:
                    item = Rifle.objects.get(item_id=item_id)
                except Rifle.DoesNotExist:
                    raise CommandError(f'Item not found: {item_id!r}')
            try:
                result = generate_item_tag(item)
                self.stdout.write(self.style.SUCCESS(
                    f'OK  {item.item_id}  →  {result["tag"]}'
                ))
            except Exception as exc:
                self.stdout.write(self.style.ERROR(
                    f'FAIL  {item.item_id}  →  {type(exc).__name__}: {exc}'
                ))
            return

        # Bulk mode
        items = list(Pistol.objects.all()) + list(Rifle.objects.all())
        generated = skipped = 0
        errors = []

        for item in items:
            filename = f'{item.item_id}.png'
            if not force and filename in existing:
                skipped += 1
                self.stdout.write(f'SKIP  {item.item_id}')
                continue
            try:
                result = generate_item_tag(item)
                generated += 1
                self.stdout.write(self.style.SUCCESS(f'OK    {item.item_id}'))
            except Exception as exc:
                errors.append((item.item_id, exc))
                self.stdout.write(self.style.ERROR(
                    f'FAIL  {item.item_id}  →  {type(exc).__name__}: {exc}'
                ))

        self.stdout.write('')
        self.stdout.write(f'Generated: {generated}  Skipped: {skipped}  Errors: {len(errors)}')
        if errors:
            self.stdout.write(self.style.ERROR('--- Error details ---'))
            for eid, exc in errors:
                self.stdout.write(self.style.ERROR(f'  {eid}: {type(exc).__name__}: {exc}'))
