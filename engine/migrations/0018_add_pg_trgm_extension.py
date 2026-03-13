from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("engine", "0017_seed_sitesettings")]

    operations = [
        TrigramExtension(),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS post_title_trgm_gin ON engine_post USING gin (title gin_trgm_ops);",
            reverse_sql="DROP INDEX IF EXISTS post_title_trgm_gin;",
        ),
    ]
