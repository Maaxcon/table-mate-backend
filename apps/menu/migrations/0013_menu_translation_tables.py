from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("menu", "0012_menucategory_color"),
    ]

    operations = [
        migrations.CreateModel(
            name="MenuCategoryTranslation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("language_code", models.CharField(max_length=10)),
                ("name", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "category",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="translations",
                        to="menu.MenuCategory",
                    ),
                ),
            ],
            options={
                "ordering": ["category_id", "language_code"],
            },
        ),
        migrations.CreateModel(
            name="MenuItemTranslation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("language_code", models.CharField(max_length=10)),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True, null=True)),
                ("ingredients", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "menu_item",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="translations",
                        to="menu.MenuItem",
                    ),
                ),
            ],
            options={
                "ordering": ["menu_item_id", "language_code"],
            },
        ),
        migrations.CreateModel(
            name="MenuTranslation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("language_code", models.CharField(max_length=10)),
                ("name", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "menu",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="translations",
                        to="menu.Menu",
                    ),
                ),
            ],
            options={
                "ordering": ["menu_id", "language_code"],
            },
        ),
        migrations.AddConstraint(
            model_name="menutranslation",
            constraint=models.UniqueConstraint(
                fields=["menu", "language_code"],
                name="menu_translation_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="menucategorytranslation",
            constraint=models.UniqueConstraint(
                fields=["category", "language_code"],
                name="menu_category_translation_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="menuitemtranslation",
            constraint=models.UniqueConstraint(
                fields=["menu_item", "language_code"],
                name="menu_item_translation_unique",
            ),
        ),
    ]
