from django.db import migrations, models


def _close_duplicate_active_sessions(apps, schema_editor):
    CartSession = apps.get_model("orders", "CartSession")
    active = CartSession.objects.filter(status="active").order_by(
        "reservation_id", "-created_at", "-id"
    )
    seen_reservations = set()
    stale_ids = []
    for session in active.values("id", "reservation_id"):
        reservation_id = session["reservation_id"]
        if reservation_id in seen_reservations:
            stale_ids.append(session["id"])
        else:
            seen_reservations.add(reservation_id)
    if stale_ids:
        CartSession.objects.filter(id__in=stale_ids).update(status="closed")


def _noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0013_rename_device_id_guest_identity"),
    ]

    operations = [
        migrations.RunPython(_close_duplicate_active_sessions, _noop),
        migrations.AddConstraint(
            model_name="cartsession",
            constraint=models.UniqueConstraint(
                fields=("reservation",),
                condition=models.Q(status="active"),
                name="orders_cartsession_one_active_per_reservation",
            ),
        ),
    ]
