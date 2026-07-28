from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("feedback", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="feedback",
            name="guest_identity",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name="feedback",
            name="guest",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="feedback",
                to="authentication.user",
            ),
        ),
        migrations.AddConstraint(
            model_name="feedback",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("guest__isnull", False), ("guest_identity__isnull", True))
                    | models.Q(("guest__isnull", True), ("guest_identity__isnull", False))
                ),
                name="feedback_single_owner",
            ),
        ),
    ]
