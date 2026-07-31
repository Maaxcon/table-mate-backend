import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("menu", "0022_allergen_public_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="allergen",
            name="name",
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="allergen",
            name="restaurant",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="restaurants.restaurant",
            ),
        ),
        migrations.AddField(
            model_name="ingredient",
            name="name",
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name="allergen",
            name="key",
            field=models.SlugField(max_length=100),
        ),
        migrations.AlterModelOptions(
            name="allergen",
            options={"ordering": ["sort_order", "id"]},
        ),
        migrations.AddConstraint(
            model_name="allergen",
            constraint=models.UniqueConstraint(
                fields=("restaurant", "key"),
                name="allergen_restaurant_key_unique",
            ),
        ),
    ]
