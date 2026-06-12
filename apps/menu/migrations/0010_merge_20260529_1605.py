"""Merge migration to resolve multiple menu leaf nodes."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("menu", "0004_cartitem_quantity_check"),
        ("menu", "0009_alter_menuitem_price_decimal_places"),
    ]

    operations = []
