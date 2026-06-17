from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0012_cartitem_guest_fields"),
    ]

    operations = [
        migrations.RenameField(
            model_name="cartitem",
            old_name="device_id",
            new_name="guest_identity",
        ),
    ]
