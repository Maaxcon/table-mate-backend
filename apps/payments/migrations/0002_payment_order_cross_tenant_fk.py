from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0002_order_restaurant_id_unique"),
        ("payments", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            ALTER TABLE payments_payment
            ADD CONSTRAINT payments_payment_order_same_rest_fk
            FOREIGN KEY (restaurant_id, order_id)
            REFERENCES orders_order (restaurant_id, id)
            DEFERRABLE INITIALLY DEFERRED
            """,
            reverse_sql="""
            ALTER TABLE payments_payment
            DROP CONSTRAINT payments_payment_order_same_rest_fk
            """,
        ),
    ]
