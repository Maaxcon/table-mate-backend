from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("menu", "0025_allergen_ingredient_finalize_not_null"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="allergen",
            name="allergen_restaurant_key_unique",
        ),
        migrations.RemoveConstraint(
            model_name="ingredient",
            name="ingredient_restaurant_key_unique",
        ),
        migrations.RemoveField(
            model_name="allergen",
            name="key",
        ),
        migrations.RemoveField(
            model_name="ingredient",
            name="key",
        ),
        migrations.AddConstraint(
            model_name="allergen",
            constraint=models.UniqueConstraint(
                fields=("restaurant", "name"),
                name="allergen_restaurant_name_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="ingredient",
            constraint=models.UniqueConstraint(
                fields=("restaurant", "name"),
                name="ingredient_restaurant_name_unique",
            ),
        ),
    ]
