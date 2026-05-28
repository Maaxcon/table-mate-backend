import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("menu", "0003_alter_menu_public_id_alter_menucategory_public_id_and_more"),
        ("orders", "0006_merge_20260526_1321"),
        ("reservations", "0002_remove_reservation_reservations_no_overlap_per_table_and_more"),
        ("restaurants", "0003_merge_20260526_1437"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CartSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("closed", "Closed")],
                        default="active",
                        max_length=20,
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_cart_sessions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "participants",
                    models.ManyToManyField(
                        blank=True,
                        related_name="cart_sessions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "reservation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cart_sessions",
                        to="reservations.reservation",
                    ),
                ),
                (
                    "restaurant",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="restaurants.restaurant"),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="CartItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("quantity", models.PositiveIntegerField()),
                ("comment", models.TextField(blank=True, null=True)),
                (
                    "added_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="added_cart_items",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "cart_session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="orders.cartsession",
                    ),
                ),
                (
                    "menu_item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="cart_items",
                        to="menu.menuitem",
                    ),
                ),
                (
                    "restaurant",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="restaurants.restaurant"),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="cartsession",
            constraint=models.CheckConstraint(
                condition=models.Q(("status__in", ["active", "closed"])),
                name="orders_cartsession_status_valid",
            ),
        ),
    ]
