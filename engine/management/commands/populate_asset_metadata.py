"""
Management command to populate metadata for existing assets.
"""

from django.core.management.base import BaseCommand
from engine.models import Asset
from engine.utils import populate_asset_metadata


class Command(BaseCommand):
    help = "Populate metadata (dimensions, MIME type, file size) for existing assets"

    def add_arguments(self, parser):
        parser.add_argument(
            '--key',
            type=str,
            help='Populate metadata for a specific asset key',
        )
        parser.add_argument(
            '--type',
            type=str,
            choices=['image', 'video', 'audio', 'document', 'data'],
            help='Populate metadata for assets of a specific type',
        )

    def handle(self, *args, **options):
        key = options.get('key')
        asset_type = options.get('type')

        if key:
            # Process single asset
            try:
                asset = Asset.objects.get(key=key)
                self.stdout.write(f"Processing asset: {asset.key}")
                populate_asset_metadata(Asset, asset, created=False)
                self.stdout.write(self.style.SUCCESS(f"✓ Populated metadata for {asset.key}"))
            except Asset.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Asset with key '{key}' not found"))
                return

        else:
            # Process all assets (or filtered by type)
            queryset = Asset.objects.filter(is_deleted=False)

            if asset_type:
                queryset = queryset.filter(asset_type=asset_type)

            total = queryset.count()
            self.stdout.write(f"Processing {total} asset(s)...")

            for i, asset in enumerate(queryset, 1):
                self.stdout.write(f"[{i}/{total}] Processing: {asset.key} ({asset.asset_type})")
                try:
                    populate_asset_metadata(Asset, asset, created=False)
                    self.stdout.write(self.style.SUCCESS(f"  ✓ Populated metadata"))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  ✗ Error: {e}"))

            self.stdout.write(self.style.SUCCESS(f"\nCompleted! Processed {total} asset(s)"))
