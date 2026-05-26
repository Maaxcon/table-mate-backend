from typing import Any

from django.db import migrations
from django.db.migrations.state import StateApps

VOID_REASONS = [
    ("mispick", "Mispick"),
    ("guest_changed_mind", "Guest changed mind"),
    ("quality_issue", "Quality issue"),
    ("out_of_stock", "Out of stock"),
]


def seed_void_reasons(apps: StateApps, schema_editor: Any) -> None:
    VoidReason = apps.get_model("orders", "VoidReason")
    VoidReason.objects.bulk_create([VoidReason(code=code, label=label) for code, label in VOID_REASONS])


def unseed_void_reasons(apps: StateApps, schema_editor: Any) -> None:
    VoidReason = apps.get_model("orders", "VoidReason")
    VoidReason.objects.filter(code__in=[code for code, _ in VOID_REASONS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0004_voidreason"),
    ]

    operations = [
        migrations.RunPython(seed_void_reasons, reverse_code=unseed_void_reasons),
    ]
