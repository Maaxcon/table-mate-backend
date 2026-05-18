from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0001_initial"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="order",
            constraint=models.UniqueConstraint(
                fields=("restaurant", "id"),
                name="orders_order_rest_uniq",
            ),
        ),
    ]
