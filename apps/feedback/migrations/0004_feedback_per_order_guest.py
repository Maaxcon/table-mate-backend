from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("feedback", "0003_remove_resolved_review_status"),
    ]

    operations = [
        migrations.AlterField(
            model_name="feedback",
            name="order",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="feedback_entries",
                to="orders.order",
            ),
        ),
        migrations.AddConstraint(
            model_name="feedback",
            constraint=models.UniqueConstraint(
                fields=("order", "guest"),
                name="feedback_order_guest_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="feedback",
            constraint=models.UniqueConstraint(
                fields=("order", "guest_identity"),
                name="feedback_order_guest_identity_unique",
            ),
        ),
    ]
