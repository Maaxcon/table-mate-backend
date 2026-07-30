import uuid

import django.utils.timezone
from django.db import migrations, models


def gen_uuid(apps, schema_editor):
    Allergen = apps.get_model("menu", "Allergen")
    for allergen in Allergen.objects.all():
        allergen.public_id = uuid.uuid4()
        allergen.save(update_fields=["public_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("menu", "0021_alter_ingredient_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="allergen",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True, default=django.utils.timezone.now
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="allergen",
            name="public_id",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="allergen",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.RunPython(gen_uuid, reverse_code=migrations.RunPython.noop),
        migrations.AlterField(
            model_name="allergen",
            name="public_id",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
