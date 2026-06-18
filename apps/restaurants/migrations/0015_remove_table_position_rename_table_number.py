from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("restaurants", "0014_merge_20260612_1620"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="table",
            name="position_x",
        ),
        migrations.RemoveField(
            model_name="table",
            name="position_y",
        ),
        migrations.RemoveConstraint(
            model_name="table",
            name="restaurants_table_restaurant_number_unique",
        ),
        migrations.RenameField(
            model_name="table",
            old_name="table_number",
            new_name="public_number",
        ),
        migrations.AlterField(
            model_name="table",
            name="public_number",
            field=models.CharField(db_index=True, max_length=64),
        ),
    ]
