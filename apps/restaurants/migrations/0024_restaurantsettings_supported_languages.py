from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("restaurants", "0023_seed_new_restaurants"),
    ]

    operations = [
        migrations.AddField(
            model_name="restaurantsettings",
            name="supported_languages",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
