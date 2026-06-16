from collections import defaultdict
from datetime import timedelta
from typing import Any

from django.db import IntegrityError, migrations, models
from django.db.models import F


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


def backfill_subtotal_and_total(apps: Any, schema_editor: Any) -> None:
    Session = apps.get_model("orders", "Session")
    Session.objects.filter(running_total__isnull=False).update(subtotal=F("running_total"))
    Session.objects.filter(final_total__isnull=False).update(total=F("final_total"))


def ensure_no_duplicate_reservations(apps: Any, schema_editor: Any) -> None:
    Session = apps.get_model("orders", "Session")
    dupes: dict[int, list[int]] = defaultdict(list)
    for session_id, reservation_id in Session.objects.filter(reservation_id__isnull=False).values_list(
        "id", "reservation_id"
    ):
        dupes[reservation_id].append(session_id)

    for reservation_id, session_ids in dupes.items():
        if len(session_ids) > 1:
            raise IntegrityError(
                f"Migration aborting for data safety: Reservation {reservation_id} "
                f"is shared by Session IDs {session_ids}. "
                "Resolve the duplicates before converting reservation to OneToOneField."
            )


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
        # 4. Add new financial fields (before removing old ones so backfill can run)
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
        # 5. Copy old totals into new columns before dropping
        migrations.RunPython(backfill_subtotal_and_total, migrations.RunPython.noop),
        # 6. Remove old total fields
        migrations.RemoveField(
            model_name="session",
            name="running_total",
        ),
        migrations.RemoveField(
            model_name="session",
            name="final_total",
        ),
        # 7. Migrate cancelled -> voided
        migrations.RunPython(migrate_cancelled_to_voided, migrations.RunPython.noop),
        # 8. Backfill walk-in reservations for sessions with null reservation
        migrations.RunPython(backfill_reservations_for_orphaned_sessions, migrations.RunPython.noop),
        # 9. Update status constraint: CANCELLED -> VOIDED
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
        # 10. Validate no duplicate reservations before enforcing uniqueness
        migrations.RunPython(ensure_no_duplicate_reservations, migrations.RunPython.noop),
        # 11. Change reservation FK to OneToOneField (now safe: no nulls, no duplicates)
        migrations.AlterField(
            model_name="session",
            name="reservation",
            field=models.OneToOneField(
                on_delete=models.CASCADE,
                related_name="session",
                to="reservations.reservation",
            ),
        ),
        # 12. Update index to use opened_at
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
