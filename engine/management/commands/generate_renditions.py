"""
Management command to generate image renditions for assets.
"""

from django.core.management.base import BaseCommand
from engine.models import Asset
from engine.utils import generate_asset_renditions


class Command(BaseCommand):
    help = 'Generate responsive image renditions for all image assets'

    def add_arguments(self, parser):
        parser.add_argument(
            '--asset-key',
            type=str,
            help='Generate renditions for specific asset by key',
        )
        parser.add_argument(
            '--widths',
            type=str,
            help='Comma-separated list of widths (default: 400,800,1200,1600)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Regenerate even if renditions already exist',
        )

    def handle(self, *args, **options):
        asset_key = options.get('asset_key')
        widths_str = options.get('widths')
        force = options.get('force')

        # Parse widths
        widths = None
        if widths_str:
            widths = [int(w.strip()) for w in widths_str.split(',')]

        # Get assets to process
        if asset_key:
            assets = Asset.objects.filter(key=asset_key, asset_type=Asset.IMAGE)
            if not assets.exists():
                self.stdout.write(
                    self.style.ERROR(f'No image asset found with key: {asset_key}')
                )
                return
        else:
            assets = Asset.objects.filter(asset_type=Asset.IMAGE, is_deleted=False)

        total = assets.count()
        self.stdout.write(f'Processing {total} image asset(s)...\n')

        for i, asset in enumerate(assets, 1):
            self.stdout.write(f'[{i}/{total}] Processing: {asset.key}')

            # Delete existing renditions if force flag is set
            if force:
                deleted_count = asset.renditions.all().delete()[0]
                if deleted_count > 0:
                    self.stdout.write(f'  Deleted {deleted_count} existing rendition(s)')

            # Generate renditions
            renditions = generate_asset_renditions(asset, widths=widths)

            if renditions:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  Generated {len(renditions)} rendition(s): '
                        f'{", ".join([str(r.width) + "w" for r in renditions])}'
                    )
                )
            else:
                self.stdout.write('  No new renditions generated')

        self.stdout.write(
            self.style.SUCCESS(f'\nCompleted! Processed {total} asset(s)')
        )
