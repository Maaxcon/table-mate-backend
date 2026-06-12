import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps


def seed_customer_participants(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Reservation = apps.get_model("reservations", "Reservation")
    ReservationParticipant = apps.get_model("reservations", "ReservationParticipant")

    participants_to_create = []
    for reservation in Reservation.objects.exclude(customer_id__isnull=True):
        participants_to_create.append(
            ReservationParticipant(
                reservation_id=reservation.id,
                user_id=reservation.customer_id,
                restaurant_id=reservation.restaurant_id,
            )
        )

    ReservationParticipant.objects.bulk_create(
        participants_to_create,
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0002_remove_reservation_reservations_no_overlap_per_table_and_more"),
        ("authentication", "0003_merge_20260526_1321"),
        ("restaurants", "0004_cartitem_quantity_check"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReservationParticipant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "reservation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reservation_participants",
                        to="reservations.reservation",
                    ),
                ),
                (
                    "restaurant",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="restaurants.restaurant"),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reservation_participations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddField(
            model_name="reservation",
            name="participants",
            field=models.ManyToManyField(
                blank=True,
                related_name="participating_reservations",
                through="reservations.ReservationParticipant",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name="reservationparticipant",
            constraint=models.UniqueConstraint(
                fields=("reservation", "user"),
                name="reservations_participant_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="reservationparticipant",
            constraint=models.UniqueConstraint(
                fields=("restaurant", "id"),
                name="reservations_participant_rest_uniq",
            ),
        ),
        migrations.RunPython(seed_customer_participants, migrations.RunPython.noop),
    ]
