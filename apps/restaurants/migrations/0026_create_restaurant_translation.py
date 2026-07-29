import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("restaurants", "0025_set_supported_languages"),
    ]

    operations = [
        migrations.CreateModel(
            name="RestaurantTranslation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("language_code", models.CharField(max_length=10)),
                ("address", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "restaurant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="translations",
                        to="restaurants.restaurant",
                    ),
                ),
            ],
            options={
                "ordering": ["restaurant_id", "language_code"],
            },
        ),
        migrations.AddConstraint(
            model_name="restauranttranslation",
            constraint=models.UniqueConstraint(
                fields=("restaurant", "language_code"),
                name="restaurant_translation_unique",
            ),
        ),
    ]
