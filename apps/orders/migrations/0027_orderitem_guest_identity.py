from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0026_session_auto_extended"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderitem",
            name="guest_identity",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
