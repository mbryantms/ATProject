"""
Management command to check source URLs for availability.

Usage:
    python manage.py check_source_urls                  # Check batch of 50
    python manage.py check_source_urls --batch-size 100 # Larger batch
    python manage.py check_source_urls --max-age 1      # Re-check after 1 day
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Check source URLs for availability and find archived versions"

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=50,
            help="Number of URLs to check (default: 50)",
        )
        parser.add_argument(
            "--max-age",
            type=int,
            default=7,
            help="Skip URLs checked within this many days (default: 7)",
        )

    def handle(self, *args, **options):
        from engine.bibliography.link_checker import check_source_urls
        from engine.models import Source

        batch_size = options["batch_size"]
        max_age = options["max_age"]

        total_with_url = Source.objects.exclude(url="").count()
        self.stdout.write(f"Sources with URLs: {total_with_url}")
        self.stdout.write(
            f"Checking up to {batch_size} URLs (max age: {max_age} days)\n"
        )

        stats = check_source_urls(batch_size=batch_size, max_age_days=max_age)

        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(f"Checked:   {stats['checked']}")
        self.stdout.write(f"OK:        {stats['ok']}")
        self.stdout.write(f"Redirect:  {stats['redirect']}")
        self.stdout.write(f"Broken:    {stats['broken']}")
        self.stdout.write(f"Archived:  {stats['archived']}")
        self.stdout.write("=" * 50)

        if stats["broken"] > 0:
            self.stdout.write(
                self.style.WARNING(f"\n{stats['broken']} broken URL(s) found")
            )

        self.stdout.write(
            self.style.SUCCESS(f"\nCheck complete: {stats['checked']} URLs checked")
        )
