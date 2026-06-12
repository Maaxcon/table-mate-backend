"""Merge migration to resolve multiple restaurant leaf nodes."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("restaurants", "0004_cartitem_quantity_check"),
        ("restaurants", "0006_merge_20260528_0000"),
    ]

    operations = []
