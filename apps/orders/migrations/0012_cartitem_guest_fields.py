from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0011_merge_20260602_1217"),
    ]

    operations = [
        migrations.AddField(
            model_name="cartitem",
            name="device_id",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="cartitem",
            name="guest_slot",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="cartitem",
            name="is_paid",
            field=models.BooleanField(default=False),
        ),
    ]
