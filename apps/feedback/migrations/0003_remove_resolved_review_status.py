from typing import Any

from django.db import migrations, models


def migrate_resolved_feedback(apps: Any, schema_editor: Any) -> None:
    Feedback = apps.get_model("feedback", "Feedback")
    Feedback.objects.filter(review_status="resolved").update(review_status="reviewed")


class Migration(migrations.Migration):
    dependencies = [
        ("feedback", "0002_feedback_guest_identity"),
    ]

    operations = [
        migrations.RunPython(migrate_resolved_feedback, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="feedback",
            name="feedback_review_status_valid",
        ),
        migrations.AlterField(
            model_name="feedback",
            name="review_status",
            field=models.CharField(
                choices=[("new", "New"), ("reviewed", "Reviewed")],
                default="new",
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name="feedback",
            constraint=models.CheckConstraint(
                condition=models.Q(("review_status__in", ["new", "reviewed"])),
                name="feedback_review_status_valid",
            ),
        ),
    ]
