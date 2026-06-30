from __future__ import annotations

from typing import Any

from django.db import migrations, models
from django.db.migrations.state import StateApps


def assign_null_zone_tables(apps: StateApps, schema_editor: Any) -> None:
    Table = apps.get_model("restaurants", "Table")
    Zone = apps.get_model("restaurants", "Zone")
    for table in Table.objects.filter(zone__isnull=True).select_related("restaurant").iterator():
        zone = Zone.objects.filter(restaurant=table.restaurant).order_by("sort_order", "id").first()
        if zone:
            table.zone = zone
            table.save(update_fields=["zone"])


class Migration(migrations.Migration):
    dependencies = [
        ("restaurants", "0019_zone_edge_styles"),
    ]

    operations = [
        migrations.RunPython(assign_null_zone_tables, reverse_code=migrations.RunPython.noop),
        migrations.AlterField(
            model_name="table",
            name="zone",
            field=models.ForeignKey(
                on_delete=models.deletion.PROTECT,
                related_name="tables",
                to="restaurants.zone",
            ),
            preserve_default=False,
        ),
    ]
