from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("menu", "0002_menuitem_restaurant_id_unique"),
        ("orders", "0002_order_restaurant_id_unique"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            ALTER TABLE orders_orderitem
            ADD CONSTRAINT orders_orderitem_menu_item_same_rest_fk
            FOREIGN KEY (restaurant_id, menu_item_id)
            REFERENCES menu_menuitem (restaurant_id, id)
            DEFERRABLE INITIALLY DEFERRED
            """,
            reverse_sql="""
            ALTER TABLE orders_orderitem
            DROP CONSTRAINT orders_orderitem_menu_item_same_rest_fk
            """,
        ),
        migrations.RunSQL(
            sql="""
            ALTER TABLE orders_orderitem
            ADD CONSTRAINT orders_orderitem_order_same_rest_fk
            FOREIGN KEY (restaurant_id, order_id)
            REFERENCES orders_order (restaurant_id, id)
            DEFERRABLE INITIALLY DEFERRED
            """,
            reverse_sql="""
            ALTER TABLE orders_orderitem
            DROP CONSTRAINT orders_orderitem_order_same_rest_fk
            """,
        ),
    ]
