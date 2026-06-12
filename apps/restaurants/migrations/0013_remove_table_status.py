from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("restaurants", "0012_alter_table_status"),
        ("orders", "0007_alter_order_public_id_alter_orderitem_public_id_and_more"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="table",
            name="restaurants_table_status_valid",
        ),
        migrations.RemoveField(
            model_name="table",
            name="status",
        ),
    ]
