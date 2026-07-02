from django.db import migrations


def backfill_ends_at(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE orders_session AS s
            SET ends_at = r.end_at
            FROM reservations_reservation AS r
            WHERE s.reservation_id = r.id
              AND s.ends_at IS NULL
            """,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0024_one_open_session_per_table"),
    ]

    operations = [
        migrations.RunPython(backfill_ends_at, migrations.RunPython.noop),
    ]
