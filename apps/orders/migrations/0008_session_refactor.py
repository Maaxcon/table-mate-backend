from datetime import timedelta
from typing import Any

from django.db import migrations, models


def migrate_cancelled_to_voided(apps: Any, schema_editor: Any) -> None:
    Session = apps.get_model("orders", "Session")
    Session.objects.filter(status="cancelled").update(status="voided")


def backfill_reservations_for_orphaned_sessions(apps: Any, schema_editor: Any) -> None:
    Session = apps.get_model("orders", "Session")
    Reservation = apps.get_model("reservations", "Reservation")

    orphaned = Session.objects.filter(reservation__isnull=True).select_related("table")
    for session in orphaned:
        opened_at = session.opened_at or session.created_at

        reservation = Reservation.objects.create(
            restaurant_id=session.restaurant_id,
            table_id=session.table_id,
            guest_count=session.guest_count,
            start_at=opened_at,
            end_at=opened_at + timedelta(seconds=1),
            type="walk_in",
            status="completed",
            created_by_staff=True,
        )
        session.reservation_id = reservation.pk
        session.save(update_fields=["reservation"])


class Migration(migrations.Migration):
    atomic = False
    dependencies = [
        ("orders", "0007_alter_order_public_id_alter_orderitem_public_id_and_more"),
        ("reservations", "0006_add_type_and_created_by_staff"),
    ]

    operations = [
        # 1. Rename started_at -> opened_at
        migrations.RenameField(
            model_name="session",
            old_name="started_at",
            new_name="opened_at",
        ),
        # 2. Fix ordering immediately so RunPython can load the model
        migrations.AlterModelOptions(
            name="session",
            options={"ordering": ["-opened_at", "-id"]},
        ),
        # 3. Remove closed_at
        migrations.RemoveField(
            model_name="session",
            name="closed_at",
        ),
        # 4. Remove old total fields
        migrations.RemoveField(
            model_name="session",
            name="running_total",
        ),
        migrations.RemoveField(
            model_name="session",
            name="final_total",
        ),
        # 5. Add new financial fields
        migrations.AddField(
            model_name="session",
            name="subtotal",
            field=models.DecimalField(decimal_places=4, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="session",
            name="tax",
            field=models.DecimalField(decimal_places=4, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="session",
            name="total",
            field=models.DecimalField(decimal_places=4, default=0, max_digits=14),
        ),
        # 6. Migrate cancelled -> voided
        migrations.RunPython(migrate_cancelled_to_voided, migrations.RunPython.noop),
        # 7. Backfill walk-in reservations for sessions with null reservation
        migrations.RunPython(backfill_reservations_for_orphaned_sessions, migrations.RunPython.noop),
        # 8. Update status constraint: CANCELLED -> VOIDED
        migrations.RemoveConstraint(
            model_name="session",
            name="orders_session_status_valid",
        ),
        migrations.AddConstraint(
            model_name="session",
            constraint=models.CheckConstraint(
                condition=models.Q(status__in=["open", "closed", "voided"]),
                name="orders_session_status_valid",
            ),
        ),
        # 9. Change reservation FK to OneToOneField (now safe: no nulls, no duplicates)
        migrations.AlterField(
            model_name="session",
            name="reservation",
            field=models.OneToOneField(
                on_delete=models.CASCADE,
                related_name="session",
                to="reservations.reservation",
            ),
        ),
        # 10. Update index to use opened_at
        migrations.RemoveIndex(
            model_name="session",
            name="ord_sess_rest_tbl_open_idx",
        ),
        migrations.AddIndex(
            model_name="session",
            index=models.Index(
                condition=models.Q(status="open"),
                fields=["restaurant", "table"],
                name="ord_sess_rest_tbl_open_idx",
            ),
        ),
    ]
