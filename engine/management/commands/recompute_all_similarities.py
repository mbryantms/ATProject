"""
Management command to rebuild PostSimilarity rows for all published posts.

Useful for initial population after the feature lands, after weight changes,
or to recover from any missed signal. Calls the Celery task synchronously
so output is deterministic.
"""

from django.core.management.base import BaseCommand

from engine.models import Post, PostSimilarity
from engine.tasks import recompute_similarity_for_post


class Command(BaseCommand):
    help = "Recompute the PostSimilarity table for all published posts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--post",
            type=str,
            help="Limit to a single post by slug.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be processed without writing.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print per-post results.",
        )

    def handle(self, *args, **options):
        slug = options.get("post")
        dry_run = options.get("dry_run")
        verbose = options.get("verbose")

        qs = Post.objects.filter(
            status=Post.Status.PUBLISHED, is_deleted=False
        )
        if slug:
            qs = qs.filter(slug=slug)
            if not qs.exists():
                self.stdout.write(
                    self.style.ERROR(f"No published post with slug: {slug}")
                )
                return

        total = qs.count()
        self.stdout.write(f"Found {total} published post(s) to process.")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — nothing will be written."))

        total_rows = 0
        for i, post in enumerate(qs.iterator(), 1):
            if dry_run:
                self.stdout.write(f"  [{i}/{total}] would recompute: {post.slug}")
                continue
            async_result = recompute_similarity_for_post.apply(args=(post.pk,))
            result = async_result.result if async_result else {}
            rows = result.get("rows", 0) if isinstance(result, dict) else 0
            total_rows += rows
            if verbose:
                message = (
                    result.get("message", "ok") if isinstance(result, dict) else "ok"
                )
                self.stdout.write(
                    f"  [{i}/{total}] {post.slug}: {rows} rows ({message})"
                )
            elif i % 25 == 0 or i == total:
                self.stdout.write(f"  progress: {i}/{total}")

        if not dry_run:
            table_total = PostSimilarity.objects.count()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Done. Wrote {total_rows} new rows; "
                    f"table now has {table_total} total rows."
                )
            )
