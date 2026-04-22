"""
Management command to regenerate ``Post.content_html_cached`` and the
table-of-contents for existing posts.

Mirrors the ``regenerate_html_cache`` admin action but lets you run it
over the whole corpus from the shell — useful after markdown pipeline
changes (e.g. the image enhancer starting to emit a new inline attr)
when every cached render needs to be refreshed.
"""

from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from engine.markdown.extensions.toc_extractor import extract_toc_from_html
from engine.markdown.renderer import render_markdown
from engine.models import Post


class Command(BaseCommand):
    help = "Re-render Post.content_html_cached + table_of_contents for existing posts"

    def add_arguments(self, parser):
        parser.add_argument(
            "--post-id",
            type=int,
            help="Regenerate a single post by ID",
        )
        parser.add_argument(
            "--post-slug",
            type=str,
            help="Regenerate a single post by slug",
        )
        parser.add_argument(
            "--since",
            type=str,
            help="Only regenerate posts updated on/after YYYY-MM-DD",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count affected posts without writing",
        )

    def handle(self, *args, **options):
        post_id = options.get("post_id")
        post_slug = options.get("post_slug")
        since = options.get("since")
        dry_run = options.get("dry_run")

        qs = Post.objects.all()

        if post_id:
            qs = qs.filter(pk=post_id)
        if post_slug:
            qs = qs.filter(slug=post_slug)
        if since:
            try:
                since_date = datetime.strptime(since, "%Y-%m-%d").date()
            except ValueError as exc:
                raise CommandError(
                    f"--since must be YYYY-MM-DD (got {since!r})"
                ) from exc
            since_dt = timezone.make_aware(
                datetime.combine(since_date, datetime.min.time())
            )
            qs = qs.filter(updated_at__gte=since_dt)

        total = qs.count()
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"DRY RUN: would regenerate HTML for {total} post(s)"
                )
            )
            return

        regenerated = 0
        failed = 0
        for post in qs.iterator():
            try:
                context = {"post": post}
                html = render_markdown(post.content_markdown or "", context=context)
                post.content_html_cached = html
                try:
                    post.table_of_contents = extract_toc_from_html(html) or []
                except Exception:
                    post.table_of_contents = []
                post.save(update_fields=["content_html_cached", "table_of_contents"])
                regenerated += 1
            except Exception as exc:
                failed += 1
                self.stderr.write(
                    self.style.ERROR(
                        f"Failed to regenerate post {post.pk} ({post.slug!r}): {exc}"
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Regenerated {regenerated}/{total} post(s)"
                + (f"; {failed} failed" if failed else "")
            )
        )
