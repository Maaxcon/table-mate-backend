from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("menu", "0001_initial"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="menuitem",
            constraint=models.UniqueConstraint(
                fields=("restaurant", "id"),
                name="menu_menuitem_rest_uniq",
            ),
        ),
    ]
