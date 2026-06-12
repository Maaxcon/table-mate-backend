from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("restaurants", "0009_zone_table_zone_and_more"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="table",
            name="restaurants_table_status_valid",
        ),
        migrations.AddConstraint(
            model_name="table",
            constraint=models.CheckConstraint(
                condition=models.Q(status__in=["free", "occupied", "reserved"]),
                name="restaurants_table_status_valid",
            ),
        ),
    ]
