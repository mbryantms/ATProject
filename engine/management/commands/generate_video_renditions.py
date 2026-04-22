"""
Management command to transcode video assets into MP4 + WebM renditions
and extract poster frames. Mirrors generate_renditions.py for images but
drives the video_pipeline instead.
"""

from django.core.management.base import BaseCommand

from engine.models import Asset
from engine.video_pipeline import extract_poster, generate_video_renditions


class Command(BaseCommand):
    help = "Generate video renditions (poster + H.264 MP4 + VP9 WebM) for video assets"

    def add_arguments(self, parser):
        parser.add_argument(
            "--asset-key",
            type=str,
            help="Process only the asset with this key",
        )
        parser.add_argument(
            "--resolutions",
            type=str,
            default="720,1080",
            help="Comma-separated list of target heights (default: 720,1080)",
        )
        parser.add_argument(
            "--skip-poster",
            action="store_true",
            help="Skip poster-frame extraction (useful on retranscode runs)",
        )
        parser.add_argument(
            "--skip-renditions",
            action="store_true",
            help="Skip MP4/WebM transcoding (useful when only posters are needed)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List assets that would be processed without touching them",
        )

    def handle(self, *args, **options):
        asset_key = options.get("asset_key")
        resolutions_str = options.get("resolutions") or ""
        skip_poster = options.get("skip_poster")
        skip_renditions = options.get("skip_renditions")
        dry_run = options.get("dry_run")

        try:
            resolutions = tuple(
                int(r.strip()) for r in resolutions_str.split(",") if r.strip()
            )
        except ValueError as exc:
            self.stderr.write(self.style.ERROR(f"Invalid --resolutions: {exc}"))
            return

        qs = Asset.objects.videos()
        if asset_key:
            qs = qs.filter(key=asset_key)

        total = qs.count()
        if total == 0:
            self.stdout.write("No matching video assets.")
            return

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"DRY RUN: would process {total} asset(s)")
            )
            for a in qs:
                self.stdout.write(f"  - {a.key}")
            return

        for i, asset in enumerate(qs, 1):
            self.stdout.write(f"[{i}/{total}] {asset.key}")

            if not skip_poster:
                poster = extract_poster(asset)
                if poster:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  poster: {poster.width}x{poster.height} {poster.format}"
                        )
                    )
                else:
                    self.stdout.write("  poster: skipped or failed")

            if not skip_renditions:
                renditions = generate_video_renditions(asset, resolutions=resolutions)
                if renditions:
                    tags = ", ".join(
                        f"{r.preset}/{r.format}" for r in renditions
                    )
                    self.stdout.write(
                        self.style.SUCCESS(f"  renditions: {tags}")
                    )
                else:
                    self.stdout.write("  renditions: none generated")

        self.stdout.write(self.style.SUCCESS(f"\nProcessed {total} asset(s)"))
