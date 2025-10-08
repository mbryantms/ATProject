"""
Management command to rebuild internal link (backlinks) records.

This command extracts internal links from post markdown content and creates/updates
InternalLink records. Useful for initial setup or after bulk content changes.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from engine.models import Post, InternalLink
from engine.links.extractor import update_post_links, get_link_statistics


class Command(BaseCommand):
    help = 'Rebuild InternalLink records by parsing post content'

    def add_arguments(self, parser):
        parser.add_argument(
            '--post-id',
            type=int,
            help='Rebuild links for specific post by ID',
        )
        parser.add_argument(
            '--post-slug',
            type=str,
            help='Rebuild links for specific post by slug',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear all existing InternalLink records before rebuilding',
        )
        parser.add_argument(
            '--status',
            type=str,
            choices=['draft', 'scheduled', 'published', 'archived'],
            default='published',
            help='Post status to process (default: published)',
        )
        parser.add_argument(
            '--all-statuses',
            action='store_true',
            help='Process posts of all statuses (overrides --status)',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed progress and statistics',
        )
        parser.add_argument(
            '--stats',
            action='store_true',
            help='Show link statistics after rebuild',
        )

    def handle(self, *args, **options):
        post_id = options.get('post_id')
        post_slug = options.get('post_slug')
        dry_run = options.get('dry_run')
        clear = options.get('clear')
        status = options.get('status')
        all_statuses = options.get('all_statuses')
        verbose = options.get('verbose')
        show_stats = options.get('stats')

        # Dry run mode warning
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE: No changes will be saved\n')
            )

        # Clear existing links if requested
        if clear and not dry_run:
            self.stdout.write('Clearing all existing InternalLink records...')
            with transaction.atomic():
                count = InternalLink.all_objects.all().delete()[0]
            self.stdout.write(
                self.style.SUCCESS(f'Cleared {count} InternalLink records\n')
            )

        # Get posts to process
        if post_id:
            posts = Post.objects.filter(id=post_id)
            if not posts.exists():
                self.stdout.write(
                    self.style.ERROR(f'No post found with ID: {post_id}')
                )
                return
        elif post_slug:
            posts = Post.objects.filter(slug=post_slug)
            if not posts.exists():
                self.stdout.write(
                    self.style.ERROR(f'No post found with slug: {post_slug}')
                )
                return
        else:
            # Process all posts with specified status
            if all_statuses:
                posts = Post.objects.all()
                self.stdout.write('Processing posts with all statuses...\n')
            else:
                posts = Post.objects.filter(status=status)
                self.stdout.write(f'Processing {status} posts...\n')

        total = posts.count()
        self.stdout.write(f'Found {total} post(s) to process\n')

        # Track overall statistics
        total_stats = {
            'posts_processed': 0,
            'links_found': 0,
            'links_created': 0,
            'links_updated': 0,
            'links_deleted': 0,
            'links_failed': 0,
            'failed_slugs': set()
        }

        # Process each post
        for i, post in enumerate(posts, 1):
            if verbose:
                self.stdout.write(f'\n[{i}/{total}] Processing: {post.title} ({post.slug})')
            else:
                # Show progress every 10 posts
                if i % 10 == 0 or i == total:
                    self.stdout.write(f'Progress: {i}/{total} posts processed')

            # Update links for this post
            try:
                stats = update_post_links(post, dry_run=dry_run)

                # Accumulate stats
                total_stats['posts_processed'] += 1
                total_stats['links_found'] += stats['links_found']
                total_stats['links_created'] += stats['links_created']
                total_stats['links_updated'] += stats['links_updated']
                total_stats['links_deleted'] += stats['links_deleted']
                total_stats['links_failed'] += stats['links_failed']
                total_stats['failed_slugs'].update(stats['failed_slugs'])

                if verbose:
                    self.stdout.write(
                        f"  Found: {stats['links_found']}, "
                        f"Created: {stats['links_created']}, "
                        f"Updated: {stats['links_updated']}, "
                        f"Deleted: {stats['links_deleted']}"
                    )

                    if stats['links_failed'] > 0:
                        self.stdout.write(
                            self.style.WARNING(
                                f"  Failed to resolve {stats['links_failed']} link(s): "
                                f"{', '.join(stats['failed_slugs'])}"
                            )
                        )

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'  Error processing post {post.slug}: {str(e)}')
                )
                continue

        # Print summary
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write('SUMMARY')
        self.stdout.write('=' * 60)
        self.stdout.write(f"Posts processed:   {total_stats['posts_processed']}")
        self.stdout.write(f"Links found:       {total_stats['links_found']}")
        self.stdout.write(f"Links created:     {total_stats['links_created']}")
        self.stdout.write(f"Links updated:     {total_stats['links_updated']}")
        self.stdout.write(f"Links deleted:     {total_stats['links_deleted']}")

        if total_stats['links_failed'] > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"Links failed:      {total_stats['links_failed']}"
                )
            )
            if verbose:
                self.stdout.write(
                    self.style.WARNING(
                        f"Failed slugs:      {', '.join(sorted(total_stats['failed_slugs']))}"
                    )
                )

        self.stdout.write('=' * 60)

        # Show link statistics if requested
        if show_stats and not dry_run:
            self.stdout.write('\nLINK STATISTICS')
            self.stdout.write('=' * 60)

            try:
                link_stats = get_link_statistics()

                self.stdout.write(f"Total links:              {link_stats['total_links']}")
                self.stdout.write(f"Total posts:              {link_stats['total_posts']}")
                self.stdout.write(
                    f"Average links per post:   {link_stats['average_links_per_post']:.2f}"
                )
                self.stdout.write(
                    f"Orphaned posts:           {link_stats['orphaned_posts_count']}"
                )
                self.stdout.write(
                    f"Broken links:             {link_stats['broken_links_count']}"
                )

                if link_stats['most_linked_posts']:
                    self.stdout.write('\nMost linked-to posts:')
                    for post in link_stats['most_linked_posts'][:5]:
                        self.stdout.write(
                            f"  - {post['title']} ({post['slug']}): "
                            f"{post['backlink_count']} backlinks"
                        )

                if link_stats['most_linking_posts']:
                    self.stdout.write('\nPosts with most outgoing links:')
                    for post in link_stats['most_linking_posts'][:5]:
                        self.stdout.write(
                            f"  - {post['title']} ({post['slug']}): "
                            f"{post['outgoing_count']} outgoing links"
                        )

                self.stdout.write('=' * 60)

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Error generating statistics: {str(e)}')
                )

        # Final message
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    '\nDRY RUN COMPLETE: No changes were saved'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nREBUILD COMPLETE: Processed {total_stats["posts_processed"]} posts'
                )
            )