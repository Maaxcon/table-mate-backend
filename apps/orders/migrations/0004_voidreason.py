from django.db import migrations, models


_VOID_REASONS = [
    ("mispick", "Mispick"),
    ("guest_changed_mind", "Guest changed mind"),
    ("quality_issue", "Quality issue"),
    ("out_of_stock", "Out of stock"),
]


def seed_void_reasons(apps, schema_editor):
    VoidReason = apps.get_model("orders", "VoidReason")
    VoidReason.objects.bulk_create(
        [VoidReason(code=code, label=label) for code, label in _VOID_REASONS],
        ignore_conflicts=True,
    )


def unseed_void_reasons(apps, schema_editor):
    VoidReason = apps.get_model("orders", "VoidReason")
    VoidReason.objects.filter(code__in=[c for c, _ in _VOID_REASONS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0003_orderitem_cross_tenant_fks"),
    ]

    operations = [
        migrations.CreateModel(
            name="VoidReason",
            fields=[
                ("code", models.CharField(max_length=32, primary_key=True, serialize=False)),
                ("label", models.CharField(max_length=128)),
            ],
            options={
                "ordering": ["code"],
            },
        ),
        migrations.RunPython(seed_void_reasons, reverse_code=unseed_void_reasons),
    ]
