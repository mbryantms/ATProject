# Generated manually to add rich Markdown authoring support to Page.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("engine", "0043_postfurtherreading"),
    ]

    operations = [
        migrations.AddField(
            model_name="page",
            name="first_line_caps",
            field=models.BooleanField(
                default=False,
                help_text="Style the first line of the opening paragraph with small caps.",
                verbose_name="Intro Paragraph Small Caps",
            ),
        ),
        migrations.AddField(
            model_name="page",
            name="show_toc",
            field=models.BooleanField(
                default=False,
                help_text="Display a generated table of contents above the page body.",
                verbose_name="Show Table of Contents",
            ),
        ),
        migrations.AddField(
            model_name="page",
            name="table_of_contents",
            field=models.JSONField(
                blank=True,
                default=list,
                editable=False,
                help_text="Heading structure extracted from rendered content.",
            ),
        ),
        migrations.CreateModel(
            name="PageAsset",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                (
                    "alias",
                    models.SlugField(
                        blank=True,
                        help_text="Optional short alias for this page. Use in markdown as @alias",
                        max_length=100,
                    ),
                ),
                (
                    "order",
                    models.PositiveIntegerField(
                        default=0, help_text="Display order in admin"
                    ),
                ),
                (
                    "custom_caption",
                    models.TextField(
                        blank=True, help_text="Override default caption for this page"
                    ),
                ),
                (
                    "custom_alt_text",
                    models.CharField(
                        blank=True,
                        help_text="Override default alt text for this page",
                        max_length=255,
                    ),
                ),
                (
                    "asset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="page_usages",
                        to="engine.asset",
                    ),
                ),
                (
                    "page",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="page_assets",
                        to="engine.page",
                    ),
                ),
            ],
            options={
                "ordering": ["order", "created_at"],
                "indexes": [
                    models.Index(
                        fields=["page", "order"], name="pageasset_page_order_idx"
                    ),
                    models.Index(
                        fields=["page", "asset"], name="pageasset_page_asset_idx"
                    ),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="pageasset",
            constraint=models.UniqueConstraint(
                condition=~models.Q(alias=""),
                fields=("page", "alias"),
                name="unique_page_alias_when_not_blank",
            ),
        ),
        migrations.CreateModel(
            name="PageFurtherReading",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                (
                    "position",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Display order within the Further Reading section.",
                    ),
                ),
                (
                    "note",
                    models.TextField(
                        blank=True,
                        help_text="Optional note shown beneath the entry (why it's recommended).",
                    ),
                ),
                (
                    "page",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="further_reading",
                        to="engine.page",
                    ),
                ),
                (
                    "source",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="page_further_reading_entries",
                        to="engine.source",
                    ),
                ),
            ],
            options={
                "ordering": ["position"],
                "indexes": [
                    models.Index(
                        fields=["page", "position"], name="pagefr_page_position_idx"
                    )
                ],
                "unique_together": {("page", "source")},
            },
        ),
    ]
