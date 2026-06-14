from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "coremovieshub",
            "0011_telegrammovie_unique_channel_message",
        ),
    ]

    operations = [

        migrations.AddField(
            model_name="telegrammovie",
            name="banner",
            field=models.URLField(
                blank=True,
                null=True,
            ),
        ),

        migrations.AddField(
            model_name="telegrammovie",
            name="overview",
            field=models.TextField(
                blank=True,
            ),
        ),

        migrations.AlterField(
            model_name="telegrammovie",
            name="poster",
            field=models.URLField(
                blank=True,
                null=True,
            ),
        ),

        migrations.AlterField(
            model_name="telegrammovie",
            name="description",
            field=models.TextField(
                blank=True,
                help_text="Telegram caption or custom notes",
            ),
        ),

        migrations.AlterField(
            model_name="telegrammovie",
            name="rating",
            field=models.FloatField(
                blank=True,
                null=True,
            ),
        ),

    ]