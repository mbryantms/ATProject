from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("engine", "0036_add_postsimilarity_drop_related_posts"),
    ]

    operations = [
        migrations.AlterField(
            model_name="assetrendition",
            name="file",
            field=models.FileField(
                help_text="Rendition file (image, video, or poster frame)",
                upload_to="assets/renditions/%Y/%m/",
            ),
        ),
    ]
