"""
Management command to sync sources from a Zotero library.

Usage:
    python manage.py sync_zotero                    # Incremental sync with attachments
    python manage.py sync_zotero --full              # Full re-import
    python manage.py sync_zotero --no-attachments    # Skip PDF downloads
    python manage.py sync_zotero --dry-run           # Preview without saving
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Sync sources from a Zotero library (top-level items only)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--full",
            action="store_true",
            help="Re-import all items (default: incremental since last sync)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be synced without saving changes",
        )
        parser.add_argument(
            "--no-attachments",
            action="store_true",
            help="Skip downloading PDF attachments from Zotero",
        )

    def handle(self, *args, **options):
        from engine.bibliography.zotero_sync import sync_zotero_library

        full = options["full"]
        dry_run = options["dry_run"]
        download_attachments = not options["no_attachments"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE\n"))

        mode = "full" if full else "incremental"
        self.stdout.write(f"Starting {mode} Zotero sync...\n")

        try:
            stats = sync_zotero_library(
                full=full,
                dry_run=dry_run,
                download_attachments=download_attachments,
            )
        except ValueError as e:
            self.stdout.write(self.style.ERROR(str(e)))
            return

        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(f"Created:       {stats['created']}")
        self.stdout.write(f"Updated:       {stats['updated']}")
        self.stdout.write(f"Skipped:       {stats['skipped']}")
        self.stdout.write(f"Attachments:   {stats['attachments_downloaded']}")
        self.stdout.write(f"Errors:        {stats['errors']}")
        self.stdout.write("=" * 50)

        if stats["error_details"]:
            self.stdout.write(self.style.WARNING("\nError details:"))
            for detail in stats["error_details"]:
                self.stdout.write(f"  - {detail}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING("\nDRY RUN COMPLETE: No changes saved")
            )
        else:
            total = stats["created"] + stats["updated"]
            self.stdout.write(
                self.style.SUCCESS(f"\nSync complete: {total} sources processed")
            )
