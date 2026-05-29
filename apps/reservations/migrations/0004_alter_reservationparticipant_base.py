from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0003_reservationparticipant"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="reservationparticipant",
            name="reservations_participant_rest_uniq",
        ),
        migrations.RemoveField(
            model_name="reservationparticipant",
            name="restaurant",
        ),
    ]
