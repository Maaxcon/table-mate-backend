from django.db import migrations, models

import apps.restaurants.models


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
                condition=models.Q(status__in=apps.restaurants.models.TableStatus.values),
                name="restaurants_table_status_valid",
            ),
        ),
    ]
