"""
Management command to clean up orphaned renditions and unused assets.
"""

from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from engine.models import Asset, AssetRendition


class Command(BaseCommand):
    help = 'Clean up orphaned renditions and optionally unused assets'

    def add_arguments(self, parser):
        parser.add_argument(
            '--orphaned-renditions',
            action='store_true',
            help='Delete renditions whose parent assets no longer exist or are deleted',
        )
        parser.add_argument(
            '--unused-assets',
            action='store_true',
            help='Delete assets that are not used in any posts',
        )
        parser.add_argument(
            '--soft-deleted',
            action='store_true',
            help='Include soft-deleted assets in cleanup',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )
        parser.add_argument(
            '--days',
            type=int,
            help='Only delete items older than N days (for unused assets)',
        )
        parser.add_argument(
            '--delete-files',
            action='store_true',
            help='Also delete files from R2 storage (prevents orphaned files)',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run')
        orphaned_renditions = options.get('orphaned_renditions')
        unused_assets = options.get('unused_assets')
        soft_deleted = options.get('soft_deleted')
        days = options.get('days')
        delete_files = options.get('delete_files')

        if not orphaned_renditions and not unused_assets:
            self.stdout.write(
                self.style.WARNING(
                    'Please specify at least one cleanup option:\n'
                    '  --orphaned-renditions: Delete orphaned renditions\n'
                    '  --unused-assets: Delete unused assets'
                )
            )
            return

        mode = 'DRY RUN' if dry_run else 'LIVE'
        file_mode = ' + R2 FILES' if delete_files and not dry_run else ''
        self.stdout.write(self.style.WARNING(f'\n=== {mode} MODE{file_mode} ===\n'))

        if delete_files and not dry_run:
            self.stdout.write(
                self.style.WARNING('  WARNING: Files will be permanently deleted from R2!\n')
            )

        # Clean up orphaned renditions
        if orphaned_renditions:
            self._cleanup_orphaned_renditions(dry_run, soft_deleted, delete_files)

        # Clean up unused assets
        if unused_assets:
            self._cleanup_unused_assets(dry_run, soft_deleted, days, delete_files)

        self.stdout.write(self.style.SUCCESS('\nCleanup complete!'))

    def _cleanup_orphaned_renditions(self, dry_run, soft_deleted, delete_files):
        """Delete renditions whose parent assets are deleted or don't exist."""
        self.stdout.write('\n--- Orphaned Renditions ---')

        # Find renditions with deleted parent assets
        if soft_deleted:
            # Include renditions of soft-deleted assets
            orphaned = AssetRendition.objects.filter(asset__is_deleted=True)
        else:
            # Only truly orphaned (parent doesn't exist in Asset table)
            all_renditions = AssetRendition.objects.all()
            valid_asset_ids = Asset.objects.values_list('id', flat=True)
            orphaned = all_renditions.exclude(asset_id__in=valid_asset_ids)

        count = orphaned.count()

        if count == 0:
            self.stdout.write('  No orphaned renditions found.')
            return

        # Show details
        self.stdout.write(f'  Found {count} orphaned rendition(s)')

        # Calculate storage size
        total_size = sum(r.file_size or 0 for r in orphaned)
        self.stdout.write(f'  Total size: {self._format_size(total_size)}')

        # Show some examples
        examples = orphaned[:5]
        if examples:
            self.stdout.write('\n  Examples:')
            for r in examples:
                try:
                    asset_key = r.asset.key if r.asset else 'N/A'
                    status = '(deleted)' if r.asset and r.asset.is_deleted else '(missing)'
                except Asset.DoesNotExist:
                    asset_key = 'N/A'
                    status = '(missing)'

                self.stdout.write(
                    f'    - {r.variant} {r.width}w for asset: {asset_key} {status}'
                )

        # Delete if not dry run
        if not dry_run:
            # Delete files from R2 first (before DB records are gone)
            files_deleted = 0
            if delete_files:
                for rendition in orphaned:
                    if rendition.file:
                        try:
                            file_name = rendition.file.name
                            rendition.file.delete(save=False)
                            files_deleted += 1
                            self.stdout.write(f'    Deleted R2: {file_name}')
                        except Exception as e:
                            self.stdout.write(
                                self.style.ERROR(f'    Failed to delete R2 file: {e}')
                            )

            deleted_count, _ = orphaned.delete()
            msg = f'\n  ✓ Deleted {deleted_count} orphaned rendition(s)'
            if delete_files:
                msg += f' and {files_deleted} R2 file(s)'
            self.stdout.write(self.style.SUCCESS(msg))
        else:
            msg = f'\n  Would delete {count} orphaned rendition(s)'
            if delete_files:
                msg += ' and their R2 files'
            self.stdout.write(self.style.WARNING(msg))

    def _cleanup_unused_assets(self, dry_run, soft_deleted, days, delete_files):
        """Delete assets that are not used in any posts."""
        self.stdout.write('\n--- Unused Assets ---')

        # Start with base queryset
        if soft_deleted:
            # Only soft-deleted assets
            queryset = Asset.all_objects.filter(is_deleted=True)
        else:
            # Active assets
            queryset = Asset.objects.all()

        # Find assets not used in posts
        unused = queryset.annotate(
            post_count=Count('postasset')
        ).filter(post_count=0)

        # Filter by age if specified
        if days:
            from django.utils import timezone
            from datetime import timedelta
            cutoff_date = timezone.now() - timedelta(days=days)
            unused = unused.filter(created_at__lt=cutoff_date)
            age_msg = f' older than {days} days'
        else:
            age_msg = ''

        count = unused.count()

        if count == 0:
            self.stdout.write(f'  No unused assets found{age_msg}.')
            return

        # Show details
        self.stdout.write(f'  Found {count} unused asset(s){age_msg}')

        # Calculate storage size
        total_size = sum(a.file_size or 0 for a in unused)
        self.stdout.write(f'  Total size: {self._format_size(total_size)}')

        # Group by type
        by_type = {}
        for asset in unused:
            asset_type = asset.asset_type
            by_type[asset_type] = by_type.get(asset_type, 0) + 1

        self.stdout.write('\n  Breakdown by type:')
        for asset_type, type_count in sorted(by_type.items()):
            self.stdout.write(f'    - {asset_type}: {type_count}')

        # Show some examples
        examples = unused[:5]
        if examples:
            self.stdout.write('\n  Examples:')
            for asset in examples:
                status = '(deleted)' if asset.is_deleted else ''
                self.stdout.write(
                    f'    - {asset.key} ({asset.asset_type}) {status}'
                )

        # Delete if not dry run
        if not dry_run:
            # Count renditions that will be cascade deleted
            rendition_count = sum(a.renditions.count() for a in unused)

            # Delete files from R2 first (before DB records are gone)
            asset_files_deleted = 0
            rendition_files_deleted = 0
            if delete_files:
                for asset in unused:
                    # Delete rendition files first
                    for rendition in asset.renditions.all():
                        if rendition.file:
                            try:
                                rendition.file.delete(save=False)
                                rendition_files_deleted += 1
                            except Exception as e:
                                self.stdout.write(
                                    self.style.ERROR(
                                        f'    Failed to delete rendition R2 file: {e}'
                                    )
                                )
                    # Delete asset file
                    if asset.file:
                        try:
                            file_name = asset.file.name
                            asset.file.delete(save=False)
                            asset_files_deleted += 1
                            self.stdout.write(f'    Deleted R2: {file_name}')
                        except Exception as e:
                            self.stdout.write(
                                self.style.ERROR(f'    Failed to delete R2 file: {e}')
                            )

            deleted_count, details = unused.delete()

            msg = (
                f'\n  ✓ Deleted {deleted_count} unused asset(s) '
                f'and {details.get("engine.AssetRendition", 0)} associated rendition(s)'
            )
            if delete_files:
                msg += f'\n  ✓ Deleted {asset_files_deleted} asset file(s) and {rendition_files_deleted} rendition file(s) from R2'
            self.stdout.write(self.style.SUCCESS(msg))
        else:
            rendition_count = sum(a.renditions.count() for a in unused)
            msg = (
                f'\n  Would delete {count} unused asset(s) '
                f'and {rendition_count} associated rendition(s)'
            )
            if delete_files:
                msg += ' and their R2 files'
            self.stdout.write(self.style.WARNING(msg))

    def _format_size(self, size_bytes):
        """Format bytes as human-readable size."""
        if size_bytes == 0:
            return '0 B'

        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f'{size_bytes:.2f} {unit}'
            size_bytes /= 1024.0

        return f'{size_bytes:.2f} TB'
