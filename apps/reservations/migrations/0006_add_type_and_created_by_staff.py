from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0005_add_pending_and_completed_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="reservation",
            name="type",
            field=models.CharField(
                choices=[("pre_booked", "Pre-booked"), ("walk_in", "Walk-in")],
                default="pre_booked",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="reservation",
            name="created_by_staff",
            field=models.BooleanField(default=False),
        ),
        migrations.AddConstraint(
            model_name="reservation",
            constraint=models.CheckConstraint(
                condition=models.Q(type__in=["pre_booked", "walk_in"]),
                name="reservations_reservation_type_valid",
            ),
        ),
    ]
