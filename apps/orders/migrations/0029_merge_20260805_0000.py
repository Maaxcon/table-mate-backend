from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0027_orderitem_guest_identity"),
        ("orders", "0028_session_scheduled_status"),
    ]

    operations = []
