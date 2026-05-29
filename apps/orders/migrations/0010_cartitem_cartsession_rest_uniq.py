from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0009_cartitem_unique_session_item"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="cartitem",
            constraint=models.UniqueConstraint(fields=("restaurant", "id"), name="orders_cartitem_rest_uniq"),
        ),
        migrations.AddConstraint(
            model_name="cartsession",
            constraint=models.UniqueConstraint(fields=("restaurant", "id"), name="orders_cartsession_rest_uniq"),
        ),
    ]
