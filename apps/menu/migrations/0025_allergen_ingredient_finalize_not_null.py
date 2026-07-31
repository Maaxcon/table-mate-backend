import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("menu", "0024_backfill_allergen_ingredient_vocab"),
    ]

    operations = [
        migrations.AlterField(
            model_name="allergen",
            name="name",
            field=models.CharField(max_length=255),
        ),
        migrations.AlterField(
            model_name="allergen",
            name="restaurant",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to="restaurants.restaurant",
            ),
        ),
        migrations.AlterField(
            model_name="ingredient",
            name="name",
            field=models.CharField(max_length=255),
        ),
    ]
